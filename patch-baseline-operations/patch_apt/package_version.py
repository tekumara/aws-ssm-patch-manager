# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import logging

from patch_apt.constants import COMPLIANCE_UNSPECIFIED
from patch_apt.constants import FILTER_KEY_PRIORITY
from patch_apt.constants import FILTER_KEY_PRODUCT
from patch_apt.constants import FILTER_KEY_SECTION
from patch_apt.constants import FILTER_VALUE_WILDCARDS
from patch_apt.constants import FILTER_VALUE_SECURITY
from patch_apt.constants import DEBIAN_SECURITY_SITE
from patch_apt.constants import FULL_PACKAGE_VERSION_NAME_FORMAT
from patch_apt.constants import SORTED_COMPLIANCE_LEVEL

from patch_common.package_matcher import match_package, generate_package_data, APT_CODES
from patch_apt.changes_checker import get_pending_changes, format_pending_changes, check_pending_changes

logger = logging.getLogger()

class PackageVersion:
    def __init__(self, apt_package, apt_package_version):
        self.apt_package = apt_package
        self.apt_package_version = apt_package_version

        self.pkg_data = generate_package_data((self.name, self.architecture, None, self.version, None), APT_CODES)
        self.is_security = is_security_version(apt_package_version)

        # Compliance level should be per pkg version since different version could match different rules or approved patches
        self.compliance_level = COMPLIANCE_UNSPECIFIED
        self.is_matched = False
        self.required_changes = {}

    @property
    def name(self):
        return self.apt_package.name

    @property
    def architecture(self):
        return self.apt_package.architecture()

    @property
    def version(self):
        return self.apt_package_version.version

    @property
    def fullname(self):
        return FULL_PACKAGE_VERSION_NAME_FORMAT % (self.name, self.architecture, self.version)

    @property
    def priority(self):
        return self.apt_package_version.priority

    @property
    def section(self):
        return self.apt_package_version.section

    @property
    def is_installed(self):
        # The package version level "is_installed" property is not available for all versions of python-apt
        # The following code logic is copied from latest python-apt
        # More details refer to https://github.com/mvo5/python-apt/blob/debian/sid/apt/package.py#L552-L560
        installed_pkg_ver = self.apt_package.installed
        return installed_pkg_ver is not None and installed_pkg_ver._cand.id == self.apt_package_version._cand.id

    @property
    def is_upgradable(self):
        self.apt_package.candidate = self.apt_package_version
        # Changing pkg's candidate can update pkg's upgradable status
        return self.apt_package.is_upgradable

    @property
    def installed_version(self):
        return self.apt_package.installed.version if self.apt_package.is_installed else None


    def compare_version(self, other):
        """
        Compare version
        :param other: other pkg version from the same pkg
        :return: <0 if lower than other version, =0 if equals to other version, >0 if higher than other version

        """
        return self.apt_package_version._cmp(other.apt_package_version)


    def _set_compliance_to_higher(self, new_compliance_level):
        """
        Compare the two compliance levels and sets the higher of the two for the package version
        :param new_compliance_level: to compare to the first.
        :return: None
        """
        if new_compliance_level is not None and new_compliance_level != self.compliance_level:
            current_compliance_level_number = SORTED_COMPLIANCE_LEVEL.index(self.compliance_level)
            new_compliance_level_number = SORTED_COMPLIANCE_LEVEL.index(new_compliance_level)

            if current_compliance_level_number < new_compliance_level_number:
                self.compliance_level = new_compliance_level


    def _set_match_status(self, enable_non_security=False, compliance_level=COMPLIANCE_UNSPECIFIED):
        """
        Set the baseline matching status and applicable compliance level
        Use this method to set the match status after the pkg version already satisfied the following:
            1) matched global filters
            2) not a rejected patch
            3) match any approval rule or approved patches list

        :param enable_non_security: boolean to indicate whether enables non-security updates or not;
                                    True if non-security updates are allowed; if False, only security updates are updated
        :param compliance_level: compliance level for the pkg version
        :return:
        """
        # When enables non-security, it is matching the baseline
        if enable_non_security or self.is_security:
            self.is_matched = True

            if self.apt_package.is_installed:
                # only set higher compliance for installed and matched pkgs
                # because not installed pkgs are not applicable pkgs, which will not be reported
                self._set_compliance_to_higher(compliance_level)


    def apply_approval_rules(self, product, approval_rules):
        """
        Apply approval rules from the baseline to match the package version
        :param product: product of the instance
        :param approval_rules: aggregated approval rules from the baseline
        :return:
        """
        for approval_rule in approval_rules:
            if match_aggregate_filter(self, product, approval_rule.aggregate_filter):
                # Matching any rule is good enough, we can set the match status
                self._set_match_status(approval_rule.enable_non_security_updates,
                                       approval_rule.compliance_level)
                # Do not return here so that we can set the compliance level to the highest one
        return self.is_matched


    def match_baseline(self, patch_snapshot):
        """
        Apply patch baseline attributes to the package version to set the baseline matching status
        :param patch_snapshot: patch snapshot object which contains baseline attributes
        :return:
        """
        # Apply global filters: Always filter on non security updates because global filters does not have the flag.
        if match_aggregate_filter(self, patch_snapshot.product, patch_snapshot.global_filter):

            # Apply rejected patches list before applying rules and list
            # so that all rejected pkg versions won't be matched with any rules and list in the baseline
            if not match_package(patch_snapshot.rejected_patches, self.pkg_data):
                # Match global filter and not rejected patches, now apply approval rules and approved patches

                # Apply approval rules
                self.apply_approval_rules(patch_snapshot.product, patch_snapshot.approval_rules)

                # Apply approved patches list
                if match_package(patch_snapshot.approved_patches,  self.pkg_data):
                    self._set_match_status(patch_snapshot.approved_patches_enable_non_security,
                                           patch_snapshot.approved_patches_compliance_level)
        return self.is_matched


    def match_override_list(self, override_list):
        """
        Apply install override list to the package version to set the overridden status
        :param override_list: install override list to be matched
        :return:
        """
        # Override list matching does not care if it is security patch or not, it only cares about the package version
        # Override list can install rejected patches
        return match_package(override_list.all_filters, self.pkg_data)


    def mark_upgrade(self, upgradable_packages=None, patch_snapshot=None, override_list=None,
                     check_related_changes=False, from_user=True):
        """
        Mark the package version to be upgraded and this is mimic the following logic in the python wrapper:
        https://sources.debian.org/src/python-apt/1.7.0/apt/package.py/#L1491-L1501
        :param upgradable_packages: a list of upgradable packages
        :param patch_snapshot: patch snapshot
        :param override_list: override list
        :param check_related_changes: boolean to indicate whether to check related updates or not
        :param from_user: requested by user or not
        :return: True if successfully marked the package, otherwise False
        """
        if self.is_upgradable:
            auto = self.apt_package.is_auto_installed

            marked = self.mark_install(upgradable_packages, patch_snapshot, override_list, check_related_changes, from_user=from_user)

            if marked:
                if self.apt_package.marked_upgrade:
                    self.apt_package.mark_auto(auto)
                return True
            else:
                logger.warning("Package version %s is upgradable but failed to be marked upgrade", self.fullname)
                return False
        else:
            logger.error(("MarkUpgrade() called on a non-upgrable package version: '%s'") % self.fullname)
            return False


    def mark_install(self, upgradable_packages=None, patch_snapshot=None, override_list=None, check_related_changes=False,
                     auto_fix=True, auto_inst=True, from_user=True):
        """
        Mark the package version to be installed and this is mimic the following logic in the python wrapper:
        https://sources.debian.org/src/python-apt/1.7.0/apt/package.py/#L1466-L1489
        :param upgradable_packages: a list of upgradable packages
        :param patch_snapshot: patch snapshot
        :param override_list: override list
        :param check_related_changes: boolean to indicate whether to check related updates or not
            Please note when enable checking related changes, it will clear the cache to isolate the related changes
        :param auto_fix: automatically fix the broken packages or not
        :param auto_inst: automatically install new packages or not
        :param from_user: requested by user or not
        :return:
        """
        if not check_related_changes:
            changes = self._mark_install_without_check(upgradable_packages, auto_fix, auto_inst,
                                                       from_user, log_prefix='(Final)')
            return changes is not None and self.apt_package._pcache._depcache.broken_count <= 0

        pass_check, problems = self._mark_install_with_check(upgradable_packages, patch_snapshot, override_list,
                                                             auto_fix, auto_inst, from_user, log_changes=check_related_changes)

        if pass_check:
            return True
        elif problems:
            # Not pass check and exist some solvable problems -> try to solve them
            logger.info("Exist some potential resolvable problems to upgrade package %s from %s to %s, "
                        "try to adjust the candidates to solve them...", self.name, self.installed_version, self.version)
            return self._resolve_problems(problems, upgradable_packages, patch_snapshot, override_list, auto_fix, auto_inst, from_user)
        else:
            # Not pass check but the problems are empty -> exist some unresolvable problems -> Fail
            logger.warning("Exist some potential unresolvable problems to upgrade package %s from %s to %s",
                        self.name, self.installed_version, self.version)
            return False


    def _mark_install_without_check(self, upgradable_packages=None, auto_fix=True, auto_inst=True, from_user=True,
                                    clear_cache=False, required_changes=None, log_prefix=''):
        """
        Mark the package version to be installed and this is mimic the following logic in the python wrapper:
        https://sources.debian.org/src/python-apt/1.7.0/apt/package.py/#L1466-L1489
        :param upgradable_packages: a list of upgradable packages
        :param auto_fix: automatically fix the broken packages or not
        :param auto_inst: automatically install new packages or not
        :param from_user: requested by user or not
        :param clear_cache: boolean to indicate whether we need to clear cache before making changes or not
        :param required_changes: required candidate changes before marking
        :param log_prefix: logging prefix string, default is empty string. To disable logging, set it to None
        :return: tuple of pending changes or None if not exist
        """
        if clear_cache:
            self.apt_package._pcache.clear()
            # Set the candidates for all other pkgs if we cleared the cache
            # This will allow some special pkgs depending on the candidates' changes to be marked, e.g.
            # A is depending on B and C, without changing B and C's candidates, A will NEVER be marked
            # And we can't get information from apt cache by looking at pending changes.
            # This can't be resolved entirely until we have our own dependency resolution algorithm
            if upgradable_packages:
                for pkg in upgradable_packages: pkg.set_candidate()

        # Before marking the target package, adjust the candidate for required change
        # KNOWN ISSUE: there could be conflicts between required_changes and upgradable_packages' current candidate
        # if there are multiple versions approved for the same package
        required_changes = required_changes if required_changes else self.required_changes.values()
        for change in required_changes:
            change.set_candidate()

        self.apt_package.candidate = self.apt_package_version
        try:
            self.apt_package.mark_install(auto_fix, auto_inst, from_user)
        except Exception as e:
            logger.info("Error installing package: %s, due to Exception: %s", self.name, str(e))
        if self.apt_package.marked_install or self.apt_package.marked_upgrade:
            changes = get_pending_changes(self.apt_package._pcache)
            if log_prefix is not None:
                final_log_prefix = log_prefix + ' ' if log_prefix else log_prefix
                logger.info(final_log_prefix + "Upgrading package %s from %s to %s will do the following changes: \n %s",
                            self.name, self.installed_version, self.version, format_pending_changes(changes))
            return changes
        else:
            # A special case that some pkgs can't be marked to upgrade/install if there exists a newer version
            # or it must be upgraded as part of required dependency of another package
            logger.warning("Unable to mark upgrade package %s from %s to %s. Maybe there is another latest version "
                           "or it needs to be upgraded as part of required dependency of another package.",
                           self.name, self.installed_version, self.version)


    def _mark_install_with_check(self, upgradable_packages=None, patch_snapshot=None, override_list=None,
                                 auto_fix=True, auto_inst=True, from_user=True,
                                 required_changes=None, log_changes=False):
        """
        Mark the package version to be installed with checking related changes
        :param upgradable_packages: a list of upgradable packages
        :param patch_snapshot: patch snapshot
        :param override_list: override list
        :param auto_fix: automatically fix the broken packages or not
        :param auto_inst: automatically install new packages or not
        :param from_user: requested by user or not
        :param required_changes: required candidate changes before marking
        :param log_changes: boolean to indicate whether we log the changes or not
        :return: True if pass check, otherwise False
        """
        # First mark pkg to install without auto fix
        changes_before_fix = self._mark_install_without_check(upgradable_packages, auto_fix=False,
                                                              auto_inst=auto_inst, from_user=from_user,
                                                              clear_cache=True, required_changes=required_changes,
                                                              log_prefix='(Before fix)' if log_changes else None)

        changes_after_fix = None
        if auto_fix and self.apt_package._pcache._depcache.broken_count > 0:
            # Then, mark pkg to install with auto fix
            changes_after_fix = self._mark_install_without_check(upgradable_packages, auto_fix=True,
                                                                 auto_inst=auto_inst, from_user=from_user,
                                                                 clear_cache=True, required_changes=required_changes,
                                                                 log_prefix='(After fix)' if log_changes else None)

        # Last, compare changes before and after fix
        pass_check, problems = check_pending_changes(self, changes_before_fix, changes_after_fix,
                                                     patch_snapshot, override_list, auto_inst)
        # Clear cache to remain clean start (checking ONLY)
        self.apt_package._pcache.clear()

        return pass_check, problems


    def _resolve_problems(self, problems, upgradable_packages=None, patch_snapshot=None, override_list=None,
                         auto_fix=True, auto_inst=True, from_user=True):
        """
        Try to resolve all problems by adjusting the problem packages' candidates
        :param problems: a map of the current problems
        :param upgradable_packages: a list of upgradable packages
        :param patch_snapshot: patch snapshot
        :param override_list: override list
        :param auto_fix: automatically fix the broken packages or not
        :param auto_inst: automatically install new packages or not
        :param from_user: requested by user or not
        :return:
        """
        failed_pkgs = []
        for pkg_name in list(problems):
            change = problems.get(pkg_name)
            # Before try to resolve, check if the problem still exists
            if not change or not change.problem:
                logger.info("Problem for package %s to upgrade package %s from %s to %s is already resolved by "
                            "other packages.", pkg_name, self.name, self.installed_version, self.version)
                continue

            if not self._try_to_resolve_problem(pkg_name, problems, upgradable_packages, patch_snapshot, override_list,
                                                auto_fix, auto_inst, from_user):
                # Exist package changes failed all versions, not able to resolve it
                failed_pkgs.append(pkg_name)

        if failed_pkgs:
            logger.warning("Failed to try to resolve the problem(s) for package(s) %s to upgrade package %s from "
                           "%s to %s", failed_pkgs, self.name, self.installed_version, self.version)
            return False

        logger.info("Resolved all problems to upgrade package %s from %s to %s",
                    self.name, self.installed_version, self.version)
        return True


    def _try_to_resolve_problem(self, pkg_name, problems, upgradable_packages=None, patch_snapshot=None,
                                override_list=None, auto_fix=True, auto_inst=True, from_user=True):
        """
        Try to resolve the given pkg's problem by adjusting its candidates
        :param pkg_name: problem pkg name to be resolved
        :param problems: a map of the current problems
        :param upgradable_packages: a list of upgradable packages
        :param patch_snapshot: patch snapshot
        :param override_list: override list
        :param auto_fix: automatically fix the broken packages or not
        :param auto_inst: automatically install new packages or not
        :param from_user: requested by user or not
        :return: True if able to find another version to resolve the problem, otherwise, False
        """
        change = problems.get(pkg_name)
        other_changes = list(self.required_changes.values())
        possible_versions = change.get_other_applicable_versions()

        for version in possible_versions:
            # Try to solve problem by changing the candidate version
            change.candidate_version = version
            pass_check, problems_after_adjust = self._mark_install_with_check(
                upgradable_packages, patch_snapshot, override_list,
                auto_fix, auto_inst, from_user, required_changes=other_changes + [change])
            new_problems = [prob for prob in problems_after_adjust if prob not in problems]

            # Problem solved for the targeted package when either 1) passed the check for all packages or
            # 2) still exist some problems but the targeted package is no longer a problem, and there also exists
            #  one constraint that the new candidate version should not introduce any new problems
            if pass_check or (problems_after_adjust and pkg_name not in problems_after_adjust and not bool(new_problems)):
                logger.info("Resolved package %s by adjusting its candidate to be %s",
                            pkg_name, change.candidate_version.version)
                change.set_problem(None)
                self.required_changes[pkg_name] = change
                self._adjust_problems(problems, problems_after_adjust)
                return True

        # Exist package changes failed all versions, not able to resolve it
        versions = [ pkg_ver.version for pkg_ver in possible_versions ]
        logger.warning("Can't resolve the problem for package %s with versions %s to upgrade package %s from "
                       "%s to %s", pkg_name, versions, self.name, self.installed_version, self.version)
        return False

    @staticmethod
    def _adjust_problems(old_problems, new_problems):
        """
        Reset the old problems to be None if the problem does not exist any more in the new problems
        :param old_problems: old problems before adjusting candidates
        :param new_problems: new problem after adjusting candidates
        :return:
        """
        for pkg in list(old_problems):
            if pkg not in new_problems:
                old_problems.get(pkg).set_problem(None)

