# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
from patch_common.constant_repository import ExitCodes, OperationType
from patch_common.metrics_service import append_runtime_metric_traceback
from patch_dnf import dnf_report
import logging
import sys

logger = logging.getLogger()


def perform_update(dnf, package_inventory_before_install, baseline, override_list=None):
    """
    perform install operation using the DNF CLI
    :param dnf: DNF object
    :param package_inventory_before_install: PackageInventory object from before install occurs
    :param baseline: DnfBaseline object
    :param override_list: InstallOverrideList object
    :return ExitCodes.TYPE, PackageInventory object from after install occurs
    """
    # missing_pkgs become failed_pkgs in PackageInventory for "install" operation
    # (if override list is empty, failed_pkgs contains "missing patches" else it contains "override list")
    if len(package_inventory_before_install.failed_pkgs) > 0:
        # Retry installation once if any packages fail to install
        return _install_with_retry(dnf, package_inventory_before_install, baseline, override_list, num_retries=2)
    else:
        logger.info("Nothing to install. Ending process...")
        return ExitCodes.SUCCESS, package_inventory_before_install


def _install_with_retry(dnf, pkg_inventory, baseline, override_list, num_retries):
    """
    Perform install operation with retry logic if packages fail to install
    In testing many packages have been found to override/conflict with one another. Implementing retry logic
    allows for an easier customer experience and allows us to more effective log packages that are related to these conflicts
    :param dnf: DNF object
    :param pkg_inventory: PackageInventory object from before install occurs
    :param baseline: DnfBaseline object
    :param override_list: InstallOverrideList object
    :param num_retries: number of retries to perform on install operation
    :return ExitCodes.TYPE, PackageInventory object from after install occurs
    """
    exit_code = ExitCodes.FAILURE
    pkgs_to_install = pkg_inventory.failed_pkgs
    debug_logs_enabled = False

    for i in range(num_retries):
        try:
            if i > 0:
                debug_logs_enabled = True
                logger.info("Retrying Install for Packages: {}".format([pkg.taxonomy for pkg in pkgs_to_install]))

            dnf.install_packages(pkgs_to_install, debug_logs_enabled)
            exit_code = ExitCodes.REBOOT
        except Exception as e:
            append_runtime_metric_traceback()
            logger.exception("Installation process has failed.")

        pkg_inventory = dnf_report.generate_report(dnf, baseline, OperationType.INSTALL, override_list)
        pkgs_to_install = pkg_inventory.failed_pkgs
        if len(pkgs_to_install) == 0:
            break

    return exit_code, pkg_inventory
