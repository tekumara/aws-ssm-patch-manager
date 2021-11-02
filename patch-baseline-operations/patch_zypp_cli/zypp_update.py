#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
from patch_zypp_cli import zypp_report
from cli_wrapper.zypper_cli import ZypperCLI
from cli_wrapper.ZYpp import ZYpp
from patch_common.constant_repository import ExitCodes
from patch_common.constant_repository import OperationType
from patch_common import package_matcher
from patch_common import package_inventory
from patch_common.metrics_service import append_runtime_metric_traceback
from patch_common.metrics_service import append_runtime_metric_file_info

import sys
import logging

logger = logging.getLogger()

def zypp_update(ZYpp_base, baseline, inventory, override_list = None):
    """
    Method for executing a ZYpp update commands.
    :param ZYpp_base - ZYpp(ZypperCLI())
    :param baseline is a ZyppBaseline object from zypp_baseline.
    :param inventory is PackageInventory object result of scan.
    :param override_list is the contents of the install override list provided by customer.
    """
    try:
        zb = ZYpp_base
        locked_packages = []
        if override_list:
            return override_list_update(zb, baseline, override_list)
        else:
            logger.info("Running scan operation to find missing packages...")
            logger.info("Found %s missing packages."%(len(inventory.missing_pkgs)))

            # get list of packages locked by us.
            locked_packages = __lock_rejected_packages(zb, baseline, inventory.installed_rejected_pkgs)

            # run the install.
            result = regular_install(zb, baseline, inventory, override_list)

            # unlock the rejected packages that we locked.
            __unlock_rejected_packages(zb, locked_packages)

            return result

    except Exception as e:
        logger.exception("Unable to run install operation %s", e)
        __unlock_rejected_packages(zb, locked_packages)
        append_runtime_metric_traceback()
    finally:
        pass

def regular_install(zb, baseline, inventory, override_list = None):
    """
    Method for completing a regular (non - install - override list) update / install.
    :param zb is the ZYpp base
    :param baseline is the baselin.py object from the common package.
    :param inventory is a package_inventory.py result form a "scan" operation.
    :param override_list is the override_list.py form the common package.
    :returns (ExitCode, Inventory)
    """

    # Attempt install / commit.
    logger.info("Updating missing packages...")
    commit_result = zb.commit(inventory.missing_pkgs)
    logger.info("Output from commit: \n%s \n", commit_result[0])

    # Do not reboot if there are no missing packages
    if not (inventory.missing_pkgs):
        logger.info("No missing packages detected.")
        inventory.operation_type = OperationType.INSTALL
        return (ExitCodes.SUCCESS, inventory)
    elif commit_result and commit_result[1] == 4:
        inventory = zypp_report.zypp_report(zb, baseline, OperationType.INSTALL, override_list)
        logger.exception("Commit subprocess had dependency check issues. Exit Code: %s \n Aborting."%(commit_result[1]))
        append_runtime_metric_file_info("Commit subprocess had dependency check issues. Exit Code: %s \n Aborting."%(commit_result[1]))
        return (ExitCodes.DEPENDENCY_CHECK_FAILURE, inventory)
    elif commit_result and commit_result[1] != 0:
        logger.exception("Commit subprocess was not successful. Exit Code: %s \n Aborting."%(commit_result[1]))
        append_runtime_metric_file_info("Commit subprocess was not successful. Exit Code: %s \n Aborting."%(commit_result[1]))
        return (ExitCodes.FAILURE, None)
    else:
        logger.info("Re-running scan operation.")
        inventory = zypp_report.zypp_report(zb, baseline, OperationType.INSTALL, override_list)
        return (ExitCodes.REBOOT, inventory)

def override_list_update(zb, baseline, override_list = None):
    """
    Method for completing an override list updates.
    :param zb is the ZYpp base.
    :param baseline is the baseline.py object from the common package.
    :param override_list.py is an override_list object from the common package.
    :return tuple of (ExitCode, PackageInventory)
    """
    logger.info("Installing with override list %s"%(override_list))

    all_packages = zb.get_all_installed_packages()

    all_packages_matching_override_list = __get_packages_matching_override_list(all_packages, override_list)
    logger.info("Found %s packages from override_list list."%(len(all_packages_matching_override_list)))

    packages_to_commit = __get_only_installed_packages_needing_update(all_packages_matching_override_list)

    logger.info("Of those, %s are not installed and need an update."%(len(packages_to_commit)))
    commit_result = zb.commit(packages_to_commit)

    if commit_result[1] != 0:
        logger.error("Commit subprocess was not successful. Exit Code: %s \n Commit unsuccessful. Aborting."%(commit_result[1]))
        append_runtime_metric_file_info("Commit subprocess was not successful. Exit Code: %s \nCommit unsuccessful. Aborting."%(commit_result[1]))
        return (ExitCodes.FAILURE, None)

    logger.info("Install complete. Refreshing package list.")
    all_packages = zb.get_all_installed_packages()

    logger.info("Setting if currently installed package versions match override_list versions.")
    all_packages = __set_if_current_version_matches_override_list(all_packages, all_packages_matching_override_list)

    logger.info("Categorizing packages.")
    (missing, failed, installed, installed_rejected, installed_other, not_applicable) =\
    baseline.categorize_override_list_install(all_packages)

    return (ExitCodes.REBOOT, package_inventory.PackageInventory(
        operation_type= OperationType.INSTALL,
        pkg_type='zypp',
        installed_pkgs = installed if installed else [],
        installed_other_pkgs = installed_other if installed_other else [],
        not_applicable_pkgs = not_applicable if not_applicable else [],
        missing_pkgs = missing if missing else [],
        installed_rejected_pkgs = installed_rejected,
        failed_pkgs = failed,
        override_list = override_list
    ))