# Origin is an object, for Ubuntul, an origin looks like:
# <Origin component:'universe' archive:'bionic-security' origin:'Ubuntu'
#  label:'Ubuntu' site:'security.ubuntu.com' trusted:True>
# For DEBIAN, an origin component looks like:
# <Origin component:'main' archive:'oldstable' origin:'Debian'
#  label:'Debian-Security' site:'security.debian.org' trusted:True>
# For Ubuntu, we identify if a patch is security patch by checking the origin object's
#  archive value, if it is bionic-security, xenial-security, trusty-security, then it is security patch,
#  the origin's label value is always Ubuntu.
# For DEBIAN, the origin object's site value is used to identify if a patch is security patch,
#  if the site is 'security.debian.org', then the patch is security patch, the archive value is not valuable
#  in determinging security patches for Debian. The label value is also prone to change.
def is_security_version(pkg_version):
    """
    Method to check whether provided pkg version is a security version or not

    :param pkg_version: package version from apt
    :return: True if any origins is security for the pkg version, False otherwise
    """
    for origin in pkg_version.origins:
        if (FILTER_VALUE_SECURITY in origin.archive.lower() and origin.trusted) or \
            (DEBIAN_SECURITY_SITE in origin.site.lower() and origin.trusted):
            return True
    return False


