import os.path
import re
import logging
from patch_common.constant_repository import OperatingSystem, ExitCodes
from patch_common.cli_invoker import CLIInvoker, CLIInvokerException
from patch_common.exceptions import PatchManagerError

LOGGER = logging.getLogger()

# File Constants
OS_RELEASE_FILE = "/etc/os-release"
SYSTEM_RELEASE_FILE = "/etc/system-release"
CENTOS_RELEASE_FILE = "/etc/centos-release"
REDHAT_RELEASE_FILE = "/etc/redhat-release"

# Raw Operating System Constants
# Mirrors constants from https://code.amazon.com/packages/PatchBaselineService/blobs/mainline/--/src/com/amazonaws/patch/baseline/instance/InstanceInfoConverter.java
OPERATING_SYSTEM_NAME_MAP = {
    "Amazon Linux AMI": OperatingSystem.AMAZON_LINUX,
    "Amazon Linux Bare Metal": OperatingSystem.AMAZON_LINUX,
    "Amazon Linux": OperatingSystem.AMAZON_LINUX2,
    "CentOS Linux": OperatingSystem.CENTOS,
    "CentOS": OperatingSystem.CENTOS,
    "Debian GNU/Linux": OperatingSystem.DEBIAN,
    "Raspbian GNU/Linux": OperatingSystem.RASPBIAN,
    "Ubuntu": OperatingSystem.UBUNTU,
    "Oracle Linux Server": OperatingSystem.ORACLE,
    "Red Hat Enterprise Linux Server": OperatingSystem.RED_HAT,
    "Red Hat Enterprise Linux": OperatingSystem.RED_HAT,
    "SLES": OperatingSystem.SUSE,
    "SLES_SAP": OperatingSystem.SUSE
}

# System Release Constants
SUPPORTED_SYSTEM_RELEASE_OPERATING_SYSTEMS = ["Amazon", "Red Hat", "CentOS", "SLES", "Raspbian", "Oracle"]

# Regex
NAME_REGEX = "NAME=\"*\""


def get_operating_system(document_step):
    """
    Function to get the current Operating System we are executing on.

    We are copying over the existing Agent logic to support older Agent versions here, however newer agent versions will
    provide the AWS_SSM_PLATFORM_NAME environment variable which will handle getting the platform name. If there is ever a
    customer issue related to this calculation, please inform the agent team and advise the customer to update the agent.

    :param: document_step - Either PatchMacOS or PatchLinux
    :return:
    """
    if document_step == "PatchMacOS":
        # Operating System is always MacOS for this document step
        return OperatingSystem.MACOS

    # Check for environment variable used by newer agents first
    operating_system = _get_operating_system_from_agent()
    if not operating_system:
        # Agent is an old version, use implementation as of 02/09/2020
        operating_system = _get_operating_system_from_local()

    return operating_system


def _get_operating_system_from_agent():
    """
    Check environment variable provided by the Agent to get the Operating System of the host
    :return: Operating System used by Patch Model
    """
    agent_platform_name = os.getenv("AWS_SSM_PLATFORM_NAME")
    if agent_platform_name:
        return _get_patch_operating_system_from_raw(agent_platform_name)

    return None


def _get_operating_system_from_local():
    """
    Copy of Agent OS parsing logic as of 12/05/2020
    Checks for existence and parses various operating system level files to determine the operating system
    :return: Operating System used by Patch Model
    """
    # Mirroring logic from https://code.amazon.com/packages/Amazon-ssm-agent/blobs/cf6b265386c84afbe5ae7c68508fd4ad6e041602/--/agent/platform/platform_unix.go#L73-L212
    # Check CentOS file first
    if os.path.exists(CENTOS_RELEASE_FILE):
        return OperatingSystem.CENTOS
    # Check OS Release File
    elif os.path.exists(OS_RELEASE_FILE):
        with open(OS_RELEASE_FILE) as os_release_contents:
            pattern = re.compile(NAME_REGEX)
            for line in os_release_contents.readlines():
                if pattern.match(line):
                    return _get_patch_operating_system_from_raw(line)
    # Check System Release File
    elif os.path.exists(SYSTEM_RELEASE_FILE):
        with open(SYSTEM_RELEASE_FILE) as system_release_file:
            system_release_contents = system_release_file.read()
            return _get_patch_operating_system_from_system_release(system_release_contents)
    # Check Redhat Release File
    elif os.path.exists(REDHAT_RELEASE_FILE):
        return OperatingSystem.RED_HAT
    else:
        # Try to get OS from uname command
        operating_system = _attempt_get_os_from_uname()
        if operating_system:
            return operating_system

        # Try to get OS from lsb_release command
        operating_system = _attempt_get_os_from_lsb_release()
        if operating_system:
            return operating_system

        # Unable to get OS from all sources, raise Error
        raise PatchManagerError("This Operating System is not supported by Patch Manager",
                                ExitCodes.BASELINE_OVERRIDE_UNSUPPORTED_OPERATING_SYSTEM)


def _get_patch_operating_system_from_raw(raw_os_name):
    longest_match_key = ""
    for key in OPERATING_SYSTEM_NAME_MAP.keys():
        if key in raw_os_name and len(key) > len(longest_match_key):
            longest_match_key = key

    if longest_match_key in OPERATING_SYSTEM_NAME_MAP:
        return OPERATING_SYSTEM_NAME_MAP[longest_match_key]
    else:
        raise Exception("Operating System is not Supported by Patch Manager: " + raw_os_name)


def _get_patch_operating_system_from_system_release(raw_system_release):
    for os_title in SUPPORTED_SYSTEM_RELEASE_OPERATING_SYSTEMS:
        if os_title in raw_system_release:
            raw_os_name = raw_system_release.split("release")[0].strip()
            return _get_patch_operating_system_from_raw(raw_os_name)


def _attempt_get_os_from_uname():
    try:
        raw_result = CLIInvoker(comd=["/usr/bin/uname", "-sr"]).execute()[0].strip()
        return _get_patch_operating_system_from_raw(raw_result.split(" ")[0])
    except:
        LOGGER.warning("Unable to grab Operating System Name from uname Command")
        return None


def _attempt_get_os_from_lsb_release():
    try:
        raw_result = CLIInvoker(comd=["lsb_release", "-i"]).execute()[0].strip()
        return _get_patch_operating_system_from_raw(raw_result)
    except:
        LOGGER.warning("Unable to grab Operating System Name from lsb_release Command")
