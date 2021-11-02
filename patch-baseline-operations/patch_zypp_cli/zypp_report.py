#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import logging
from patch_common import package_inventory
from patch_zypp_cli import zypp_shared_operation_methods as shared

logger = logging.getLogger()

def zypp_report(ZYpp_base, baseline, operation_type, override_list = None):
    """
    :param ZYpp_base - ZYpp(ZypperCLI())
    :param baseline: baseline
    :param operation_type: "Scan" or "Install"
    :param install_override_list: override list
    """

    try:
        zb = ZYpp_base
        return _report_package(zb, baseline, operation_type, override_list)
    except Exception as e:
        logger.exception('Unable to generate a zypp package report.')
        return None

def _report_package(zb, baseline, operation_type, override_list):
    """
    :param zb: zypp object from  zypp
    :param baseline: zypp baseline from us
    :param install_override_list: list used in install.
    :return: tuples of installed, installed other,
             missing and not applicable arrays of packages.
    """
    
    # This is a dict of form {(name, arch) => [CLIPackageBean, ...]} where each 
    # CLIPackageBean represents a different combination of classification, severity, etc...
    all_packages = zb.get_all_installed_packages()

    # get all uninstalled packages
    potential_not_applicable_packages = zb.get_all_uninstalled_packages()

    # append to installed packages hash list.
    all_package_to_report = shared.append_na2pkg_hash_list_to_na2pkg_hash_list(all_packages, potential_not_applicable_packages)

    # get zypp report from baseline.
    (missing, installed, installed_rejected, installed_other, not_applicable) = \
    baseline.categorize_packages_scan(all_package_to_report)


    return package_inventory.PackageInventory(
        operation_type=operation_type,
        pkg_type='zypp',
        installed_pkgs = installed if installed else [],
        installed_other_pkgs = installed_other if installed_other else [],
        not_applicable_pkgs = not_applicable if not_applicable else [],
        missing_pkgs = missing if missing else [],
        installed_rejected_pkgs = installed_rejected,
        failed_pkgs = [],
        override_list = override_list
    )