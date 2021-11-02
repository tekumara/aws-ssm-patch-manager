import logging

from patch_common.constant_repository import OperationType, RebootOption, PatchStates, ExitCodes, REBOOT_EXIT_CODES
from patch_common.system_utils import get_last_reboot_time

logger = logging.getLogger()


def needs_reboot(reboot_option, patch_states_configuration, operation, patching_exit_code, operating_system=None):

    if operation.lower() == OperationType.SCAN or reboot_option == RebootOption.NO_REBOOT:
        return False

    if has_pending_reboot_patches(patch_states_configuration) and _is_last_operation_after_last_reboot_time(patch_states_configuration.last_no_reboot_install_operation_time, operating_system):
        return True

    return patching_exit_code in REBOOT_EXIT_CODES

def _is_last_operation_after_last_reboot_time(last_no_reboot_operation_time, operating_system=None):
    last_reboot_time = get_last_reboot_time(operating_system)

    # If no value provided, treating it as true
    if last_no_reboot_operation_time == None or last_no_reboot_operation_time == 0:
        return True
    logger.info("Last No Reboot Operation Time: %s", last_no_reboot_operation_time)
    logger.info("System Last Reboot Time: %s", last_reboot_time)

    return float(last_no_reboot_operation_time) > float(last_reboot_time)

def has_pending_reboot_patches(patch_states_configuration):
    if patch_states_configuration is None:
        return False
    return len(patch_states_configuration.get_pending_reboot_patches()) != 0
