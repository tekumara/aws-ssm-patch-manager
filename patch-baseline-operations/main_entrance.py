#!/usr/bin/env python
# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys
import traceback

from patch_common.baseline_override import output_baseline_override_results
from patch_common.metrics_service import append_runtime_metric_file_info

sys.path.insert(1, "./")
sys.path.insert(1, "./botocore/vendored")

import logging
import os
import datetime
import optparse
import json
from patch_common import snapshot
from patch_common.constant_repository import ExitCodes, Metrics, OperationType, RebootOption, INVENTORY_PATH, CONFIGURATION_DIRECTORY
from patch_common.exceptions import PatchManagerError
from patch_common import package_compliance
from patch_common.install_override_list import InstallOverrideList
import patch_common.instance_info
import patch_common.inventory_uploader
from patch_common.downloader import load_json_file
from patch_common import reboot_controller
from patch_common.patch_states_configuration import PatchStatesConfiguration
from patch_common import livepatch_utils
from patch_common.metrics_service import try_initialize_metrics_service, post_metric, append_runtime_metric_traceback, append_runtime_metric_file_info, set_runtime_metric, deallocate_metrics_service

# initialize logging
LOGGER_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOGGER_DATEFORMAT = "%m/%d/%Y %X"
LOGGER_LEVEL = logging.INFO
LOGGER_STREAM = sys.stdout

logging.basicConfig(format=LOGGER_FORMAT, datefmt=LOGGER_DATEFORMAT, level=LOGGER_LEVEL, stream=LOGGER_STREAM)
logger = logging.getLogger()

MODULE_OVERRIDES = dict.fromkeys(
    ['amazon_linux', 'amazon_linux_2', 'centos', 'redhat_enterprise_linux', 'oracle_linux'],
    'yum_generic_entrance')
MODULE_OVERRIDES.update(dict.fromkeys(['ubuntu', 'debian', 'raspbian'], 'apt_entrance'))
MODULE_OVERRIDES.update(dict.fromkeys(['redhat_enterprise_linux_8', 'centos_8', 'oracle_linux_8'], 'dnf_generic_entrance'))

def get_commandline_options():
    """
    Method for parsing the command line arguments.

    :returns: the command line arguments as separate options.
    """
    parser = optparse.OptionParser()
    parser.add_option("-d", "--debug", dest="debug", default=False)
    parser.add_option("-f", "--file", dest="file",
                      help="""
                      path to json file which contains
                      'patchBaseline': <baseline json object>
                      'product': <instance product>
                      'patchGroup': <patch group this instance belongs to>
                      'instanceId': <instance ID, such as i-12345678>
                      'region': <aws public region, such as us-east-1>
                      'operation': <install / scan>
                      'snapshotId': <snapshot UUID>
                      """)
    (options, _) = parser.parse_args()
    return options


def get_execution_module(operating_system, product):
    """
    Method for getting the correct python module for a given operating system and product

    :param operating_system: the operating system in lower case from snapshot.
    :param product: the product version of the given operating system
    :return: returns an imported module that contains an execute() method for running the package.
    """
    module_name = get_module_name(operating_system, product)
    try:
        if os.path.exists(module_name + ".py"):
            logger.debug("Loading module %s for %s", module_name, operating_system)
            return __import__(module_name, globals(), locals(), [], 0)
        else:
            module_name = operating_system + '_entrance'
            if os.path.exists(module_name + ".py"):
                return __import__(module_name, globals(), locals(), [], 0)

    except Exception as e :
        raise PatchManagerError("Error importing module %s for %s" % (module_name, operating_system), e)
    raise PatchManagerError("Could not find module %s for %s" % (module_name, operating_system))

def get_module_name(operating_system, product):
    """
    Method for getting the correct python module for a given operating system and product
    :param operating_system: the operating system in lower case from snapshot.
    :param product: the product version of the given operating system
    :return: the corresponding key in the MODULE_OVERRIDES dict
    """
    if operating_system == 'redhat_enterprise_linux' and product.startswith('RedhatEnterpriseLinux8'):
        return MODULE_OVERRIDES.get('redhat_enterprise_linux_8', operating_system + '_entrance')
    elif operating_system == 'centos' and product.startswith('CentOS8'):
        return MODULE_OVERRIDES.get('centos_8', operating_system + '_entrance')
    elif operating_system == 'oracle_linux' and product.startswith('OracleLinux8'):
        return MODULE_OVERRIDES.get('oracle_linux_8', operating_system + '_entrance')
    else:
        return MODULE_OVERRIDES.get(operating_system, operating_system + '_entrance')

