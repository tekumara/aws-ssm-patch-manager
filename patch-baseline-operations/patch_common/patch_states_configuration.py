from patch_common.constant_repository import PatchStatesConfigurationKeys
from patch_common.exceptions import PatchManagerError
from patch_common.constant_repository import ExitCodes, RebootOption, LivePatch
from patch_common.constant_repository import CONFIGURATION_PATH, CONFIGURATION_DIRECTORY, KERNEL_STATE_PATH, KERNEL_STATE_DIRECTORY
from patch_common.package_matcher import get_format, get_package_title, get_package_id
from patch_common import system_utils
import datetime
import logging
import os
import json
import shutil

logger = logging.getLogger()

# Patch Name matching name.arch.epoach.version.release
PATCH_NAME_PATTERN = "(.*?)\.(.*?)\.(.*?)\.(.*?)\.(.*)"

"""
PatchStatesConfiguration Class is used to interact with the data stored in /var/log/amazon/ssm/patch-configuration/configuration.json
The format of the file will be:
{
    lastNoRebootOperationTime: 1255
    patchStates: {
        patch1_title: {
            id: patch1_id,
            state: patch1_state,
            installedTime: patch1_installed_time
        },
        patch2_title: {
            id: patch2_id,
            state: patch2_state,
            installedTime: patch2_installed_time
        }
    }
}
"""


