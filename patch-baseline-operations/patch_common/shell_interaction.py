import os
import subprocess
import logging
import shutil
import sys

from patch_common.exceptions import PatchManagerError

logger = logging.getLogger()
tmp_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations/")
reboot_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-194/")
reboot_with_failure_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-195/")


def use_curl():
    output, has_curl = shell_command(["which", "curl"])
    if has_curl == 0:
        return True
    else:
        return False


def download_from_url(url, file_path):
    """
    Download provided url to provided path
    :param url: URL to be downloaded
    :param file_path: file path for the downloaded file
    :return: True for success, False otherwise
    """
    if use_curl():
        output, result = shell_command(["curl", "-o", file_path, url])
    else:
        output, result = shell_command(["wget", "-O", file_path, url])

    if result != 0:
        raise Exception("Could not download %s" % url)
    return result == 0


def shell_command(cmd_list):
    with open(os.devnull, "w") as devnull:
        p = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=devnull)
        (std_out, _) = p.communicate()
        if not type(std_out) == str:
            std_out = std_out.decode("utf-8")
        return (std_out, p.returncode)


def abort(pme=None):
    """
    Terminates the patching operation using the error code in the error, if any
    :type pme: PatchManagerError
    :param pme: the error, if any
    """
    error_code = 1
    if isinstance(pme, PatchManagerError):
        error_code = pme.error_code
    if pme:
        logger.exception("Patching operation has failed")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    sys.exit(error_code)


def restart_agent(operation_type, product, exit_code):
    if operation_type.lower() == "install" and exit_code == 194:
        if product.startswith("RedhatEnterpriseLinux7"):
            # In case the agent was interrupted by updates, restart it and schedule a reboot.
            shell_command(["shutdown", "-r", "3"])
            try:
                shell_command(["systemctl", "start", "amazon-ssm-agent"])
            except Exception:
                pass
