# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common.constant_repository import ExitCodes
import yum_report
import yum_update
import yum_repolist
from patch_common.package_compliance import get_packages_installed_on_current_run
from patch_common.livepatch_utils import remove_not_current_kernel_livepatches
from patch_common.livepatch_utils import LIVEPATCH_ENABLED
from patch_common.metrics_service import append_runtime_metric_file_info

def yum_main(baseline, operation_type, override_list=None):
    """
    Starting point for the scan or install operation.

    :param baseline: baseline object
    :param operation_type: can be either "scan" or "install"
    :param override_list: a list of patches to override installation decisions
    :return: (exit_code, package inventory) see patch_common.constant_repository.ExitCodes
    """
    package_inventory = None
    if operation_type.lower() == "scan":
        package_inventory = yum_report.yum_report(baseline, operation_type)
        if package_inventory is None:
            append_runtime_metric_file_info()
            exit_code = ExitCodes.FAILURE
        else:
            exit_code = ExitCodes.SUCCESS

    elif operation_type.lower() == "install":
        package_inventory_before_install = yum_report.yum_report(baseline, operation_type, override_list)
        if package_inventory_before_install is None:
            append_runtime_metric_file_info()
            exit_code = ExitCodes.FAILURE
            return (exit_code, None)
        repos_before_install = yum_repolist.yum_list_repos(baseline)

        exit_code = yum_update.yum_update(baseline, override_list)

        repos = yum_repolist.yum_list_repos(baseline)
        package_inventory = yum_report.yum_report(baseline, operation_type, override_list)

        package_inventory.current_installed_pkgs = list(get_packages_installed_on_current_run(
            package_inventory_before_install.installed_pkgs + package_inventory_before_install.installed_other_pkgs + package_inventory_before_install.installed_rejected_pkgs,
            package_inventory.installed_pkgs + package_inventory.installed_other_pkgs + package_inventory.installed_rejected_pkgs,
        ))

        # Remove the not current kernel's livepatches from failed transactions since we don't care about them.
        if LIVEPATCH_ENABLED:
            package_inventory.failed_pkgs = remove_not_current_kernel_livepatches(package_inventory.failed_pkgs)

        # The exit code returned from yum_update is the result of building the transaction, not running it.
        # processTransaction is used to run the transaction but does not include a return code. Attempts to update to
        # runTransaction (which has a return code), failed.
        # Transaction may have built, run without exception but should still be failed.
        if package_inventory.failed_pkgs and len(package_inventory.failed_pkgs) > 0:
            if (yum_repolist.yum_detect_repo_change(repos_before_install, repos)):
                yum_repolist.log_repo_update_error()

            if (exit_code == ExitCodes.SUCCESS):
                append_runtime_metric_file_info()
                exit_code = ExitCodes.FAILURE
            elif (exit_code == ExitCodes.REBOOT):
                append_runtime_metric_file_info()
                exit_code = ExitCodes.REBOOT_WITH_FAILURES
    else:
        raise Exception("Unknown operation: %s" % (operation_type))
    # This exits success, failure, or reboot depending on the exit code from YUM.
    return (exit_code, package_inventory)