def __unlock_rejected_packages(zb, locked_packages):
    """
    Method for unlocking a list list of packages via the cli.
    :param zb is the zypp base with all zypp cli commands.
    :param locked-packages should be a list of package names List<String>
    and should not contain packages the customer locked.
    """
    if locked_packages and len(locked_packages) > 0:
        zb.remove_locks(locked_packages)


def __lock_rejected_packages(zb, baseline, install_rejected_packages):
    """
    Method for placing a package lock on rejected patches when the rejected patches action is checked.
    :param zb is the zypp base with all zypp cli commands.
    :param baseline is the patch baseline as a baseline.py object from the common package.
    :param install_rejected_patches is a list of compliances packages from package_inventory.
    :return List<string> of package names locked.
    """
    # get all uninstalled packages to lock
    all_uninstalled_packages = zb.get_all_uninstalled_packages()

    # Get currently existing locks so we don't add to them and
    # accidentally remove customer locks.
    locks =  zb.get_all_locks()
    locked_packages = [package.name for package in locks]

    # add all uninstalled packages that are not already locked and in the baseline.
    packages_to_lock = []
    for package in all_uninstalled_packages:
        if not package.name in locked_packages:
            if baseline.match_exclude_patterns(package) \
            and not package.name in packages_to_lock:
                packages_to_lock.append(package.name)

    # add all install rejected packages that are not already locked so we don't inadvertently upgrade them.
    for package in install_rejected_packages:
        if not package.name in locked_packages \
        and not package.name in packages_to_lock:
            packages_to_lock.append(package.name)

    if packages_to_lock:
        zb.add_locks(packages_to_lock)
        logger.info("Packages locked.")

    return packages_to_lock

def __get_only_installed_packages_needing_update(all_packages_matching_override_list):
    """
    Method for filtering out non-installed package versions.
    :param all_packages_matching_override_list.
    :return list of CLIPackageBeans to commit.
    """
    packages_to_commit = []
    for package in all_packages_matching_override_list:
        if package.installed == True and package.update_available:
            packages_to_commit.append(package)
    return packages_to_commit

def __get_packages_matching_override_list(all_packages, override_list):
    """
    Method for getting the list of all packages that match the install override list.
    :param - all_packages is a (name, arch) => [CLIPackageBean, ...] where there is a CLIPackageBean for every combination of Classification & Severity
    from patches and package version.
    :param 0 override list is the common package install_override_list.py class.
    :returns List[CLIPackageBean]
    """
    try:
        packages_to_upgrade = []
        # for every (name, arch)
        for na in all_packages:
            potential_upgrade = __get_version_matching_override_list(all_packages[na], override_list)
            if potential_upgrade:
                packages_to_upgrade.append(potential_upgrade)
        return packages_to_upgrade
    except Exception as e:
        logger.exception("Caught exception in zypp_update.py while getting packages that match the override list. %s", e)

def __get_version_matching_override_list(package_versions, override_list):
    """
    Method for getting the highest version of a package that matches override_list (if regex, else exact match)
    :param package_versions is a list of CLIPackageBeans of all versions and classification / severity combos
    of a package.
    :param override_list - is the override list of the package.
    :returns a potential upgrade as a CLIPackageBean else None.
    """
    potential_upgrade = None
    # Loop through every package combo for that (name, arch)
    for package in package_versions:
    # if the name and arch match the override list. # This is repetition but it's the most readable way to do this.
        if __match_package(override_list.id_filters, package):
            # Check if the available_version and release match as well.
            if __match_package(override_list.all_filters, package):
                    if not potential_upgrade:
                        potential_upgrade = package
                    elif potential_upgrade.compare_version(package.available_edition) == -1:
                        potential_upgrade = package

    return potential_upgrade

def __set_if_current_version_matches_override_list(all_packages = {}, packages_upgraded = []):
    """
    Method for setting the update_available and matches_override_listattributes on packages that match the override list.
    :param all_packages is a (name, arch) => [CLIPackageBeanA, CLIPackageBeanB, etc...] of packages that are installed. The value is a list
    because it contains a new CLIPackageBean for every combination of package edition and classification & severity for the different package editions that were found.
    :param packages_upgraded is a List of [CLIPackageBean] of all of the packages that were attempted to upgrade via the install override list.
    :returns all_packages with update_available and matches_override_list attributes set.
    """
    try:
        for package in packages_upgraded:
            if (package.name, package.arch) in all_packages:
                for potential_override_package in all_packages[(package.name, package.arch)]:
                    # if it is the same version as the package and the packages is marked as installed.
                    if potential_override_package.compare_version(package.available_edition) == 0:
                        potential_override_package.update_available = potential_override_package.installed == False # if this version is not installed, an update is available.
                        potential_override_package.matches_install_override_list = True

        return all_packages

    except Exception as e:
        logger.exception("Caught exception in zypp_update.py while setting packages that match the override list for reporting purposes. %s", e)

def __match_package(regexes, package):
        """
        :param regexes: list of regex for matching
        :param package: is the package to check is matching.
        :return: True to matches, False otherwise
        """
        pkg_tup = (package.name, package.arch, package.epoch, package.version, package.release)
        result = package_matcher.match_package(regexes, package_matcher.generate_package_data(pkg_tup), None)
        return result
