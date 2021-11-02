# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import datetime
import hashlib
import json
import logging
import time
import uuid
from patch_common.package_matcher import get_package_title, get_package_id, get_package_patch_severity, get_package_severity, get_package_classification, get_package_cves
from patch_common.constant_repository import Compliance_string_formatting, ExitCodes, OperationType, RebootOption, REBOOT_EXIT_CODES, PatchStatesConfigurationKeys
from patch_common.system_utils import get_last_reboot_time
from patch_common import livepatch_utils
from patch_common import reboot_controller
from patch_common import system_utils

logger = logging.getLogger()


class PackageCompliance:

    def __init__(self,
                 instance_id,
                 baseline_id,
                 snapshot_id,
                 patch_group,
                 patch_inventory,
                 start_time,
                 end_time,
                 patching_exit_code,
                 reboot_option,
                 patch_states_configuration,
                 operating_system,
                 upload_na_compliance=False,
                 install_override_list=None,
                 association_id="",
                 baseline_name="",
                 execution_id=str(uuid.uuid4()),
                 association_severity="",
                 non_compliant_severity=None):
        self.instance_id = instance_id
        self.baseline_id = baseline_id
        self.snapshot_id = snapshot_id
        self.patch_group = patch_group
        self.patch_inventory = patch_inventory
        self.start_time = start_time
        self.end_time = end_time
        self.upload_na_compliance = upload_na_compliance
        self.install_override_list = install_override_list
        self.reboot_option = reboot_option
        self.patching_exit_code = patching_exit_code
        self.patch_states_configuration = patch_states_configuration
        self.operating_system = operating_system
        self.association_id=association_id
        self.baseline_name=baseline_name
        self.execution_id = execution_id if execution_id != None else str(uuid.uuid4())
        self.association_severity=association_severity
        self.non_compliant_severity=non_compliant_severity

        logger.info("""
Package compliance initialized with instance ID:%s, 
baseline ID: %s, snapshot ID: %s, patch group: %s,
start time: %s, end time: %s, upload NA compliance: %s, 
install override list path: %s, execution id: %s
        """,
                    instance_id, baseline_id, snapshot_id, patch_group,
                    start_time, end_time, upload_na_compliance, install_override_list, self.execution_id)

        # Calculate non compliant severity
        compliance_priority = {"CRITICAL" : 5, "HIGH" : 4, "MEDIUM" : 3, "LOW" : 2, "INFORMATIONAL": 1, "UNSPECIFIED": 0}

        non_compliant_pkgs = self.patch_inventory.failed_pkgs + self.patch_inventory.installed_rejected_pkgs + self.patch_inventory.missing_pkgs + self.patch_inventory.installed_pending_reboot_pkgs

        if not non_compliant_pkgs:
            # Exit immediately if instance is compliant
            logger.info(""" Instance is Compliant """)
            return

        self.non_compliant_severity = "INFORMATIONAL" # Assign the default severity value and update later

        # Loop through non-compliant packages and assign the highest compliance level
        for pkg in non_compliant_pkgs:
            compliance_level = get_package_severity(self.operating_system, pkg)
            if compliance_level == "CRITICAL": # If non compliant level is CRITICAL. update and exit immeidetly 
                self.non_compliant_severity = compliance_level
                logger.info(""" Instance is Non-Compliant with severity of %s """, self.non_compliant_severity)
                return
            if compliance_priority[compliance_level] > compliance_priority[self.non_compliant_severity]: # Otherwise compare it with current compliance level
                self.non_compliant_severity = compliance_level

        logger.info(""" Instance is Non-Compliant with severity of %s """, self.non_compliant_severity)

    def _update_inventory_for_reboot_state(self):

        """
        Update compliance data for installed patches pending reboot.
        :return: updated PackageInventory
        """

        last_no_reboot_operation_time = self.patch_states_configuration.last_no_reboot_install_operation_time

        self._update_installation_time_for_pkgs()
        # There are three cases we don't need to care about the pending reboot state because it will trigger reboot to erase all the pending reboot patches
        # 1. Customer never performed Install Operation with NoReboot and current operation is not Install with No Reboot
        # 2. Exit code is reboot related and reboot option is RebootIfNeeded
        # 3. Install Operation found no missing packages but found PendingReboot packages and RebootOption is RebootIfNeeded.

        if (last_no_reboot_operation_time == 0 and not (self.reboot_option == RebootOption.NO_REBOOT and self.patch_inventory.operation_type.lower() == OperationType.INSTALL)) or \
                (self.patching_exit_code in REBOOT_EXIT_CODES and self.reboot_option == RebootOption.REBOOT_IF_NEEDED) or \
                (reboot_controller.has_pending_reboot_patches(self.patch_states_configuration) and self.patch_inventory.operation_type.lower() == OperationType.INSTALL and self.reboot_option == RebootOption.REBOOT_IF_NEEDED):
            return

        self._update_installed_pending_reboot_pkgs(self.patch_inventory.current_installed_pkgs)

    def _update_installation_time(self, pkg_list):
        '''
        Updates the installation time for each pkg in pgk_list
        :param pkg_list:
        :return: None
        '''
        for itr in range(len(pkg_list)):
            pkg_list[itr].installed_time = self._get_installation_time(pkg_list[itr])

    def _update_installation_time_for_pkgs(self):
        """
        Updates the installation time of installed package categories.
        :return: None.
        """
        self._update_installation_time(self.patch_inventory.installed_pkgs)
        self._update_installation_time(self.patch_inventory.installed_other_pkgs)
        self._update_installation_time(self.patch_inventory.installed_rejected_pkgs)

    def _update_installed_pending_reboot_pkgs(self, current_installed_packages):
        """
        Extracts installed pending reboot packages from other install package inventory categories.
        :param current_installed_packages: set of packages got installed by us in current operation, without live patches if Live-Patching is identified        :return: None
        """
        last_reboot_time = get_last_reboot_time(self.operating_system)

        pending_reboot_packages_dict = {}
        for pkg in current_installed_packages:
            pending_reboot_packages_dict[get_package_title(self.operating_system, pkg)] = pkg

        for title, package in pending_reboot_packages_dict.items():
            if package.installed_time is None:
                package.installed_time = system_utils.get_total_seconds(self.end_time - datetime.datetime(1970, 1, 1))

        # Add previous Installed Pending Reboot patches if no reboot detected since last no reboot install time
        if last_reboot_time < self.patch_states_configuration.last_no_reboot_install_operation_time:
            pending_reboot_packages_dict.update(self.retrieve_previous_pending_reboot_patches())
            if livepatch_utils.should_put_kernel_back_to_pending_reboot(self.operating_system, self.patch_states_configuration):
                pending_reboot_packages_dict.update(self.retrieve_pending_reboot_kernel())

        self.patch_inventory.installed_pkgs = _filter_installed_pending_reboot_pkgs(
            self.patch_inventory.installed_pkgs, pending_reboot_packages_dict, self.operating_system)

        self.patch_inventory.installed_other_pkgs = _filter_installed_pending_reboot_pkgs(
            self.patch_inventory.installed_other_pkgs, pending_reboot_packages_dict, self.operating_system)

        self.patch_inventory.installed_rejected_pkgs = _filter_installed_pending_reboot_pkgs(
            self.patch_inventory.installed_rejected_pkgs, pending_reboot_packages_dict, self.operating_system)

        self.patch_inventory.installed_pending_reboot_pkgs = list(pending_reboot_packages_dict.values())

    def generate_compliance_report(self):
        """
        Generate the inventory items for the compliance report to ec2 inventory
        :return: summary, compliance inventory item tuple
        """
        self._update_inventory_for_reboot_state()
        compliance = self._get_package_compliance_item()
        summary = self._get_patch_summary_item(compliance.get("Content", []))
        self._update_patch_configuration()

        return summary, compliance

    def _update_patch_configuration(self):
        logger.info("Updating patch state configuration")
        # need to convert to epoch seconds
        last_no_reboot_operation_time = self._get_last_no_reboot_operation_time()
        if last_no_reboot_operation_time:
            epoch = datetime.datetime(1970, 1, 1, 0, 0, 0)
            last_no_reboot_operation_time = system_utils.get_total_seconds(last_no_reboot_operation_time - epoch)
        else:
            last_no_reboot_operation_time = 0
        self.patch_states_configuration.update_configuration(self.operating_system, self.patch_inventory, last_no_reboot_operation_time)

    def datetime_to_string(self, date_time):
        """
        :param date_time: datetime.datetime
        :return: formatted string
        """
        return date_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _get_patch_summary_item(self, compliance_items):
        """
        :return: return the level 1 content for patch summary
        """
        content = self._get_patch_summary_content(compliance_items)
        content_sha256 = generate_sha256(content)
        logger.info(content)
        return {
            "TypeName": "AWS:PatchSummary",
            "SchemaVersion": "1.0",
            "ContentHash": content_sha256,
            "CaptureTime": self.datetime_to_string(self.end_time),
            "Content": content
        }

    def generate_associations_compliance_report(self):
        """
        Generate the compliance items for the compliance report to compliance
        :return: compliance inventory item tuple
        """
        self._update_inventory_for_reboot_state()
        compliance = self._get_association_compliance_item()
        self._update_patch_configuration()

        return compliance   

    def _get_association_compliance_item(self):
        """
        :return: return the level 1 content for patch compliance
        """
        self._sort_patch_inventory()
        compliance_items = self._get_package_compliance_content()
        ( critical_non_compliant_count, security_non_compliant_count, other_non_compliant_count ) = self._get_count(compliance_items)

        status = "COMPLIANT"
        if len(self.patch_inventory.installed_rejected_pkgs) > 0 or len(self.patch_inventory.installed_pending_reboot_pkgs) > 0 \
            or len(self.patch_inventory.missing_pkgs) > 0 or len(self.patch_inventory.failed_pkgs) > 0:
            status="NON_COMPLIANT"

        detailed_text_content = {
            "PatchGroup": self.patch_group,
            "SnapshotId": self.snapshot_id,
            "ExecutionId": self.execution_id,
            "InstalledCount": str(len(self.patch_inventory.installed_pkgs)),
            "InstalledOtherCount": str(len(self.patch_inventory.installed_other_pkgs)),
            "InstalledRejectedCount": str(len(self.patch_inventory.installed_rejected_pkgs)),
            "InstalledPendingRebootCount": str(len(self.patch_inventory.installed_pending_reboot_pkgs)),
            "NotApplicableCount": str(len(self.patch_inventory.not_applicable_pkgs)),
            "MissingCount": str(len(self.patch_inventory.missing_pkgs)),
            "FailedCount": str(len(self.patch_inventory.failed_pkgs)),
            "CriticalNonCompliantCount": str(critical_non_compliant_count),
            "SecurityNonCompliantCount": str(security_non_compliant_count),
            "OtherNonCompliantCount": str(other_non_compliant_count),
            "OperationType": self.patch_inventory.operation_type,
            "OperationStartTime": self.datetime_to_string(self.start_time),
            "OperationEndTime": self.datetime_to_string(self.end_time)
        }
        if self.non_compliant_severity: # For compliant instance we don't include NonCompliantSeverity
            detailed_text_content["NonCompliantSeverity"] = str(self.non_compliant_severity)

        detailed_text_content = json.dumps(detailed_text_content)
        content = [{
            "Id": self.association_id,
            "Title": self.baseline_name,
            "Severity": self.association_severity, 
            "Status": status,
            "Details": {
                "DocumentName": "AWS-RunPatchBaselineAssociation",
                "DocumentVersion": "1",
                "PatchBaselineId": self.baseline_id,
                "DetailedText": detailed_text_content
            },
            "OperationStartTime": self.datetime_to_string(self.start_time)
        }]
        content_sha256 = generate_sha256(content)
        del content[0]['OperationStartTime']
        return {
            "ResourceId": self.instance_id,
            "ResourceType": "ManagedInstance",
            "ComplianceType": "Association",
            "ExecutionSummary": {
                "ExecutionTime": self.datetime_to_string(self.start_time),
                "ExecutionId": self.association_id,
                "ExecutionType": "Command"
            },
            "UploadType": "PARTIAL",
            "Items" : content,
            "ItemContentHash" : content_sha256
        }


    def _get_package_compliance_item(self):
        """
        :return: return the level 1 content for patch compliance
        """
        content = self._get_package_compliance_content()
        content_sha256 = generate_sha256(content)
        return {
            "TypeName": "AWS:ComplianceItem",
            "SchemaVersion": "1.0",
            "ContentHash": content_sha256,
            "CaptureTime": self.datetime_to_string(self.end_time),
            "Context": {
                "ComplianceType": "Patch",
                "ExecutionId": self.snapshot_id,
                "ExecutionType": "Command",
                "ExecutionTime": self.datetime_to_string(self.start_time),
            },
            "Content": content
        }

    def _get_patch_summary_content(self, compliance_items):
        """
        :return: return the level 2 content for patch summary
        """
        ( critical_non_compliant_count, security_non_compliant_count, other_non_compliant_count ) = self._get_count(compliance_items)

        ret = {
            "BaselineId": self.baseline_id,
            "PatchGroup": self.patch_group,
            "SnapshotId": self.snapshot_id,
            "ExecutionId": self.execution_id,
            "InstalledCount": str(len(self.patch_inventory.installed_pkgs)),
            "InstalledOtherCount": str(len(self.patch_inventory.installed_other_pkgs)),
            "InstalledRejectedCount": str(len(self.patch_inventory.installed_rejected_pkgs)),
            "InstalledPendingRebootCount": str(len(self.patch_inventory.installed_pending_reboot_pkgs)),
            "NotApplicableCount": str(len(self.patch_inventory.not_applicable_pkgs)),
            "MissingCount": str(len(self.patch_inventory.missing_pkgs)),
            "FailedCount": str(len(self.patch_inventory.failed_pkgs)),
            "CriticalNonCompliantCount": str(critical_non_compliant_count),
            "SecurityNonCompliantCount": str(security_non_compliant_count),
            "OtherNonCompliantCount": str(other_non_compliant_count),
            "OperationType": self.patch_inventory.operation_type,
            "OperationStartTime": self.datetime_to_string(self.start_time),
            "OperationEndTime": self.datetime_to_string(self.end_time),
            "RebootOption": self.reboot_option
        }

        if self.install_override_list:
            ret["InstallOverrideList"] = self.install_override_list

        last_no_reboot_operation_time = self._get_last_no_reboot_operation_time()
        if last_no_reboot_operation_time:
            ret["LastNoRebootInstallOperationTime"] = self.datetime_to_string(last_no_reboot_operation_time)

        if self.non_compliant_severity: # For compliant instance we don't include NonCompliantSeverity
            ret["NonCompliantSeverity"] = str(self.non_compliant_severity)
            
        return [ret]

    def _get_count(self, compliance_items):
        """
        Return a tuple of CriticalNonCompliantCount, SecurityNonCompliantCount and OtherNonCompliantCount
        """
        criticalNonCompliantCount = 0
        securityNonCompliantCount = 0
        otherNonCompliantCount = 0
        for compliance_item in compliance_items:
            criticalOrSecurityVisited = False
            if compliance_item.get("Status", "") != 'NON_COMPLIANT':
                continue
            if compliance_item.get("Severity", "") and compliance_item.get("Severity", "").lower() == 'critical':
                criticalNonCompliantCount += 1
                criticalOrSecurityVisited = True
            if compliance_item.get("Classification", "").lower() == 'security':
                securityNonCompliantCount += 1
                criticalOrSecurityVisited = True
            if not criticalOrSecurityVisited:
                otherNonCompliantCount += 1
    
        return (criticalNonCompliantCount,
                securityNonCompliantCount,
                otherNonCompliantCount)

    def _sort_patch_inventory(self):
        if self.operating_system.lower() in ["debian", "ubuntu", "raspbian"]:
            self.patch_inventory.installed_pkgs.sort(key=lambda x: x.name)
            self.patch_inventory.installed_other_pkgs.sort(key=lambda x: x.name)
            self.patch_inventory.installed_rejected_pkgs.sort(key=lambda x: x.name)
            self.patch_inventory.installed_pending_reboot_pkgs.sort(key=lambda x: x.name)
            self.patch_inventory.missing_pkgs.sort(key=lambda x: x.name)
            self.patch_inventory.failed_pkgs.sort(key=lambda x: x.name)
            self.patch_inventory.not_applicable_pkgs.sort(key=lambda x: x.name)
        else:
            self.patch_inventory.installed_pkgs.sort()
            self.patch_inventory.installed_other_pkgs.sort()
            self.patch_inventory.installed_rejected_pkgs.sort()
            self.patch_inventory.installed_pending_reboot_pkgs.sort()
            self.patch_inventory.missing_pkgs.sort()
            self.patch_inventory.failed_pkgs.sort()

    def _get_package_compliance_content(self):
        """
        :return: return the level 2 content for patch compliance
        """
        ret = []
        self._sort_patch_inventory()

        for pkgtup in self.patch_inventory.installed_pkgs:
            ret.append(self.get_package_compliance_pkg("COMPLIANT", "Installed", pkgtup))

        for pkgtup in self.patch_inventory.installed_other_pkgs:
            ret.append(self.get_package_compliance_pkg("COMPLIANT", "InstalledOther", pkgtup))

        for pkgtup in self.patch_inventory.installed_rejected_pkgs:
            ret.append(self.get_package_compliance_pkg("NON_COMPLIANT", "InstalledRejected", pkgtup))

        for pkgtup in self.patch_inventory.installed_pending_reboot_pkgs:
            ret.append(self.get_package_compliance_pkg("NON_COMPLIANT", "InstalledPendingReboot", pkgtup))

        if self.upload_na_compliance:
            self.patch_inventory.not_applicable_pkgs.sort()
            for pkgtup in self.patch_inventory.not_applicable_pkgs:
                ret.append(self.get_package_compliance_pkg("COMPLIANT", "NotApplicable", pkgtup))

        for pkgtup in self.patch_inventory.missing_pkgs:
            ret.append(self.get_package_compliance_pkg("NON_COMPLIANT", "Missing", pkgtup))

        for pkgtup in self.patch_inventory.failed_pkgs:
            ret.append(self.get_package_compliance_pkg("NON_COMPLIANT", "Failed", pkgtup))

        return ret

    def get_package_compliance_pkg(self, compliance_or_not, state, package):
        """
        :param compliance_or_not: COMPLIANT OR NON_COMPLIANT
        :param state: package state, i.e.
                      installed, installed other, not applicable, missing, failed
        :param package: yum package from us
        :return: dict formatted for inventory
        """
        id = get_package_id(self.operating_system, package)
        title = get_package_title(self.operating_system, package)
        patch_severity = get_package_patch_severity(self.operating_system, package)
        severity = get_package_severity(self.operating_system, package)
        classification = get_package_classification(self.operating_system, package)
        cve_ids = get_package_cves(self.operating_system, package)
        ret = {
            "Id": id,
            "Title": title,
            "Severity": severity,
            "Status": compliance_or_not,
            "PatchBaselineId": self.baseline_id,
            "PatchState": state,
            "PatchGroup": self.patch_group,
            "DocumentName": "",
            "DocumentVersion": "",
            "InstalledTime": format_package_installed_time(state, package),
            "Classification": classification,
            "PatchSeverity": patch_severity or ""
        }

        if cve_ids and (state == "Missing" or state == "Failed"):
            ret["CVEIds"] = cve_ids

        if self.install_override_list:
            ret["InstallOverrideList"] = self.install_override_list

        return ret

    def _get_installation_time(self, pkg):
        """
        Method to find the installed time of an package. The order of checking installed time:
        1. Get installed date from package manager contained in package object if not proceed to next step.
        2. Get installed date from patch status file saved in the local system if not proceed to next step.
        3. None
        :param pkg: The package.
        :return: Installation time in epoch seconds.
        """

        if getattr(pkg, 'installed_time', None) is not None:
            return int(float(pkg.installed_time))

        package_state = self.patch_states_configuration.patch_states
        title = get_package_title(self.operating_system, pkg)
        try:
            return int(float(package_state[title][PatchStatesConfigurationKeys.INSTALLED_TIME]))
        except:
            return None

    def _get_last_no_reboot_operation_time(self):
        """0
        Method to get last reboot patching install operation time datetime format, returns None if not applicable
        :return:
        """

        if self.patch_inventory.operation_type.lower() == OperationType.INSTALL and\
                self.reboot_option == RebootOption.NO_REBOOT:
            return self.end_time

        last_no_reboot_install_operation_time = self.patch_states_configuration.last_no_reboot_install_operation_time
        if last_no_reboot_install_operation_time and last_no_reboot_install_operation_time != 0:
            return datetime.datetime.fromtimestamp(float(last_no_reboot_install_operation_time))

    def retrieve_previous_pending_reboot_patches(self):
        installed_pkgs = self.patch_inventory.installed_pkgs + self.patch_inventory.installed_other_pkgs + self.patch_inventory.installed_rejected_pkgs
        installed_pkgs_dict = {}
        for pkg in installed_pkgs:
            installed_pkgs_dict[get_package_title(self.operating_system, pkg)] = pkg

        previous_installed_pending_reboot_patches_dict = self.patch_states_configuration.get_pending_reboot_patches()
        result = {}
        for title, patch_state in previous_installed_pending_reboot_patches_dict.items():
            if title in installed_pkgs_dict.keys():
                result[title] = installed_pkgs_dict[title]
        return result

    def retrieve_pending_reboot_kernel(self):
        installed_pkgs = self.patch_inventory.installed_pkgs + self.patch_inventory.installed_other_pkgs + self.patch_inventory.installed_rejected_pkgs
        installed_pkgs_dict = {}
        for pkg in installed_pkgs:
            installed_pkgs_dict[get_package_title('amazon_linux_2', pkg)] = pkg

        previous_installed_pending_reboot_kernel = self.patch_states_configuration.pending_reboot_kernel
        result = {}
        for title, patch_state in previous_installed_pending_reboot_kernel.items():
            if title in installed_pkgs_dict.keys():
                result[title] = installed_pkgs_dict[title]
        self.patch_states_configuration.clean_pending_reboot_kernel()
        return result