def transform_exit_code(patching_exit_code, inventory_success, is_reboot_required, operation, reboot_option):
    """
    Method transforms the exit code to indicate situations where a reboot is required.

    :param patching_exit_code: system exit code to transform
    :param inventory_success: boolean indicating if inventory report was successfully uploaded.
    :param is_reboot_required: boolean
    :param operation: operation type requested.
    :param reboot_option: reboot option that passed in by customers control reboot workflow.
    :return:  returns: the exit code to use, taking into account if inventory upload was successful or not.
    """

    if is_reboot_required:
        if inventory_success:
            logging.info("Inventory upload was successful")
            if patching_exit_code == ExitCodes.SUCCESS or patching_exit_code == ExitCodes.REBOOT:
                logging.info("Reboot is required with patching exit code %s", patching_exit_code)
                return ExitCodes.REBOOT
            else:
                logging.error("Patching Operation failed with exit code %s but instance needs reboot", patching_exit_code)
                append_runtime_metric_file_info()
                return ExitCodes.REBOOT_WITH_FAILURES
        else:
            logging.error("Patching exit code is %s and inventory reporting failed but reboot is required", patching_exit_code)
            append_runtime_metric_file_info()
            return ExitCodes.REBOOT_WITH_FAILURES
    else:
        if operation.lower() == OperationType.SCAN:
            logging.info("Reboot is not permitted for scan operation")
        elif reboot_option == RebootOption.NO_REBOOT:
            logging.info("Reboot is not permitted because RebootOption is NoReboot")
        else:
            logging.info("Reboot is not required")
        if inventory_success and (patching_exit_code == ExitCodes.SUCCESS or patching_exit_code == ExitCodes.REBOOT):
            return ExitCodes.SUCCESS
        else:
            logging.error("Failure occurred in the operation, patching exit code is %s and inventory exit code is %i", patching_exit_code, inventory_success)
            append_runtime_metric_file_info()
            return ExitCodes.FAILURE

def upload_inventory_report(summary, compliance, snapshot):
    """
    Method to upload the PackageInventory result to inventory.

    :param summary: patch inventory summary
    :param compliance: patch inventory compliance
    :param snapshot: snapshot object representing snapshot.json
    :returns: A boolean representing if the inventory report upload was a success.
    """
    inventory_success = False

    try:
        # TODO: Change to string size once we get the right encoding that inventory uses
        compliance_json_char_count = len(json.dumps(compliance))
        summary_json_char_count = len(json.dumps(summary))
        set_runtime_metric(Metrics.COMPLIANCE_ITEM_CHAR_COUNT, compliance_json_char_count)
        set_runtime_metric(Metrics.SUMMARY_ITEM_CHAR_COUNT, summary_json_char_count)

        patch_common.inventory_uploader.upload_report(
            region=snapshot.region,
            instance_id=snapshot.instance_id,
            summary_item=summary,
            compliance_item=compliance
        )
        inventory_success = True
        logger.info("Report upload successful.")
    except Exception:
        logger.exception("Unable to upload compliance report.")
        append_runtime_metric_traceback()
    return inventory_success

def get_compliance_report(snapshot, package_inventory, start_time, patching_exit_code, patch_states_configuration):
    """
    Method to get the PackageCompliance from inventory.

    :param snapshot: snapshot object representing snapshot.json
    :param package_inventory: PackageInventory object (found in patch_common) that represents the patching results.
    :param start_time: utc date representing time the patching started.
    :param patching_exit_code: exit code of the patching operation.
    :param patch_states_configuration: patch state configuration object.
    :returns: A boolean representing if the inventory report upload was a success.
    """
    compliance = package_compliance.PackageCompliance(
                instance_id=snapshot.instance_id,
                baseline_id=snapshot.patch_baseline.baseline_id,
                snapshot_id=snapshot.snapshot_id,
                patch_group=snapshot.patch_group,
                patch_inventory=package_inventory,
                start_time=start_time,
                end_time=datetime.datetime.utcnow(),
                patching_exit_code=patching_exit_code,
                reboot_option=snapshot.reboot_option,
                patch_states_configuration=patch_states_configuration,
                operating_system=snapshot.patch_baseline.operating_system.lower(),
                # only include override list to the compliance reporting for install operation if specified
                install_override_list=snapshot.install_override_list if snapshot.operation.lower() == "install" else None,
                execution_id=os.environ["SSM_COMMAND_ID"] if "SSM_COMMAND_ID" in os.environ else None

            )
    return compliance.generate_compliance_report()

