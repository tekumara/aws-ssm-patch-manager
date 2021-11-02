# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import apt
import apt_pkg
import logging
import os

from patch_apt.package import Package
from patch_apt.baseline_operations import apply_patch_baseline, apply_override_list, upgradables_sanity_check
from patch_common.constant_repository import ExitCodes, OperationType
from patch_common import reboot_controller
from patch_common.metrics_service import append_runtime_metric_file_info

logger = logging.getLogger()


def apt_update(cache, patch_snapshot, override_list=None):
    """
    Perform install operations according to given baseline or override list
    :param cache: apt cache to get all pkg information
    :param patch_snapshot: patch snapshot, which contains baseline to filter pkgs
    :param override_list: optional override list to override installation decisions from baseline
    :return: installation exit code
    """
    # Update and open a new cache to get updated pkg installation or upgradable status
    cache.update(fetch_progress=apt.progress.text.AcquireProgress())
    cache.open()
    packages = (Package(apt_package) for apt_package in cache)

    if override_list:
        missing_updates = apply_override_list(packages, override_list)
    else:
        # Get all pkg status but only missing updates will be used
        installed_updates, installed_other, installed_rejected, missing_updates, not_applicable_packages = \
            apply_patch_baseline(packages, patch_snapshot)
    logger.info("After applying filters, missing count: %i failed count: 0", len(missing_updates))

    # Before perform the install action, do the sanity check to see if it is okay to upgrade those missing updates
    missing_updates, failed_packages = upgradables_sanity_check(missing_updates, patch_snapshot, override_list)
    logger.info("After applying sanity check, missing count: %i failed count: %i", len(missing_updates), len(failed_packages))
    if len(failed_packages) == 0:
        exit_code = ExitCodes.SUCCESS
    else:
        exit_code = ExitCodes.DEPENDENCY_CHECK_FAILURE

    if len(missing_updates) == 0:
        logger.info("No packages found that can be upgraded.")
        return ExitCodes.SUCCESS
    else:
        missing_updates.sort(key=lambda p: p.fullname)
        pkgs = " ".join([pkg.fullname for pkg in missing_updates])
        logger.info("Packages that look like they should be upgraded: %s", pkgs)

        missing_updates = _mark_upgrade(cache, missing_updates, failed_packages)
        logger.info("After adding upgrades to cache, missing count: %i failed count: %i", len(missing_updates), len(failed_packages))


        if len(missing_updates) != 0:
            if not _before_upgrade(cache):
                append_runtime_metric_file_info("There are %s missing packages"%len(missing_updates))
                return ExitCodes.FAILURE

            # do the install based on list of missing packages
            pkgs = " ".join([pkg.fullname for pkg in missing_updates])
            logger.info("Packages that will be upgraded: %s", pkgs)

            # Hold your breath, we're doing the upgrade now
            result, install_failed_pkgnames = _upgrade(cache)
            failed_packages = failed_packages + [cache[pkgname] for pkgname in install_failed_pkgnames]

            if not result:
                logger.error("Upgrade failed.")
                append_runtime_metric_file_info("Upgrade failed")
                return ExitCodes.FAILURE

            # Perform a sanity check
            for pkg in failed_packages:
                if not pkg.is_upgradable:
                    logger.warning("%s failed to install but it is not upgradable anymore."
                                   "Maybe this package was a required dependency?", pkg.name)

            if exit_code == ExitCodes.DEPENDENCY_CHECK_FAILURE:
                append_runtime_metric_file_info("There are %s failed packages"%len(failed_packages))
                return ExitCodes.REBOOT_WITH_DEPENDENCY_CHECK_FAILURE
            else:
                return ExitCodes.REBOOT



    return exit_code


