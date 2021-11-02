#!/usr/bin/env python
# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys
import logging

sys.path.insert(1, "./")
sys.path.insert(1, "./botocore/vendored")

from patch_common.constant_repository import RebootOption
import common_os_selector_methods
import warnings


# initialize logging
LOGGER_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOGGER_DATEFORMAT = "%m/%d/%Y %X"
LOGGER_LEVEL = logging.INFO
LOGGER_STREAM = sys.stdout

logging.basicConfig(format=LOGGER_FORMAT, datefmt=LOGGER_DATEFORMAT, level=LOGGER_LEVEL, stream=LOGGER_STREAM)
logger = logging.getLogger()

# Suppress Syntax Warning in dependency for Python 3.8
warnings.filterwarnings(
    action='ignore',
    category=SyntaxWarning,
    module=r'jmespath\.visitor'
)

def execute(document_step, snapshot_id, operation_type, override_list=None, reboot_option=RebootOption.REBOOT_IF_NEEDED, baseline_override=None):
    """
    Entry point to the AWS-RunPatchBaseline payload.

    Ultimately, it figures out which part of the payload to run with what parameters and launches it
    as a separate process, using the same python interpreter as is currently running.

    The same python interpreter is used because that was previously determined to be the most appropriate one.

    A separate process is launched to ensure changes in the SE Linux context are loaded.

    :param: document_step - Either PatchMacOS or PatchLinux
    :param: snapshot_id - to fetch the snapshot
    :param: operation_type - scan or install
    :param: override_list - the override list provided by the customer to use during an install operation.
    :param: reboot_option - document parameter indicating if system should be rebooted after operation or not.
    :param baseline_override - The baseline override provided by the customer to use instead of pre-configured baseline
    :return: exit code for the agent
    """
    instance_id, region = common_os_selector_methods.get_instance_information()

    (snapshot_id, product, patch_group, baseline, operating_system) = \
        common_os_selector_methods.fetch_snapshot(operation_type, instance_id, region, reboot_option, document_step,
                                                  snapshot_id, override_list=override_list, baseline_override=baseline_override)


    common_os_selector_methods.save_snapshot(baseline, operating_system, instance_id, region, product,\
            patch_group, operation_type, snapshot_id, reboot_option, override_list, baseline_override)

    return common_os_selector_methods.execute_entrance_script("./main_entrance.py",operating_system, operation_type, product)


