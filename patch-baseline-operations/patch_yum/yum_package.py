# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import patch_common.base_package
import rpmUtils
import patch_common.instance_info
import yum.Errors
import yum_update_notice
import yum_require
import logging
from datetime import datetime

logger = logging.getLogger()

class YumPackage(patch_common.base_package.BasePackage):
    def __init__(self, pkg_tup,
                 compliance=patch_common.base_package.BasePackage.compliance_unspecified,
                 classification=None,
                 severity=None,
                 cve_ids=None,
                 installed_time=None,
                 buildtime=0.0):
        """
        :param pkg_tup: package tuple, (name, arch, epoch, version, release)
        :param compliance: compliance level
        :param buildtime: defaults to (1970, 1, 1)
        """
        patch_common.base_package.BasePackage.__init__(self, pkg_tup[0], pkg_tup[1], compliance)
        self.epoch = pkg_tup[2]
        self.version = pkg_tup[3]
        self.release = pkg_tup[4]
        self.naevr = pkg_tup
        self.notice = None
        self.classification = classification
        self.severity = severity
        self.pkg_obj = None
        self.installed_time = installed_time
        self.buildtime = buildtime
        self.cve_ids= cve_ids
        self.all_known_cves_for_update = []

    def __getitem__(self, item):
        """
        Delegate the call to the notice.
        :param item:
        :return:
        """
        if self.notice is not None:
            return self.notice[item]
        else:
            return None

    def __setitem__(self, key, value):
        self.notice[key] = value

    @property
    def is_non_security(self):
        return self.notice is None

    @staticmethod
    def from_package(pkg):
        """
        Creates an instance from a yum package object.
        :param pkg: from a package sack.
        :return: the instance
        """
        return YumPackage(
            pkg_tup=(pkg.name, pkg.arch, pkg.epoch, pkg.ver, pkg.release)
        )

    @staticmethod
    def from_tuple_notice(pkg_tup, notice, compliance=patch_common.base_package.BasePackage.compliance_unspecified):
        """
        Creates an instance from a package tuple and an update notice.
        :param compliance: level
        :param pkg_tup: (name, arch, epoch, version, release) tuple
        :param notice: update notice from yum
        :return:
        """
        instance = YumPackage(
            pkg_tup=pkg_tup,
            compliance=compliance,
            classification=_value_from_notice(key="type", notice=notice),
            severity=_value_from_notice(key="severity", notice=notice)
        )
        instance.notice = notice
        return instance

    def get_filter_key_value(self, key):
        """
        Gets the value for a filter key for this package and notice.
        :param key: property to fetch
        :return: the value, the string "None" if not found
        """
        if key == "PRODUCT":
            return patch_common.instance_info.product
        elif key == "CLASSIFICATION":
            value = self.classification
        elif key == "SEVERITY":
            value = self.severity
        return value.title() if value is not None else None

    def compare_version(self, other):
        """
        :param other: yum package from us
        :return: < 0 if self is older than othr, 0 if equal, > 0 if self is newer
        """
        return rpmUtils.miscutils.compareEVR(
            (self.epoch, self.version, self.release),
            (other.epoch, other.version, other.release)
        )

    def __hash__(self):
        return hash(
            (self.name, self.arch, self.epoch,
             self.version, self.release, self.compliance)
        )

    def __eq__(self, other):
        return self.name == other.name and \
               self.arch == other.arch and \
               self.epoch == other.epoch and \
               self.version == other.version and \
               self.release == other.release and \
               self.compliance == other.compliance


    def __str__(self):
        return str((self.name, self.arch, self.epoch, self.version, self.release, self.compliance,
                    self.is_non_security))

    def match_baseline(self, baseline):
        """
        Check whether package matches the baseline or not
        :param baseline: target baseline to compare with
        :return: boolean to indicate whether package matches the baseline or not
        """
        if self.is_rejected(baseline):
            return False
        if self.notice:
            # security updates
            return baseline.test_notice(self) or yum_update_notice.match_yum_package(baseline.include, self.naevr)
        else:
            # non-security updates
            return baseline.test_notice(self) or \
                   (yum_update_notice.match_yum_package(baseline.include, self.naevr) and baseline.approved_patches_enable_non_security)

    def match_override_list(self, override_list=None):
        """
        Check whether package matches the override list
        :param override_list: install override list to override installation decisions
        :return: boolean to indicate whether package matches the override list or not
        """
        return override_list is not None and yum_update_notice.match_yum_package(override_list.all_filters, self.naevr)

    def is_matched(self, baseline, override_list=None):
        """
        Check whether package is matched against by baseline or override list
        :param baseline: baseline to be matched
        :param override_list: install override list to be matched
        :return: True for matched pkg, False otherwise
        """
        return self.match_override_list(override_list) if override_list else self.match_baseline(baseline)

    def set_package_object(self, yb):
        """
        Set YUM package object
        :param yb: YumBase from yum
        :return:
        """
        self.pkg_obj = _get_yum_package_object(yb, self.naevr)

    def check_requires(self, yb, baseline, override_list=None):
        """
        Check whether package's requires can be installed against baseline or override list
        :param yb: yumBase form yum
        :param baseline: baseline to be matched
        :param override_list: install override list to be matched
        :return: True for pkg that can be installed, False otherwise
        """
        return yum_require.check_all_requires(yb, self, baseline, override_list)

    def is_applicable(self, yb, available_tuples):
        """
        Check whether package is applicable or not according to available pkgs
        :param yb: yumBase from yum
        :param available_tuples: available package tuples
        :return: True for known and applicable pkg, False otherwise
        """
        return self.arch in yb.arch.archlist and self.naevr in available_tuples

    def is_rejected(self, baseline):
        """
        Check whether package is a rejected patch or not
        :param baseline: baseline to be checked against
        :return: True for rejected patch, False otherwise
        """
        return baseline.has_rejected_patches and yum_update_notice.match_yum_package(baseline.exclude, self.naevr)

    def get_updated_time(self):
        return max(yum_update_notice.get_update_notice_timestamp(self), datetime.utcfromtimestamp(self.buildtime))

def _value_from_notice(key, notice):
    return notice[key].title() if notice[key] is not None else None


def _get_yum_package_object(yb, pkgtup, allow_missing=False):
    """
    Get package object from the pkgtup

    :param yb: YumBase from yum
    :param pkgtup: package tuple from yum in the format of (name, arch, epoch, version, release)
    :param allow_missing: boolean to allow missing pkg, when False and no object found, it will print a warning
    :return: package object from yum
    """
    try:
        return yb.getPackageObject(pkgtup, allow_missing)
    except yum.Errors.DepError, e:
        logger.warn("Unable to find package object for pkgtup %s", pkgtup)
