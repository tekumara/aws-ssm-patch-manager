#!/usr/bin/env python
# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys

from patch_common.exceptions import PatchManagerError


sys.path.insert(1, "./")
sys.path.insert(1, "./botocore/vendored")

import json
import logging
import optparse
import os

from patch_common import snapshot
from patch_common.constant_repository import ExitCodes, OperationType, RebootOption
from patch_common import reboot_controller
from patch_common.metrics_service import append_runtime_metric_file_info

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

def get_execution_module(operating_system, product):
    """
    Method to import the execution entrance file depending on OS.

    :param operating_system = the operating system in lower case from snapshot.
    :return: returns an imported module that contains an execute() method for running the package.
    """
    module_name = get_module_name(operating_system, product)
    try:
        if os.path.exists(module_name + ".py"):
            logger.debug("Loading module %s for %s", module_name, operating_system)
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
