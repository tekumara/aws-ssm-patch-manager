# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import logging

from patch_apt.constants import COMPLIANCE_UNSPECIFIED
from patch_apt.file_utilities import get_file_last_modification_time
from patch_apt.package_version import get_package_versions, is_security_version
from patch_common.package_matcher import match_package, generate_package_data, APT_CODES

class Package:
    def __init__(self, apt_package):
        """
        Constructor for the package.
        :param apt_package: from the apt cache
        """
        self.apt_package = apt_package
        # get_package_versions will return a sorted (from latest to oldest) list of versions
        self.versions = get_package_versions(apt_package)
        self.matched_upgradable_versions = []
        self.compliance_level = COMPLIANCE_UNSPECIFIED
        # default to the first one and will be reset to the correct one after matching
        self.candidate_pkg_ver = self.versions[0]

    def _set_installed_as_candidate(self):
        """
        Set the installed one to be the candidate
        :return:
        """
        for pkg_ver in self.versions:
            if pkg_ver.is_installed:
                self.set_candidate(pkg_ver)
                break


    def _has_matched_versions(self, versions):
        """
        Check whether there exists versions for a given list of filter versions, and set the candidate version
        :param versions: a list of filtered versions
        :return: a tuple of boolean in the format of (is_match, has_upgrades), where
            is_matched indicates whether the given versions contains one or more matched versions
            has_upgrades indicates whether the given versions contains one or more upgradable versions
        """
        if versions:
            # exists matched versions
            if self.is_installed:
                # pkg installed, check whether exists upgradable versions
                # since the applicable versions are sorted from latest to oldest,
                # the filtered subset of versions by looping the sorted list will also be sorted from latest to oldest
                self.matched_upgradable_versions = [pkg_ver for pkg_ver in versions if pkg_ver.is_upgradable]
                if len(self.matched_upgradable_versions) > 0:
                    # exists matched and upgradable versions

                    # set the candidate and compliance level to the latest upgradable one
                    self.set_candidate(self.matched_upgradable_versions[0])
                    return True, True
                else:
                    # exists matched versions and installed but no upgradable versions
                    # set the candidate and compliance level to the installed one
                    self._set_installed_as_candidate()
            else:
                # pkg not installed
                # since the applicable versions are sorted from latest to oldest,
                # the filtered subset of versions by looping the sorted list will also be sorted from latest to oldest
                # set the candidate and compliance level to be the latest matched one
                self.set_candidate(versions[0])

            # matched but not upgrades or not installed
            return True, False

        # no matched versions
        else:
            # not matched but installed
            # set the candidate and compliance level to the installed one
            if self.is_installed:
                self._set_installed_as_candidate()
        return False, False

    def __hash__(self):
        return hash(
            (self.name, self.architecture, self.version)
        )

    def __eq__(self, other):
        return self.name == other.name and self.architecture == other.architecture and self.version == other.version

    def __str__(self):
        return '%s.%s.%s' % (self.name, self.architecture, self.version)

    def __repr__(self):
        return '%s.%s.%s' % (self.name, self.architecture, self.version)

    def match_baseline(self, patch_snapshot):
        """
        Method to check whether the package is matching a baseline or not
        :param patch_snapshot: patch snapshot object which contains the baseline attributes
        :return: a tuple of boolean in the format of (is_match, has_upgrades), where
            is_matched indicates whether the given versions contains one or more matched versions
            has_upgrades indicates whether the given versions contains one or more upgradable versions
        """
        filtered_versions = [pkg_ver for pkg_ver in self.versions if pkg_ver.match_baseline(patch_snapshot)]
        return self._has_matched_versions(filtered_versions)


    def match_override_list(self, override_list):
        """
        Method to check whether the package is matching an override list or not
        :param override_list: InstallOverrideList object from patch common
        :return: True if it matches the baseline, False otherwise
        """
        filtered_versions = [pkg_ver for pkg_ver in self.versions if pkg_ver.match_override_list(override_list)]
        return self._has_matched_versions(filtered_versions)


    def adjust_candidate(self, upgradable_packages, patch_snapshot, override_list=None):
        """
        Method to adjust the candidate with the dependency check
        :param upgradable_packages: a list of upgradable packages
        :param patch_snapshot: patch snapshot object which contains baseline attributes
        :param override_list: InstallOverrideList object from patch common
        :return:
        """
        if self.has_matched_upgrades:
            for pkg_ver in self.matched_upgradable_versions:
                if pkg_ver.mark_upgrade(upgradable_packages, patch_snapshot, override_list, check_related_changes=True):
                    self.set_candidate(pkg_ver)
                    return True
        return False


    def has_matched_upgrades(self):
        """
        Method to check whether there is a matched upgradable packages or not
        :return: True if exists matched upgradable pkg, False otherwise
        """
        return bool(self.matched_upgradable_versions)


    def compare_version(self, other):
        """
        Compare the candidate version with another package object
        :param other: package object
        :return: <0 if lower than other pkg, =0 if equals to other pkg, >0 if higher than other pkg
        """
        return self.candidate_pkg_ver.compare_version(other.candidate_pkg_ver)


    def mark_upgrade(self, patch_snapshot=None, override_list=None):
        """
        Marks the package for upgrade.
        :return: True if successfully mark the package to be upgrade and pass the check
        """
        return self.candidate_pkg_ver.mark_upgrade(patch_snapshot, override_list)


    def set_candidate(self, pkg_ver=None):
        """
        Method to set the apt package candidate to be given package version
        :param pkg_ver: pkg version
        :return:
        """
        if pkg_ver:
            self.candidate_pkg_ver = pkg_ver
        self.apt_package.candidate = self.candidate_pkg_ver.apt_package_version
        self.compliance_level = self.candidate_pkg_ver.compliance_level


    def is_installed_rejected(self, patch_snapshot):
        """
        Check to see if pkg is installed and rejected with the snapshot
        :param patch_snapshot: patch snapshot which contains the baseline attributes
        :return: True if pkg is installed rejected, False otherwise
        """
        if self.is_installed:
            return patch_snapshot.block_rejected_patches and \
                   match_package(patch_snapshot.rejected_patches,
                                 generate_package_data((self.name, self.architecture, None, self.apt_package.installed.version, None), APT_CODES)
                                 )
        return False


    @property
    def name(self):
        """
        Returns the package name for the APT package.
        :return: the package name.
        """
        return self.apt_package.name

    @property
    def architecture(self):
        """
        The architecture of the package.
        :return: the architecture of the package.
        """
        return self.apt_package.architecture()

    @property
    def fullname(self):
        return self.apt_package.fullname

    @property
    def priority(self):
        """
        Returns the package's candidate priority.
        :return: the package's candidate priority for the security or non security package.
        """
        return self.candidate_pkg_ver.priority

    @property
    def section(self):
        """
        Returns the package's candidate section.
        :return: the package's candidate section for the security or non security package.
        """
        return self.candidate_pkg_ver.section

    @property
    def is_installed(self):
        """
        If the package is installed.
        :return: True, if the package is installed. False, otherwise.
        """
        return self.apt_package.is_installed

    @property
    def is_upgradable(self):
        """
        If the package is upgradable.
        :return: True, if the package is upgradable. False, otherwise.
        """
        return self.apt_package.is_upgradable

    @property
    def marked_upgrade(self):
        """
        Returns True or False, if the package is marked for upgrade.
        :return: True if the package is marked for upgrade. False, otherwise.
        """
        return self.apt_package.marked_upgrade

    @property
    def version(self):
        """
        The candidate version of the package.
        :return: the candidate version of the package.
        """
        return self.candidate_pkg_ver.version


    @property
    def installed_time(self):
        """
        Get the package's installed time according to the dpkg list file last modification time

        GNU/Linux Debian has no built-in tools to get the install time, and the history in /var/log/dpkg.log* could be lost,
        but all information about programs installed in the standard way is saved in files with program-name.list
        in the location /var/lib/dpkg/info/.
        In particular, /var/lib/dpkg/info/$packagename.list is created/updated when the package version is installed
        (and not modified afterwards) and it only show when a package was last updated.
        But there is no information about manually installed programs there.
        Refer to https://unix.stackexchange.com/questions/12578/list-packages-on-an-apt-based-system-by-installation-date
        :return: installed time as epoch seconds or None
        """
        dpkg_list_file_path_pattern = '/var/lib/dpkg/info/%s.list'
        possible_path = [
            # DO NOT change the order, check the fullname first, which contains pkg name and arch
            dpkg_list_file_path_pattern % self.fullname, # e.g. /var/lib/dpkg/info/libgpm2:amd64.list
            dpkg_list_file_path_pattern % self.name  # e.g. /var/lib/dpkg/info/python3-apt.list
        ]
        for path in possible_path:
            install_time = get_file_last_modification_time(path)

            if install_time:
                return install_time

    @installed_time.setter
    def installed_time(self, value):
        return value