def format_package_installed_time(state, package):
    """
    Method to format package's installed time
    :param state: package's state, which could be Installed/InstalledOther/InstalledRejected/NotApplicable/Missing/Failed
    :param package: package object, which could contains installed_time property in the epoch seconds
    :return: formatted installed time or empty string
    """
    # Only add installed_time for Installed/InstalledOther/InstalledRejected packages
    # And "InstalledTime" is not always applicable
    if 'installed' in state.lower() and package.installed_time:
        try:
            if isinstance(package.installed_time, type("")):
                return time.strftime(Compliance_string_formatting.INSTALL_TIME, time.gmtime(float(package.installed_time)))

            return time.strftime(Compliance_string_formatting.INSTALL_TIME, time.gmtime(package.installed_time))
        except Exception as e:
            # Only log the exception if exists
            logger.warning("Unable to format the timestamp: %s", package.installed_time)
    return ""


def generate_sha256(content):
    sha256 = hashlib.sha256()
    # the json.dumps(content) can be unicode, so encode it
    sha256.update(json.dumps(content).encode("utf-8"))
    return sha256.hexdigest()

def get_packages_installed_on_current_run(installed_packages_before_install, installed_packages_after_install):
    """
    Method to be used in all sub packages
    :param installed_packages_before_install: a list of packages installed before performing Install operation
    :param installed_packages_after_install: a list of packages installed after performing Install operation
    :return: a set of packages installed by Patch Manager
    """
    return set(installed_packages_after_install) - set(installed_packages_before_install)

def _filter_installed_pending_reboot_pkgs(original_pkgs_list, installed_pending_reboot_pgks_dict, operating_system):
    '''
    :param original_pkgs_list: The packages list from which to remove installed pending reboot packages.
    :param installed_pending_reboot_pgks_list: The package list to add installed pending reboot packages.
    :param last_reboot_time: last reboot time in epoch seconds.
    :return: updated_pkgs_list
    '''

    updated_pkgs_list = []

    for pkg in original_pkgs_list:
        if get_package_title(operating_system, pkg) not in installed_pending_reboot_pgks_dict.keys():
            updated_pkgs_list.append(pkg)

    return updated_pkgs_list

