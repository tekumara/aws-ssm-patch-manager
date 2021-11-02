# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
from patch_dnf import dnf_report
from patch_dnf import dnf_update
from patch_dnf.dnf import DNF
from patch_common.constant_repository import ExitCodes, OperationType
from patch_common.package_compliance import get_packages_installed_on_current_run
from patch_common.metrics_service import append_runtime_metric_file_info
from patch_common.constant_repository import Metrics

logger = logging.getLogger()

def dnf_main(baseline, operation_type, override_list=None):
    """
    Starting point for the scan or install operation.

    :param baseline: baseline object
    :param operation_type: can be either "scan" or "install"
    :param override_list: a list of patches to override installation decisions
    :return: (exit_code, package inventory) see patch_common.constant_repository.ExitCodes
    """
    dnf = DNF()
    package_inventory = None

    if operation_type.lower() == OperationType.SCAN:
        package_inventory = dnf_report.generate_report(dnf, baseline, operation_type)

        if package_inventory is None:
            append_runtime_metric_file_info("Package inventory is None")
            exit_code = ExitCodes.FAILURE
        else:
            exit_code = ExitCodes.SUCCESS

    elif operation_type.lower() == OperationType.INSTALL:
        logger.info("Installation process started:\n")
        package_inventory_before_install = dnf_report.generate_report(dnf, baseline, operation_type, override_list)

        exit_code, package_inventory = dnf_update.perform_update(dnf, package_inventory_before_install, baseline, override_list)

        package_inventory.current_installed_pkgs = list(get_packages_installed_on_current_run(
            package_inventory_before_install.installed_pkgs + package_inventory_before_install.installed_other_pkgs + package_inventory_before_install.installed_rejected_pkgs,
            package_inventory.installed_pkgs + package_inventory.installed_other_pkgs + package_inventory.installed_rejected_pkgs,
            ))
        # The exit code returned from dnf_update is the result of building the transaction, not running it.
        # processTransaction is used to run the transaction but does not include a return code. Attempts to update to
        # runTransaction (which has a return code), failed.  cf
        # Transaction may have built, run without exception but should still be failed.
        if package_inventory.failed_pkgs and len(package_inventory.failed_pkgs) > 0:
            if (exit_code == ExitCodes.SUCCESS):
                exit_code = ExitCodes.FAILURE
                append_runtime_metric_file_info("Package inventory has failed packages")
            elif (exit_code == ExitCodes.REBOOT):
                exit_code = ExitCodes.REBOOT_WITH_FAILURES
                append_runtime_metric_file_info("Package inventory has failed packages")
    else:
        raise Exception("Unknown operation: %s" % (operation_type))
    # This exits success, failure, or reboot depending on the exit code from Dnf.
    return (exit_code, package_inventory)
