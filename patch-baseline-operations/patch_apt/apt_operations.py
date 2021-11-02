# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import os

import apt

from patch_apt.context_os_nice import os_nice
from patch_apt.apt_update import apt_update
from patch_apt.apt_report import apt_report

from patch_common.install_override_list import InstallOverrideList
from patch_common.constant_repository import OperationType, ExitCodes
from patch_common.package_compliance import get_packages_installed_on_current_run
from patch_common.metrics_service import append_runtime_metric_file_info

class AptOperations:
    """
    Class to perform interactions with APT.
    """
    def __init__(self):
        """
        Constructor for the AptOperations class.
        """
        pass

    def execute_patch_operation(self, patch_snapshot):
        """
        Executes the patching operation based on the snapshot.
        :param patch_snapshot: to execute the patching operation
        :return: exit code, package inventory class.
                 The exit code is of the patching operation can be success, failure, reboot
                 The package inventory class is the result of the operation containing the
                 installed, missing, failed, not applicable packages.
        """
        operation_type = patch_snapshot.operation

        # It is preferable to lock the APT package system before we access it.
        # But this is currently not functioning properly. Will debug later.
        # with apt_pkg.SystemLock():
        # get a cache
        cache = apt.Cache()

        # TODO: Find appropriate public method and output the broken packages.
        if cache._depcache.broken_count > 0:
            logging.error("APT cache has broken packages, exiting")
            append_runtime_metric_file_info("APT cache has broken packages, exiting")
            return ExitCodes.FAILURE, None

        with os_nice():

            # Before scanning the pkgs for install operation, we will need to load install override list if provided
            override_list = InstallOverrideList.load(patch_snapshot)
            if operation_type.lower() == OperationType.SCAN.lower():
                package_inventory = apt_report(cache, patch_snapshot, override_list)
                if package_inventory is None:
                    append_runtime_metric_file_info("Inventory is None")
                    exit_code = ExitCodes.FAILURE
                else:
                    exit_code = ExitCodes.SUCCESS

            elif operation_type.lower() == OperationType.INSTALL.lower():
                package_inventory_before_install = apt_report(cache, patch_snapshot, override_list)
                exit_code = apt_update(cache, patch_snapshot, override_list)

                package_inventory = apt_report(cache, patch_snapshot, override_list)

                package_inventory.current_installed_pkgs = list(get_packages_installed_on_current_run(
                    package_inventory_before_install.installed_pkgs + package_inventory_before_install.installed_other_pkgs + package_inventory_before_install.installed_rejected_pkgs,
                    package_inventory.installed_pkgs + package_inventory.installed_other_pkgs + package_inventory.installed_rejected_pkgs,
                ))
            else:
                raise Exception("Unknown operation: %s" % (operation_type))
            # This exits success, failure, or reboot depending on the exit code from YUM.
            return (exit_code, package_inventory)

    @staticmethod
    def clean_retrieved_packages():
        """
        Cleans the retrieved packages from the cache using: apt-get clean
        :return: None
        """
        # cleans the cache of retrieved package files.
        logging.info("Calling apt-get clean to clean retrieved package files.")
        os.system("apt-get clean")

    def refresh_cache(self):
        """
        Cleans and updates the cache after default repositories are restored.
        :return: None
        """
        self.clean_retrieved_packages()

        # updates the repositories package metadata
        logging.info("Calling APT update to retrieve package metadata locations.")
        cache = apt.Cache()
        cache.update(fetch_progress=apt.progress.text.AcquireProgress())
        cache.close()