def _mark_upgrade(cache, missing_updates, failed_packages):
    """
    Mark missing updates to be upgraded
    :param cache: apt cache
    :param missing_updates: a list of missing updates that needs to be marked upgrade
    :param failed_packages: a list of failed packages to append pkgs that are failed to be marked to upgrade
    :return: a list of pkgs that can be successfully marked to upgrade
    """
    # now mark for upgrade
    logger.info("Beginning marking upgrade process.")
    # These packages will be marked for upgrade
    upgrade_pkgs = []

    # speed things by using ActionGroup
    with cache.actiongroup():
        for pkg in missing_updates:
            # Before each marking, reset the candidates for all other pkgs in case they are cleared when rewinding
            for other_pkg in missing_updates: other_pkg.set_candidate()

            if not pkg.is_upgradable:
                logger.error("%s exists in missing_updates packages but is not upgradable!", pkg.name)
                append_runtime_metric_file_info("%s exists in missing_updates packages but is not upgradable!"%pkg.name)
                return ExitCodes.FAILURE 
            try:
                logger.info("Package name: %s, arch: %s, version: %s, is to be updated.",
                            pkg.name, pkg.architecture, pkg.version)
                pkg.mark_upgrade()

                if pkg.marked_upgrade:
                    upgrade_pkgs.append(pkg)
                else:
                    # This fails without reason in the APT code.
                    logger.error("Package %s failed to be marked for upgrade.", pkg.name)
                    failed_packages.append(pkg)
            except SystemError as e:
                logger.warning("Package %s is upgradable but failed to be marked for upgrade (%s)."
                               " Please try again.", pkg.name, e)
                # When mark_upgrade() throws an exception, the package will often be left in a state where
                # pkg.marked_upgraded returns True. This will cause an exception when we try to commit our
                # changes. To prevent this we must rewind the cache to the point before we tried to
                # mark this package for upgrade.
                _rewind_cache(upgrade_pkgs, cache)
                failed_packages.append(pkg)
    return upgrade_pkgs


def _before_upgrade(cache):
    """
    Perform a list of preparations before commit to upgrade
    :param cache: apt cache
    :return: True if successfully done all preparations, False otherwise
    """
    # download what looks good
    logger.info("Fetching archives for selected packages...")
    try:
        cache.fetch_archives(apt.progress.text.AcquireProgress())
    except SystemError as e:
        logger.error("fetch_archives() failed: '%s'", e)
        return False

    # If DPkg options are not set then we set the --force-confdef --force-confold to prevent conffile prompts
    # --force-confdef: ask dpkg to decide alone when it can and prompt otherwise.
    # --force-confold: do not modify the current configuration file, the new version is installed with a
    #                  .dpkg-dist suffix.
    if not "DPkg::Options" in apt_pkg.config:
        apt_pkg.config.set("DPkg::Options::", "--force-confdef")
        apt_pkg.config.set("DPkg::Options::", "--force-confold")
    return True


def _rewind_cache(upgrade_pkgs, cache):
    """
    Rewind the cache to a point where all packages in upgrade_pkgs  are
    successfully marked for upgrade.
    :param upgrade_pkgs: List of packages to mark for upgrade. These packages
      MUST succeed the mark_upgrade() call as we catch no exceptions here.
    :param cache: The cache.
    """
    cache.clear()
    for pkg in upgrade_pkgs:
        pkg.mark_upgrade()


def _upgrade(cache):
    """
    Perform apt cache commit operation and return its corresponding result
    :param cache: apt cache to perform action
    :return: result and failed pkgs after committed cache
    """
    result, error, failed_pkgs = _cache_commit(cache)
    if result:
        logger.info("All upgrades installed")
    else:
        logger.error("Installing some upgrades failed! %s", failed_pkgs)
        logger.error("Error message: '%s'", error)
    return result, failed_pkgs


def _cache_commit(cache):
    """
    Commit the changes from the given cache to the system
    :param cache: apt cache to perform action
    :return:
    """
    # set debconf to NON_INTERACTIVE, redirect output
    os.putenv("DEBIAN_FRONTEND", "noninteractive")

    # only act if there is anything to do (important to avoid writing
    # empty log stanzas)
    if len(cache.get_changes()) == 0:
        return True, None, []

    error = None
    res = False
    install_progress = InstallProgress()

    try:
        res = cache.commit(install_progress=install_progress)
    except SystemError as e:
        error = e
        logger.exception("Exception occurred during upgrade: %s", e)
    return res, error, install_progress.failed_pkgs


class InstallProgress(apt.progress.base.InstallProgress):
    """
    Use this class to register callbacks during package installation.
    """

    def __init__(self):
        self.failed_pkgs = []
        apt.progress.base.InstallProgress.__init__(self)

    def error(self, pkg, errormsg):
        """
        Receives callbacks for package installation errors.
        :param pkg: that had an error.
        :param errormsg: of the installation.
        :return: None
        """
        logger.error("Package %s failed to install: %s", pkg, errormsg)
        self.failed_pkgs.append(pkg)
