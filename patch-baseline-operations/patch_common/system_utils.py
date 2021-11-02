import logging
import os
import time
import subprocess

from patch_common.constant_repository import ExitCodes
from patch_common.cli_invoker import CLIInvoker
from patch_common.exceptions import PatchManagerError
from patch_common.boot_time_parser import BootTimeParser

logger = logging.getLogger()


def get_last_reboot_time(operating_system=None):
    """
    Get last reboot time of the instance as time in seconds since the epoch.
    """
    uptime_file = '/proc/uptime'

    if not operating_system is None and operating_system == "macos":
        # MacOS doesn't have the /proc/uptime file. Try getting the last reboot time (in seconds) from parsing the output 
        # of the "sysctl kern.boottime" command
        try:
            logger.info("Getting last reboot time for MacOS.")
            result = CLIInvoker(comd = ["sysctl", "kern.boottime"], psr=BootTimeParser()).execute()
            reboot_time = int(result[0])
            logger.info("Reboot in seconds since Linux Epoch: %s".format(str(result[0])))
        except:
            error_message = "Unable to determine the last reboot time using sysctl command".format(uptime_file)
            logger.error(error_message)
            raise PatchManagerError(error_message, ExitCodes.UPTIME_COULDNT_FIND)
        
        if reboot_time < 0:
            error_message = "Error with the last reboot time obtained from sysctl command".format(uptime_file)
            logger.error(error_message)
            raise PatchManagerError(error_message, ExitCodes.UPTIME_COULDNT_FIND)

        return reboot_time

    elif not os.path.isfile(uptime_file):
        error_message = "Last reboot time couldn't be determined, as %s is not present".format(uptime_file)
        logger.error(error_message)
        raise PatchManagerError(error_message, ExitCodes.UPTIME_COULDNT_FIND)

    with open(uptime_file, 'r') as f:
        uptime_seconds = int(float(f.readline().split()[0]))
        epoch_time = int(time.time())
        reboot_time = epoch_time - uptime_seconds

        if reboot_time < 0:
            error_message = "Reboot time couldn't be determined due to corrupt entry in %s".format(uptime_file)
            logger.error(error_message)
            raise PatchManagerError(error_message, ExitCodes.UPTIME_COULDNT_FIND)

    return reboot_time

# Python 2.6 doesn't have total_seconds() method for datetime.timedelta object, create customized method
# to calculate secs
def get_total_seconds(datetime):
    return datetime.seconds + datetime.days * 24 * 60 * 60