class PatchStatesConfiguration:
    def __init__(self):
        self.patch_states = {}
        self.last_no_reboot_install_operation_time = 0
        if os.path.exists(CONFIGURATION_PATH) and os.stat(CONFIGURATION_PATH).st_size != 0:
            try:
                with open(CONFIGURATION_PATH, 'r') as f:
                    logger.info("Reading Local Configuration file")
                    self.patch_state_list = json.load(f)
                    self.last_no_reboot_install_operation_time = self.patch_state_list.get(PatchStatesConfigurationKeys.LAST_NO_REBOOT_INSTALL_OPERATION_TIME, 0)
                    self.patch_states = self.patch_state_list.get(PatchStatesConfigurationKeys.PATCH_STATES, {})
                    logger.info(self.patch_states)
                    self._validate_configuration()
            except Exception as e:
                logger.error("Failed parse the configuration file: %s", e)
                os.remove(CONFIGURATION_PATH)
                self.patch_states = {}
                self.last_no_reboot_install_operation_time = 0
        self.pending_reboot_kernel = {}
        self.get_pending_reboot_kernel()

    def update_configuration(self, operating_system, patch_inventory, lastNoRebootInstallOperationTime):
        if not os.path.exists(CONFIGURATION_DIRECTORY):
            os.makedirs(CONFIGURATION_DIRECTORY)
        with open(CONFIGURATION_PATH, 'w+') as f:
            logger.info("Updating local configuration file")
            config = self._convert_patch_inventory_to_patch_configuration(operating_system, patch_inventory, lastNoRebootInstallOperationTime)
            json.dump(config, f)
            self.last_no_reboot_install_operation_time = lastNoRebootInstallOperationTime
            self.patch_states = config.get(PatchStatesConfigurationKeys.PATCH_STATES, {})

    def get_pending_reboot_patches(self):
        pending_reboot_patches = {}
        for k, v in self.patch_states.items():
            if v.get(PatchStatesConfigurationKeys.STATE, "") == "InstalledPendingReboot":
                pending_reboot_patches[k] = v

        return pending_reboot_patches

    def _validate_configuration(self):
        self._validate_last_no_reboot_time()
        return

    def _validate_last_no_reboot_time(self):
        now = system_utils.get_total_seconds((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)))
        if float(self.last_no_reboot_install_operation_time) < 0 or float(self.last_no_reboot_install_operation_time) > now:
            logger.error("Unable to parse the last no reboot operation time, the content of the file is %s", self.patch_state_list)
            shutil.rmtree(CONFIGURATION_DIRECTORY)
            raise PatchManagerError("LastNoRebootInstallOperation time has been damaged,"
                                    "please reboot system to keep it compliant", ExitCodes.CONFIGURATION_FILE_ERROR)

    # Covert Package_Inventory Object to Patch Configuration format
    def _convert_patch_inventory_to_patch_configuration(self, operating_system, patch_inventory, lastNoRebootInstallOperationTime):
        patch_configuration = {
            PatchStatesConfigurationKeys.PATCH_STATES: {},
            PatchStatesConfigurationKeys.LAST_NO_REBOOT_INSTALL_OPERATION_TIME: lastNoRebootInstallOperationTime
        }
        self._append_patch_state(operating_system, patch_inventory.installed_pkgs, "Installed", patch_configuration)
        self._append_patch_state(operating_system, patch_inventory.installed_other_pkgs, "InstalledOther", patch_configuration)
        self._append_patch_state(operating_system, patch_inventory.installed_rejected_pkgs, "InstalledRejected", patch_configuration)
        self._append_patch_state(operating_system, patch_inventory.installed_pending_reboot_pkgs, "InstalledPendingReboot", patch_configuration)
        logger.info(patch_configuration)
        return patch_configuration

    def _append_patch_state(self, operating_system, packages, state, patch_configuration):
        for package in packages:
            title = get_package_title(operating_system, package)
            patch_state = {
                PatchStatesConfigurationKeys.ID: get_package_id(operating_system, package),
                PatchStatesConfigurationKeys.INSTALLED_TIME: package.installed_time,
                PatchStatesConfigurationKeys.STATE: state
            }
            patch_configuration[PatchStatesConfigurationKeys.PATCH_STATES][title] = patch_state


    def pkg_in_installed_pending_reboot_state(self, na):
        """
        na: (name, arch) tuple
        """
        pending_reboot_patches = self.get_pending_reboot_patches()
        for k, v in pending_reboot_patches.items():
            if v.get(PatchStatesConfigurationKeys.ID, "") == ".".join(na):
                return True
        return False

    def remove_kernel_from_patch_state_configuration(self, kernel_na):
        """
        kernel_na: (name, arch)
        """
        ret_patch_states = {}
        if len(self.get_pending_reboot_patches().items()) > 0:
            for k, v in self.patch_states.items():
                if v[PatchStatesConfigurationKeys.ID] != ".".join(kernel_na):
                    ret_patch_states[k] = v
        self.patch_states = ret_patch_states


    def remove_livepatches_from_patch_state_configuration(self):
        """
        Remove the livepatches from the PatchStatesConfiguration patch_states field
        """
        ret_patch_states = {}
        if len(self.get_pending_reboot_patches().items()) > 0:
            for k, v in self.patch_states.items():
                if not v[PatchStatesConfigurationKeys.ID].startswith(LivePatch.LIVEPATCH_PREFIX):
                    ret_patch_states[k] = v
        self.patch_states = ret_patch_states


    def _append_kernel_state(self, kernel_candidate):
        title = get_package_title('amazon_linux_2', kernel_candidate)
        kernel_state = {
            PatchStatesConfigurationKeys.ID: get_package_id('amazon_linux_2', kernel_candidate),
            PatchStatesConfigurationKeys.INSTALLED_TIME: kernel_candidate.installed_time,
            PatchStatesConfigurationKeys.STATE: 'InstalledPendingReboot'
        }
        self.pending_reboot_kernel[title] = kernel_state


    def get_pending_reboot_kernel(self):
        """
        Check kernel-livepatch.json file on the instance to decide whether the kernel should be put into installed_pending_reboot state.
        """
        # If not amzn2, return
        if os.path.exists(KERNEL_STATE_PATH) and os.stat(KERNEL_STATE_PATH).st_size != 0:
            try:
                with open(KERNEL_STATE_PATH, 'r') as f:
                    self.pending_reboot_kernel = json.load(f)
                    logger.info(self.pending_reboot_kernel)
            except Exception as e:
                logger.error("Failed to parse the kernel that became compliant after applying all the livepatches: %s", e)
                os.remove(KERNEL_STATE_PATH)


    def save_pending_reboot_kernel_info(self, kernel_candidate):
        """
        This method saves the kernel_candidate information into the local file.
        """
        if not os.path.exists(KERNEL_STATE_DIRECTORY):
            os.makedirs(KERNEL_STATE_DIRECTORY)
        with open(KERNEL_STATE_PATH, 'w+') as f:
            self._append_kernel_state(kernel_candidate)
            json.dump(self.pending_reboot_kernel, f)


    def clean_pending_reboot_kernel(self):
        """
        To remove the kernel-livepatch.json after we put kernel back to the installed pending reboot status.
        """
        if os.path.exists(KERNEL_STATE_PATH) and os.stat(KERNEL_STATE_PATH).st_size != 0:
            os.remove(KERNEL_STATE_PATH)
