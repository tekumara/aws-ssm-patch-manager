# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import apt

from patch_apt.package import Package
# from patch_apt import inventory_operations
from patch_apt.baseline_operations import apply_patch_baseline, apply_override_list, find_final_missing_pkgs

from patch_common.constant_repository import OperationType
from patch_common.package_inventory import PackageInventory

logger = logging.getLogger()

def apt_report(cache, patch_snapshot, override_list=None):
    """
    Perform scan operations according to given baseline or override list
    :param cache: apt cache to get all pkg information
    :param patch_snapshot: patch snapshot, which contains baseline to filter pkgs
    :param override_list: optional override list to override installation decisions from baseline
    :return: package inventory
    """
    # Update and open a new cache to get updated pkg installation or upgradable status
    # This will close the old cache if exists any by default and re-open it
    logger.info("Re-synchronizing the package index files from their sources.")
    cache.update(fetch_progress=apt.progress.text.AcquireProgress())
    cache.open()

    # The missing, installed installed_other and installed_rejected could be different after installation
    # if override list used or dependencies installed or upgraded
    installed_updates, installed_other, installed_rejected, missing_updates, not_applicable_packages = \
        apply_patch_baseline((Package(apt_package) for apt_package in cache), patch_snapshot)

    failed_packages = []
    if patch_snapshot.operation.lower() == OperationType.INSTALL.lower():
        if override_list:
            # If exists override list, we will only install packages from it, and report is called after installation
            # but if still existing missing updates from override list during report -> failed packages
            failed_packages = apply_override_list((Package(apt_package) for apt_package in cache), override_list)
            # Now, find the final missing packages
            # Any pkg in the missing updates but not failed, will still be missing
            missing_updates = find_final_missing_pkgs(missing_updates, failed_packages)

        else:
            # If no override list used for install operation, we should install all missing updates
            # if not, they are failed packages
            failed_packages = missing_updates
            missing_updates = []

    logger.info(
        "Installed count: %i Installed other count: %i Installed rejected count: %i "
        "Missing count: %i Not Applicable count: %i Failed count: %i",
        len(installed_updates), len(installed_other), len(installed_rejected),
        len(missing_updates), len(not_applicable_packages), len(failed_packages)
    )

    cache.close()
    return PackageInventory(operation_type=patch_snapshot.operation,
                             pkg_type="apt",
                             installed_pkgs=installed_updates,
                             installed_other_pkgs=installed_other,
                             installed_rejected_pkgs=installed_rejected,
                             missing_pkgs=missing_updates,
                             not_applicable_pkgs=not_applicable_packages,
                             failed_pkgs=failed_packages,
                             override_list=override_list)