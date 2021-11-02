#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import os
import sys

# We use to dynamically import our entrance module with -1 as the level per: https://python-reference.readthedocs.io/en/latest/docs/functions/__import__.html
# Recent change to Python 3 broke this level: https://bugs.python.org/issue15610
# Now we have to manually append the path. 
full_path = os.path.realpath(__file__)
path, filename = os.path.split(full_path)
sys.path.append(os.path.realpath(path))

import zypp_report
import zypp_update
from patch_common.constant_repository import ExitCodes
from patch_common.constant_repository import OperationType
from patch_common.package_compliance import get_packages_installed_on_current_run
from patch_common.metrics_service import append_runtime_metric_file_info

def zypp_main(zb, baseline, operation_type, override_list):
    """
    :param baseline: baseline from us
    :param operation_type: can be either "scan" or "install"
    :return: (exit_code, package inventory) from us
    please refer to zypp_update.zypp_update function for the definition of return code
    """
    package_inventory = None

    # refresh repo or fail on connection issue.
    zb.refresh()
    if operation_type.lower() == OperationType.SCAN:
        package_inventory = zypp_report.zypp_report(zb, baseline, operation_type)
        if package_inventory is None:
            append_runtime_metric_file_info("Package inventory is None")
            exit_code = ExitCodes.FAILURE
        else:
            exit_code = ExitCodes.SUCCESS

    elif operation_type.lower() == OperationType.INSTALL:
        # Running scan before install
        package_inventory_before_install = zypp_report.zypp_report(zb, baseline, OperationType.SCAN, override_list)
        # Running install with results from scan
        (exit_code, package_inventory) = zypp_update.zypp_update(zb, baseline, package_inventory_before_install, override_list)

        package_inventory.current_installed_pkgs = list(get_packages_installed_on_current_run(
            package_inventory_before_install.installed_pkgs + package_inventory_before_install.installed_other_pkgs + package_inventory_before_install.installed_rejected_pkgs,
            package_inventory.installed_pkgs + package_inventory.installed_other_pkgs + package_inventory.installed_rejected_pkgs,
            ))
    else:
        append_runtime_metric_file_info("Unknown operation %s"%operation_type)
        raise Exception("Unknown operation: %s" % (operation_type))

    return (exit_code, package_inventory)
