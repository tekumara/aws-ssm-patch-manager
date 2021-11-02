# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common import base_package
from patch_common import rpm_version
from patch_common.constant_repository import Compliance_levels
from patch_common.base_cli_bean import BaseCLIBean
from patch_common import package_matcher
from datetime import datetime
import logging

logger = logging.getLogger()


class DnfPackage(BaseCLIBean):
    """
    Class for representing a DNF package.
    :param name: the package name
    :param taxonomy: the name, version, release, and architecture e.g. python3-perf-4.18.0-147.0.2.el8_1.x86_64
    :param classification: examples: sec, bugfix or enhancement
    :param severity: examples: LOW, MODERATE, IMPORTANT, CRITICAL
    :param issued_date: date package patch was issued
    """

    def __init__(self, **kwargs):
        super(DnfPackage, self).__init__(**kwargs)
        self.taxonomy = self.__get_param(kwargs, "taxonomy", "")
        self.epoch = self.__get_param(kwargs, "epoch", "")
        self.compliance = self.__get_param(kwargs, "compliance", Compliance_levels.UNSPECIFIED)
        self.advisory_ids = self.__get_param(kwargs, "advisory_ids", set())
        self.installed_time = self.__get_param(kwargs, "installed_time", "0")
        self.module_name = self.__get_param(kwargs, "module_name", None)
        self.module_stream = self.__get_param(kwargs, "module_stream", None)

    def __get_param(self, arg_dict, key, default):
        """
        Method for getting a key from a dict else providing a default.
        :param key - is the key to get.
        :param default - is the default ot provide if the key does not exist.
        :returns the key value form the dict or the default if one does not exist.
        """
        return arg_dict[key] if key in arg_dict else default

    @property
    def compliance(self):
        return self.__compliance

    @compliance.setter
    def compliance(self, compliance):
        """
        Set compliance if higher than current compliance level
        :param compliance: BasePackage.compliance
        """
        if compliance is None:
            return

        if hasattr(self, 'compliance'):
            current_compliance_code = Compliance_levels.COMPLIANCE_LEVELS[self.__compliance]
            new_compliance_code = Compliance_levels.COMPLIANCE_LEVELS[compliance]
            if new_compliance_code > current_compliance_code:
                self.__compliance = compliance
        else:
            self.__compliance = compliance

    @property
    def latest_edition(self):
        """
        Property to return the latest edition available for a package
        """
        if self.available_edition is None or self.available_edition == '0':
            return self.current_edition
        elif self.current_edition is None:
            return self.available_edition
        elif rpm_version.compare(self.current_edition, self.available_edition) < 0:
            return self.available_edition
        else:
            return self.current_edition

    @property
    def version(self):
        """
        Property to return the version of the latest edition
        """
        return self.latest_edition.split("-")[0]

    @property
    def release(self):
        """
        Property to return the release of the latest edition
        """
        return "-".join(self.latest_edition.split("-")[1:])

    @staticmethod
    def from_raw_dnf_string(raw_package_string, package_is_installed):
        """
        Method to convert the string output of a DNF command into a DNF Package Object
        :param package_is_installed: Whether the given package and version are already installed
        :param raw_package_string: Raw string returned by Dnf CLI
        Example of raw string:
            "NetworkManager.x86_64                 1:1.14.0-14.el8                 @anaconda"
        :return: Dnf Package Object
        """
        if raw_package_string is None or raw_package_string == "":
            raise ValueError("Raw Package String must not be Null or Empty")

        package_na = raw_package_string.split()[0]
        package_vr = raw_package_string.split()[1]
        package_epoch = "0"
        if ':' in package_vr:
            package_epoch = package_vr.split(':')[0]
            package_vr = ":".join(package_vr.split(':')[1:])
        package_version = package_vr.split('-')[0]
        package_release = "-".join(package_vr.split('-')[1:])
        package_name = ".".join(package_na.split('.')[:-1])
        package_arch = package_na.split('.')[-1]
        taxonomy = "{}-{}:{}-{}.{}".format(package_name, package_epoch, package_version, package_release, package_arch)

        if package_is_installed:
            current_version = "{}-{}".format(package_version, package_release)
            available_version = "0"
        else:
            available_version = "{}-{}".format(package_version, package_release)
            current_version = None
        return DnfPackage(
            taxonomy=taxonomy,
            name=package_name,
            arch=package_arch,
            epoch=package_epoch,
            release=package_release,
            current_edition=current_version,
            installed=package_is_installed,
            available_edition=available_version
        )

    def compare_version(self, other_version):
        """
        Uses RPM comparison code from patch_common to compare which package release is newer
        :param other_version: another DnfPackage to compare with
        :return: 1 if self is newer, 0 if equal, -1 if other is newer
        """
        if other_version is None:
            raise ValueError("Supplied version must not be Null")
        return rpm_version.compare(self.latest_edition, other_version)

    def assign_match_override_list(self, override_list):
        """
        Set match_override_list by matching a package to the Install Override List
        :param override_list: OverrideList object
        :return: True if package matches any package from Install Override List
        """
        if override_list is None:
            return False
        pkg_tup = (self.name, self.arch, self.epoch, self.version, self.release)
        # using naevr, different permutations of the package taxonomy is in pkg_data
        pkg_data = package_matcher.generate_package_data(pkg_tup)
        self.matches_install_override_list = package_matcher.match_package(override_list.all_filters, pkg_data)

    def assign_match_baseline(self, baseline):
        """
        Set match_baseline field using baseline object to determine if a patch matches the specified baseline rules
        :param baseline: Baseline object from patch_common
        """
        if baseline is None:
            raise ValueError("Baseline must not be Null")
        baseline.assign_compliance(self)

    def assign_installed(self, installed_na_packages):
        """
        Uses dictionary of installed packages to set the installed and current_edition fields of this package
        :param installed_na_packages: (name, arch) => DnfPackage dictionary of installed packages
        """
        # Check if the package is installed
        if (self.name, self.arch) in installed_na_packages:
            self.installed = True
            self.current_edition = installed_na_packages[(self.name, self.arch)].current_edition

    def match_exclude_patterns(self, exclude_list):
        """
        Uses baseline object to determine if a patch is in the rejected list
        :param exclude_list: list of excluded patch names
        :return: True if rejected explicitly by baseline, False otherwise
        """
        pkg_tup = (self.name, self.arch, self.epoch, self.version, self.release)
        pkg_data = package_matcher.generate_package_data(pkg_tup)
        return exclude_list is not None and len(exclude_list) > 0 \
               and package_matcher.match_package(exclude_list, pkg_data)

    def match_include_patterns(self, include_list):
        """
        Uses baseline object to determine if a patch is in the approved list
        We support 4 different ways of approving a package
        1) Regex with package full package name
        2) Bugzilla Id
        3) CVE IDs
        4) Advisory IDs
        :param include_list: list of included patch names or included advisory ids
        :return: True if rejected approved by baseline, False otherwise
        """
        pkg_tup = (self.name, self.arch, self.epoch, self.version, self.release)
        pkg_data = package_matcher.generate_package_data(pkg_tup)
        return include_list is not None and len(include_list) > 0 and (
                package_matcher.match_package(include_list, pkg_data) or
                self._update_notice_ids_match(include_list)
        )

    def taxonomy_matches_pattern(self, pattern_list):
        """
        Method for matching the full taxonomy of a package to a list of patterns
        :param pattern_list: list of regex patterns to match with
        :return: True if package matches any of the patterns
        """
        return pattern_list is not None and len(pattern_list) > 0 and \
            package_matcher.match_package(pattern_list, [self.taxonomy])


    def is_enabled_by_module_stream(self, enabled_module_streams):
        """
        Method to test if package is enabled by a module stream.
        :param enabled_module_streams: (module_name) => list of enabled module_version
        :return: True if module is enabled, or package doesn't belong to a module stream. False otherwise
        """
        if self.module_name is None or self.module_stream is None:
            return True

        if self.module_name in enabled_module_streams and \
                self.module_stream in enabled_module_streams[self.module_name]:
            return True
        else:
            return False

    def _update_notice_ids_match(self, include_list):
        """
        Method for determining if any update notice ids are explicitly matched by the baseline
        :param include_list: list of included patches/ids from the baseline
        :return: True if package matches any of the included ids
        """
        for bgz_id in self.bugzilla_ids:
            if bgz_id in include_list:
                return True
        for cve_id in self.cve_ids:
            if cve_id in include_list:
                return True
        for adv_id in self.advisory_ids:
            if adv_id in include_list:
                return True

        return False

    def __hash__(self):
        return hash((self.taxonomy, self.compliance))

    def __eq__(self, other):
        return self.taxonomy == other.taxonomy and \
               self.compliance == other.compliance

    def __str__(self):
        return str((self.taxonomy, self.compliance))