def save_inventory_to_configuration(summary):
    """
    Method to save the patch inventory summary result to local configuration.
    :param summary: patch inventory summary
    """
    if not os.path.exists(CONFIGURATION_DIRECTORY):
        os.makedirs(CONFIGURATION_DIRECTORY)

    try:
        with open(INVENTORY_PATH, 'w+') as f:
            logger.info("Saving inventory to local configuration directory")
            json.dump(summary, f, indent=4)
    except Exception as e:
        append_runtime_metric_traceback()
        logger.warn("Could not save inventory summary locally at %s", INVENTORY_PATH)


# ------------- BEGIN MAIN -------------#

if __name__ == "__main__":

    start_time = datetime.datetime.utcnow()
    patching_exit_code = 1
    inventory = None
    inventory_success = False
    metrics_exit_code = None
    is_reboot_required = False
    try:

        # Load options and snapshot
        snapshot_path = get_commandline_options().file
        logger.info("Loading patch snapshot from %s", snapshot_path)
        snapshot_object = snapshot.Snapshot(load_json_file(snapshot_path))
        try_initialize_metrics_service(snapshot_object)

        patch_states_configuration = PatchStatesConfiguration()
        override_list = InstallOverrideList.load(snapshot_object)

        oper_sys = snapshot_object.patch_baseline.operating_system.lower()
        patch_common.instance_info.product = snapshot_object.product
        patch_common.instance_info.instance_id = snapshot_object.instance_id
        patch_common.instance_info.region = snapshot_object.region

        (patching_exit_code, inventory) = (get_execution_module(oper_sys, snapshot_object.product)).execute(snapshot_object, override_list)

        if inventory is None:
            append_runtime_metric_file_info()
            metrics_exit_code = ExitCodes.FAILURE
            sys.exit(ExitCodes.FAILURE)

        livepatch_utils.modify_kernel_and_livepatch_status(oper_sys, snapshot_object.reboot_option, inventory, patch_states_configuration, override_list)

        if (oper_sys == "macos"):
            is_reboot_required = reboot_controller.needs_reboot(snapshot_object.reboot_option, patch_states_configuration, inventory.operation_type.lower(), patching_exit_code, oper_sys)
        else:
            is_reboot_required = reboot_controller.needs_reboot(snapshot_object.reboot_option, patch_states_configuration, inventory.operation_type.lower(), patching_exit_code)

        if inventory:
            summary, compliance = get_compliance_report(snapshot_object, inventory, start_time, patching_exit_code, patch_states_configuration)
            # this is designed for Patch Hooks feature
            save_inventory_to_configuration(summary)
            if snapshot_object.baseline_override:
                output_baseline_override_results(summary, compliance)
                inventory_success = True
            else:
                inventory_success = upload_inventory_report(summary, compliance, snapshot_object)
        sys.exit(transform_exit_code(patching_exit_code, inventory_success, is_reboot_required, inventory.operation_type.lower(), snapshot_object.reboot_option))

    except Exception as e:
        logger.exception(e)
        set_runtime_metric(Metrics.UNHANDLED_EXCEPTIONS, traceback.extract_tb(sys.exc_info()[2]))
        if isinstance(e, PatchManagerError):
            metrics_exit_code = e.error_code
        else:
            metrics_exit_code = ExitCodes.FAILURE
        sys.exit(ExitCodes.FAILURE)
    finally:
        if not metrics_exit_code:
            metrics_exit_code = transform_exit_code(patching_exit_code, inventory_success, is_reboot_required, inventory.operation_type.lower(), snapshot_object.reboot_option)
        post_metric(metric_value=metrics_exit_code, package_inventory=inventory, start_time=start_time), deallocate_metrics_service
        # not doing this causes frequent segfaults on some combinations of kernel and python versions
        deallocate_metrics_service()
# -------------_ END MAIN _-------------#
