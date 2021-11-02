import os
import shutil
import sys
import errno
import logging
import stat
import subprocess
import uuid
import time
from patch_common.cli_invoker import CLIInvoker
from patch_common.boot_time_parser import BootTimeParser

# initialize logging
LOGGER_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOGGER_DATEFORMAT = "%m/%d/%Y %X"
LOGGER_LEVEL = logging.INFO
LOGGER_STREAM = sys.stdout

logging.basicConfig(format=LOGGER_FORMAT, datefmt=LOGGER_DATEFORMAT, level=LOGGER_LEVEL, stream=LOGGER_STREAM)
logger = logging.getLogger()

tmp_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations/")
reboot_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-194/")
reboot_with_failure_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-195/")
reboot_with_dependency_failure_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-196/")

REBOOT_CODE_MAP = {
    194: reboot_dir,
    195: reboot_with_failure_dir,
    196: reboot_with_dependency_failure_dir
}

ERROR_CODE_MAP = {
    154: "Unable to create dir: %s",
    156: "Error loading patching payload"
}

def get_instance_online_timestamp(document_step):
    if document_step == "PatchMacOS":
        logger.info("Getting system uptime for MacOS.")
        result = CLIInvoker(comd = ["sysctl", "kern.boottime"], psr=BootTimeParser()).execute()
        logger.info("System uptime found to be %s seconds since Linux Epoch".format(str(result[0])))
        reboot_timestamp_in_epoch_seconds = float(result[0])
        return reboot_timestamp_in_epoch_seconds
    else:
        f = open("/proc/uptime", "r")
        uptime_seconds = float(f.readline().split()[0])
        f.close()
        # Subtract uptime from current time (in seconds since linux epoch) to get the timestamp of the reboot
        reboot_timestamp_in_epoch_seconds = time.time() - uptime_seconds
        return reboot_timestamp_in_epoch_seconds

def create_timestamp_file(reboot_dir):
    ts_file = open(reboot_dir + "timestamp", "w+")
    ts_file.write(str(time.time()))
    ts_file.close()

def get_reboot_folder_creation_timestamp(dirname):
    uptime_seconds = time.time()
    try:
        with open(dirname + "timestamp", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
    except Exception as e:
        create_timestamp_file(dirname)
    finally:
        return uptime_seconds

def create_dir(dir_path):
    dirpath = os.path.abspath(dir_path)
    # the dir should NOT exists, but do the check anyway
    if not os.path.exists(dirpath):
        try:
            os.makedirs(dirpath)
        except OSError as e:  # Guard against race condition
            if e.errno != errno.EEXIST:
                raise e
        except Exception as e:
            logger.error("Unable to create dir: %s", dirpath)
            logger.exception(e)
            abort(154, (dirpath))

def remove_dir(dir_path):
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)

def exit(code):
    if code in REBOOT_CODE_MAP:
        reboot_dir = REBOOT_CODE_MAP.get(code)
        create_dir(reboot_dir)
        create_timestamp_file(reboot_dir) # here we create the timestamp file to mark when we asked to exit w reboot
        # Change code to the reboot code to signal the agent to reboot.
        code = 194
    else:
        # No reboot behavior, remove any possible existing reboot directory
        for dir in REBOOT_CODE_MAP.values():
            remove_dir(dir)
    remove_dir(tmp_dir)
    sys.exit(code)

def shell_command(cmd_list):
    with open(os.devnull, "w") as devnull:
        p = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=devnull)
        (std_out, _) = p.communicate()
        if not type(std_out) == str:
            std_out = std_out.decode("utf-8")
        return std_out, p.returncode

def abort(error_code, params = ()):
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    sys.stderr.write(ERROR_CODE_MAP.get(error_code) % params)
    sys.exit(error_code)

# When an install occurs and the instance needs a reboot, the agent restarts our plugin.
# Check if these folders exist to know how to succeed or fail a command after a reboot.
def check_dir_and_exit(document_step, dir, exit_code):
    if not os.path.exists(dir):
        return
    num_files = len(os.listdir(dir))
    if num_files < 5:
        create_dir(dir + "/" + str(num_files) + "/")  # to cap the number of retries
        instance_online_timestamp = get_instance_online_timestamp(document_step)
        reboot_folder_creation_timestamp = get_reboot_folder_creation_timestamp(dir)
        # This captures cases where the agent failed to reboot. The reboot folder is created on exit, right before triggering a reboot to the agent.
        # This comparison is trying to capture if the reboot folder creation time occurred after the last reboot. If it did, then the agent failed to reboot.
        if instance_online_timestamp < reboot_folder_creation_timestamp - 3:
            logger.info("Patching payload detected a missed reboot, issuing exit code 194 to retry reboot")
            sys.exit(194)
    else:
        exit_code = 3 # exit code meaning we tried rebooting and failed
        logger.error("Patching payload failed to reboot 4x in a row, reporting failure code 3")

    shutil.rmtree(dir)
    sys.exit(exit_code)

def check_dir_and_exit_for_reboot_options(document_step):
    check_dir_and_exit(document_step, reboot_dir, 0)
    check_dir_and_exit(document_step, reboot_with_failure_dir, 1)
    check_dir_and_exit(document_step, reboot_with_dependency_failure_dir, 2)


def change_dir():
    os.chdir(tmp_dir)
    sys.path.insert(0, tmp_dir)


def execute(module_name, *argv):
    document_step = argv[0]
    check_dir_and_exit_for_reboot_options(document_step)
    change_dir()

    try:
        logger.info("Attempting to import entrance file %s", module_name)
        entrance_module = __import__(module_name)
        exit(   entrance_module.execute(*argv))
    except Exception as e:
        error_code = 156
        if hasattr(e, "error_code") and type(e.error_code) == int:
            error_code = e.error_code;
        logger.exception("Error loading entrance module.")
        logger.exception(e)
        abort(error_code)