def match_aggregate_filter(pkg_version, product, aggregate_filter):
    """
    Check whether pkg version is approved by the aggregate filter or not

    :param pkg_version: package version to be checked
    :param aggregate_filter: aggregate filter to be used for checking
    :return: True if pkg version is approved by the filter, False otherwise
    """
    # Check the product
    if FILTER_KEY_PRODUCT in aggregate_filter:
        if product.lower() not in aggregate_filter[FILTER_KEY_PRODUCT] \
                and FILTER_VALUE_WILDCARDS not in aggregate_filter[FILTER_KEY_PRODUCT]:
            return False

    # Check the priority and section
    if FILTER_KEY_PRIORITY in aggregate_filter:
        if pkg_version.priority not in aggregate_filter[FILTER_KEY_PRIORITY] \
                and FILTER_VALUE_WILDCARDS not in aggregate_filter[FILTER_KEY_PRIORITY]:
            return False

    if FILTER_KEY_SECTION in aggregate_filter:
        if pkg_version.section not in aggregate_filter[FILTER_KEY_SECTION] \
                and FILTER_VALUE_WILDCARDS not in aggregate_filter[FILTER_KEY_SECTION]:
            return False

    return True


def get_package_versions(package, security_only=False):
    """
    Get all versions that can be upgraded or installed for an apt pkg
    :param package: apt package
    :param security_only: boolean to indicate whether to only include security versions or not
    :return: a sorted (from latest to oldest) list of versions
    """
    # Default to all available versions
    apt_pkg_versions = package.versions

    if package.is_installed:
        # if package installed, only look at the higher or installed versions
        pkg_versions = [PackageVersion(package, pkg_ver) for pkg_ver in apt_pkg_versions
                        if pkg_ver._cmp(package.installed) >= 0]
    else:
        # For package not installed, look at all versions
        pkg_versions = [PackageVersion(package, pkg_ver) for pkg_ver in apt_pkg_versions]

    if security_only:
        pkg_versions = get_security_package_versions(pkg_versions)

    return sorted(pkg_versions, key=lambda x: x.version, reverse=True)


def get_security_package_versions(pkg_versions):
    """
    Filter out all security versions from a list of available versions
    :param pkg_versions: provided versions to be filtered on
    :return: a list of security pkg versions
    """
    return [ pkg_ver for pkg_ver in pkg_versions if pkg_ver.is_security ]
