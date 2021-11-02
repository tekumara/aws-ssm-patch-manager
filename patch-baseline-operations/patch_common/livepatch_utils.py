import logging
import os
import sys
import re
import calendar
from datetime import date, datetime
from patch_common.constant_repository import LivePatch, RebootOption, Metrics
from patch_common.exceptions import PatchManagerError
from patch_common.shell_interaction import shell_command
from patch_common.rpm_version import compare
from patch_common.livepatch_constant import LIVEPATCH_SCENARIOS
from patch_common.metrics_service import set_runtime_metric

sys.path.insert(0, "/usr/share/yum-cli")

logger = logging.getLogger()

def modify_kernel_and_livepatch_status(oper_sys, reboot_option, inventory, patch_states_configuration, override_list=None):
    """
    This method decides a set of commands to take if user enables live patching.
    The goal is if user has not upgraded to a certain version of kernel because of some unforceable reason, their
    fleet should be able to report as compliant if they enable live patching and those livepatches
    addresses all the CVEs which would have been addressed if fleet upgrade to the newer kernel.

    We instruct our user to specify baseline approval rule to approve ONLY security updates with Important/Critical severity

    #TODO Needs to honor the severity defined in a baseline, thus if there is a medium livepatch and baseline specify 
    only approve important/critial livepatch, the instance should still be reported as compliant

    There are three actions to take given the kernel and livepatch status combination:
    1. Initialize a CVE check
    2. Put the kernel and kernel-livepatch pkg into the correct pkgs(e.g remove kernel from missing_pkgs if cve check passed.etc)
    3. Clean up kernel & livepatches from patch_state_configuration
    """

    if not amazon_linux_2(oper_sys):
        return

    if not kernel_livepatch_plugin_enabled():
        # If kernel_livepatch_plugin_not_enabled or kpatch_runtime_service_not_enabled, we follow the existing patching flow
        # User needs to run the enable document before they can use live patch
        logger.info("Kernel livepatch currently not enabled for the instance.")
        return

    if kpatch_runtime_service_enabled():
        default_kernel_vra = get_applied_kernel_vra_tuple()

        logger.info("Kernel live patching currently enabled on the instance")
        logger.info("Kernel currently running on kernel-%s-%s.%s", default_kernel_vra[0], default_kernel_vra[1], default_kernel_vra[2])
        set_runtime_metric(Metrics.KERNEL_LIVE_PATCH_ENABLED)

        operation_type = inventory.operation_type.lower()
        if operation_type == "install" and reboot_option == RebootOption.REBOOT_IF_NEEDED:
            logger.info("Install with RebootIfNeeded. Live patching not required")
            return

        if kernel_supports_live_patching(default_kernel_vra) and kernel_within_support_lifetime():
            # get the current kernel's livepatch candidate from pkg lists 
            livepatch_name = get_livepatch_pkg_name(default_kernel_vra)
            livepatch_na = (livepatch_name, 'x86_64')
            (livepatch_candidate, livepatch_candidate_status) = get_pkg_and_status_from_inventory(inventory, livepatch_na)
            kernel_na = ('kernel', 'x86_64')
            (kernel_candidate, kernel_candidate_status) = get_pkg_and_status_from_inventory(inventory, kernel_na)
            if livepatch_candidate_status == 'not found':
                logger.info("Unable to find any livepatch for the running kernel. Please make sure you have met all the requirements for kernel livepatching")
                return
            if kernel_candidate_status == 'not found':
                logger.info("""Unable to find any kernel for the running kernel. """) # Kernel should always be found, just in case
                return

            # Try to see if kernel or any livepatch exist in the patch state configuration
            # We need to always remove the livepatches from psc and modify kernel when necessary
            kernel_in_installed_pending_reboot = patch_states_configuration.pkg_in_installed_pending_reboot_state(kernel_na)
            livepatch_in_installed_pending_reboot = patch_states_configuration.pkg_in_installed_pending_reboot_state(livepatch_na)

            #construct action key
            action_key = (kernel_candidate_status, kernel_in_installed_pending_reboot, livepatch_candidate_status, livepatch_in_installed_pending_reboot)
            action = LIVEPATCH_SCENARIOS.get(action_key, "no_cve_check")

            if action == 'do_cve_check':
                logger.info('Comparing the CVEs addressed by livepatches and CVEs addressed in kernel patch')
                kernel_candidate_vra_tup = (kernel_candidate.version, kernel_candidate.release, kernel_candidate.arch)
                # cve check, decide whether kernel could be considered compliant if all the livepatches for that kernel are applied
                kernel_compliant = kernel_compliant_after_applying_livepatch(kernel_candidate_vra_tup)
                if kernel_compliant:
                    logger.info('CVE comparison shows the kernel is compliant')
                    set_runtime_metric(Metrics.KERNEL_LIVE_PATCH_COMPLIANT)
                    remove_kernel_from_list(inventory, 'missing_pkgs', kernel_candidate)
 
                    if (operation_type == 'scan' and kernel_candidate_status == 'missing') or \
                        (override_list is not None and kernel_candidate_status == 'missing'):
                        add_kernel_to_list(inventory, 'installed_pkgs', kernel_candidate)

                    if operation_type.lower() == 'install' and reboot_option == RebootOption.NO_REBOOT:
                        remove_kernel_from_list(inventory, 'current_installed_pkgs', kernel_candidate)

                    # Whenever we mark kernel as installed, we keep a copy
                    # of that information in the kernel-livepatch.json so that when user disables livepatching,
                    # we have a way of setting kernel back to installed_pending_reboot
                    if kernel_candidate_status not in [ 'missing', 'failed' ]:
                        patch_states_configuration.save_pending_reboot_kernel_info(kernel_candidate)
                    patch_states_configuration.remove_kernel_from_patch_state_configuration(kernel_na)

                else:
                    logger.debug('CVE comparison indicates the kernel is not compliant')
            else:
                logger.debug('The current running kernel is missing live patches.')
        else:
            logger.info("CVE check is not performed because the current version of the Linux kernel is no longer being provided with Live Patches, please reboot into the newer kernel to receive a stream of livepatches.")

        remove_all_livepatches_from_list(inventory, 'current_installed_pkgs')
    
    else:
        """
        This is not a common case when user enables kernel-livepatch plugin but have kpatch.service disabled.
        In case this happens, we don't want to show the false installed information for livepatches, but these patches
        could still be loaded. For the first iteration, going to display a warning to user. This is by no means our suggested
        workflow to our customer when they go on this path, they are on their own.
        """
        # remove_current_kernel_livepatches_from_all_lists(inventory)
        logger.warn("kpatch.service is installed but not enabled. Please make sure kpatch.service is enabled while using Patch Manager live patching otherwise you may see livepatches as installed but are not in effect. You can run `kpatch list` on the instance to verify installed livepatches are correctly loaded")

    # General clean up work for all cases because we don't care about livepatches for other kernel versions:
    # 1. Remove all livepatch that is not for current running kernel from pkg lists
    # 2. Remove all livepatch that is not for current running kernel from the patch_state_configuration.patch_states
    remove_not_current_kernel_livepatches_from_all_lists(inventory)
    patch_states_configuration.remove_livepatches_from_patch_state_configuration()
    



def should_put_kernel_back_to_pending_reboot(operating_system, patch_states_configuration):
    if not amazon_linux_2(operating_system):
        return False
    if kernel_livepatch_plugin_enabled() and kpatch_runtime_service_enabled():
        return False
    if patch_states_configuration.pending_reboot_kernel and len(patch_states_configuration.pending_reboot_kernel) == 0:
        return False
    return True


def remove_not_current_kernel_livepatches_from_all_lists(inventory):
    """
    Remove the livepatches from ALL pkg lists if they are not for current kernel because we don't care about them
    """
    pkg_lists = ["installed_pkgs", "installed_other_pkgs", "missing_pkgs", "installed_rejected_pkgs", "failed_pkgs", "not_applicable_pkgs", "current_installed_pkgs"]
    for list_name in pkg_lists:
        if hasattr(inventory, list_name):
            remove_not_current_kernel_livepatches_from_list(inventory, list_name)

def remove_not_current_kernel_livepatches_from_list(inventory, list_name):
    """
    Remove the livepatches from a specific list if they are not for current kernel because we don't care about them
    
    inventory: a inventory of different lists of pkgs
    list_name: specific inventory list key, e.g: installed / installed_other etc
    livepatch_na: (name, arch) tuple for current kernel's livepatch
    """
    ret_pkgs = []
    if hasattr(inventory, list_name):
        ret_pkgs = remove_not_current_kernel_livepatches(getattr(inventory,list_name))
        setattr(inventory, list_name, ret_pkgs)

def remove_not_current_kernel_livepatches(pkgs):
    current_kernel_vra = get_applied_kernel_vra_tuple()
    livepatch_for_current_kernel = get_livepatch_pkg_name(current_kernel_vra)
    ret_pkgs = []
    if pkgs:
        for pkg in pkgs:
            # pass the livepatch pkg if they are not for current kernel
            if pkg.name and pkg.name.startswith(LivePatch.LIVEPATCH_PREFIX) and pkg.name not in livepatch_for_current_kernel:
                pass
            else:
                ret_pkgs.append(pkg)
    return ret_pkgs

def remove_all_livepatches_from_list(inventory, list_name):
    """
    Remove all the livepatches from current_installed_pkgs list because anything in this list later on will be marked as pending_reboot
    """
    ret_pkgs = []
    if inventory and hasattr(inventory, list_name):
        for pkg in getattr(inventory, list_name):
            if pkg.name and not pkg.name.startswith(LivePatch.LIVEPATCH_PREFIX):
                ret_pkgs.append(pkg)
        setattr(inventory, list_name, ret_pkgs)


def remove_kernel_from_list(inventory, list_name, kernel_candidate):
    """
    inventory: a PackageInventory object
    kernel_candidate: a kernel YumPackage object
    list_name: installed/installed_other/ etc
    """
    ret_pkgs = []
    if inventory and hasattr(inventory, list_name):
        for pkg in getattr(inventory, list_name):
            if pkg.name and pkg.arch and pkg.name == kernel_candidate.name and pkg.arch == kernel_candidate.arch:
                pass
            else:
                ret_pkgs.append(pkg)
        setattr(inventory, list_name, ret_pkgs)

def add_kernel_to_list(inventory, list_name, kernel_candidate):
    """
    inventory: a PackageInventory object
    kernel_candidate: a kernel YumPackage object
    list_name: installed/installed_other/ etc
    """
    if inventory and hasattr(inventory, list_name):
        ret_pkgs = getattr(inventory, list_name)
        ret_pkgs.append(kernel_candidate)
        setattr(inventory, list_name, ret_pkgs)


def get_pkg_and_status_from_inventory(inventory, pkg_na):
    """
    Since installed_pkgs, installed_other_pkgs, missing_pkgs, installed_rejected_pkgs, failed_pkgs, not_applicable_pkgs
    are mutually exclusive, we can be confident that the pkg_na would only show up once among all the lists above, thus
    search order doesn't matter. Not searching in installed_pending_reboot_pkgs here because this code happens earlier 
    than the installed_pending_reboot_pkgs get populated.

    inventory: an PackageInventory object
    pkg_na: a pkg tuple: (name, arch)
    """
    for pkg in inventory.installed_pkgs:
        if pkg.name and pkg.arch and (pkg.name, pkg.arch) == pkg_na:
            return (pkg, "installed")
    for pkg in inventory.installed_other_pkgs:
        if pkg.name and pkg.arch and (pkg.name, pkg.arch) == pkg_na:
            return (pkg, "installed_other")
    for pkg in inventory.missing_pkgs:
        if pkg.name and pkg.arch and (pkg.name, pkg.arch) == pkg_na:
            return (pkg, "missing")
    for pkg in inventory.installed_rejected_pkgs:
        if pkg.name and pkg.arch and (pkg.name, pkg.arch) == pkg_na:
            return (pkg, "installed_rejected")
    for pkg in inventory.failed_pkgs:
        if pkg.name and pkg.arch and (pkg.name, pkg.arch) == pkg_na:
            return (pkg, "failed")
    for pkg in inventory.not_applicable_pkgs:
        if pkg.name and pkg.arch and (pkg.name, pkg.arch) == pkg_na:
            return (pkg, "not_applicable")
    # Safe exit
    return (None, "not found")


def amazon_linux_2(operating_system):
    if operating_system == 'amazon_linux_2':
        return True
    return False

def get_applied_kernel_vra_tuple():
    """
    This command returns the tuple (v, r, a) of the current running kernel, e.g: 4.14.173-137.229.amzn2.x86_64
    Another way is to use misc.get_running_kernel_pkgtup(ts). that would require the yum dependency.
    For now this should be efficient
    """
    kernel_vra = os.uname()[2]
    (v, ra) = kernel_vra.split('-')
    (r, a) = ra.rsplit('.', 1)
    return (v, r, a)


def live_patching_enabled():
    enabled = False
    try:
        enabled = kernel_livepatch_plugin_enabled() and kpatch_runtime_service_enabled()
    except Exception:
        return False
    return enabled

def kpatch_runtime_service_enabled():
    """
    The kpatch service loads all of the kernel live patches upon initialization or at boot.
    This is what we used to decide if livepatching is enabled or not.
    """
    try:
        #output, return_code = shell_command(["yum", "list", "installed", "kpatch-runtime"])
        output, return_code = shell_command(["systemctl", "is-enabled", "kpatch.service"])
        if return_code != 0:
            return False
        return True
    except Exception:
        logger.warn("""Amazon Linux 2 by default supports systemd init system.
        Patch manager use systemctl to detect if live patching is enabled or not""")
        return False


def kernel_livepatch_plugin_enabled():
    """
    Whether the kernel-livepatch plugin package is (installed & enabled) or not.
    """
    try:
        output, return_code = shell_command(["yum", "list", "installed", "kernel-livepatch-*"])
        if return_code != 0:
            return False
        return True
    except Exception:
        return False


def kernel_supports_live_patching(kernel_vra_tuple):
    """
    To use Kernel Live Patching on Amazon Linux 2, must use
    Amazon Linux 2 with kernel version 4.14.165-131.185 or later

    kernel_vra: (v, r, a)
    """
    kernel_name = get_kernel_pkg_name(kernel_vra_tuple)
    if (compare(kernel_name, LivePatch.MINIMUM_REQUIRED_KERNEL) > -1):
        return True
    logger.info('The current version of the Linux kernel you are running does not support kernel live patching.')
    return False


def kernel_within_support_lifetime():
    """
    An Amazon Linux 2 kernel receives kernel live patches for 3 months.
    To continue to receive kernel live patches after the three-month period,
    instance must be rebooted to move to the new kernel version.
    Ported from yum plugin to decide if kernel within support.
    """
    build_time = get_current_kernel_build_time()
    year = int(build_time[-1])
    month2number_map = get_month_abbr()
    month = month2number_map[build_time[-5]]
    day = int(build_time[-4])
    months_of_support = int(3)
    build_date = date(year, month, day)
    EOL_date = add_months(build_date, months_of_support)
    if datetime.now().date() > EOL_date:
        logger.info('The current version of the Linux kernel is no longer being provided with Live Patches. \
            Reboot into the latest kernel version to get a continued stream of live patches')
        return False
    else:
        logger.info("The current version of the Linux kernel you are running will no longer"
                        " receive live patches after {}.".format(EOL_date)) 
        return True


def get_current_kernel_build_time():
    # >>> os.uname()[3].split()
    # ['#1', 'SMP', 'Sun', 'Feb', '9', '00:21:30', 'UTC', '2020']
    return os.uname()[3].split()


def get_month_abbr():
    cal = {'': 0, 'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
    return cal


def add_months(sourcedate, months):
    """
    Add number of months to sourcedate, and round down if the
    target date's month has less days than sourcedate's date
    Ported from yum plugin kernel-livepatch.py
    """
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year,month)[1])
    return date(year, month, day)


def get_livepatch_pkg_name(kernel_vra_tup):
    """
    kernel_naevr_tup: (v, r, a) of a pkg
    """
    (v, r, a) = kernel_vra_tup
    r = r.replace(LivePatch.DIST, "")
    return "kernel-livepatch-%s-%s" %(v, r)


def get_kernel_pkg_name(kernel_vra_tup):
    """
    kernel_naevr_tup: (v, r, a) of a pkg
    """
    (v, r, a) = kernel_vra_tup
    return "kernel-%s-%s.%s" %(v, r, a)


def kernel_compliant_after_applying_livepatch(kernel_candidate_vra_tup): 
    """
    This method decides after applying all the livepatches for current running kernel version whether the kernel becomes compliant or not,
    The method compares the CVE sets addressed by kernel patches(from current running version to candidate version)
    with the CVE sets addressed by livepatches for current running kernel version.

    kernel_candidate_vra_tup: a candidate kernel tuple (v, r, a)
    """
    current_kernel_vra_tuple = get_applied_kernel_vra_tuple()
    if kernel_supports_live_patching(current_kernel_vra_tuple) == False: 
        return False
    livepatches_cve_set = cve_set_for_livepatches(current_kernel_vra_tuple)
    kernel_cve_set = cve_set_for_kernel(current_kernel_vra_tuple, kernel_candidate_vra_tup)
    if(livepatches_cve_set.issuperset(kernel_cve_set)):
        return True
    return False


def cve_set_for_livepatches(current_kernel_vra_tup):
    """
    Get the set of cves that will be addressed by applying all the live patches for current kernel.
    Example see test case.

    an example result running 'yum updateinfo list cves all kernel':
    i CVE-2019-19062 important/Sec. kernel-livepatch-4.14.165-131.185-1.0-0.amzn2.x86_64
    i CVE-2019-19332 important/Sec. kernel-livepatch-4.14.165-131.185-1.0-0.amzn2.x86_64
      CVE-2019-15918 important/Sec. kernel-livepatch-4.14.165-131.185-1.0-2.amzn2.x86_64

    current_kernel_vra: (v, r, a) of a pkg
    """
    livepatch_pkg_name = get_livepatch_pkg_name(current_kernel_vra_tup)
    output, result = shell_command(["yum", "updateinfo", "list", "cves", "all", "kernel-livepatch*"])
    if result != 0:
        return set()
    return get_cve_set_for_livepatches(output, livepatch_pkg_name)


def get_cve_set_for_livepatches(shell_output, livepatch_pkg_name):
    """
    Get the set of cves that will be addressed by applying all the live patches for current kernel.
    Example see test case.

    Put it in a function so it can be tested

    livepatch_pkg_name: name of a livepatch, it includes the version and release_without_dist
    """
    shell_output = shell_output.replace('\ni', '\n') # remove i from the line beginning
    cve_entries = shell_output.split('\n')
    cve_set = set()
    start = 0
    end = len(cve_entries) - 1
    livepatch_regex = LivePatch.KERNEL_LIVEPATCH_PATTERN
    
    # Omit lines that are not related to cve information
    while len(re.findall(livepatch_regex, cve_entries[start])) == 0 and start <= end:
        start += 1
    while len(re.findall(livepatch_regex, cve_entries[end])) == 0 and end > 0:
        end -= 1
    while start <= end:
        # Put the lower bound for livepatches into set
        while start <= end and len(re.findall(livepatch_regex, cve_entries[start])) > 0 :
            lower_bound_pkg_name = re.findall(livepatch_regex, cve_entries[start])[0]
            if livepatch_pkg_name in lower_bound_pkg_name:
                cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[start])[0])
                start += 1
                break
            start += 1
        # Put the upper bound for livepatches into set
        while start <= end and len(re.findall(livepatch_regex, cve_entries[end])) > 0:
            upper_bound_pkg_name = re.findall(livepatch_regex, cve_entries[end])[0]
            if livepatch_pkg_name in upper_bound_pkg_name:
                cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[end])[0])
                end -= 1
                break
            end -= 1
        # Get everything in between into set
        while start <= end:
            cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[start])[0])
            cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[end])[0])
            start += 1
            end -= 1
    return cve_set


def cve_set_for_kernel(current_kernel_vra_tup, kernel_candidate_vra_tup):
    """
    an example result running 'yum updateinfo list cves all kernel'
    i CVE-2018-12207   important/Sec. kernel-4.14.154-128.181.amzn2.x86_64
    i CVE-2019-19062   important/Sec. kernel-4.14.165-131.185.amzn2.x86_64
      CVE-2019-19332   important/Sec. kernel-4.14.165-131.185.amzn2.x86_64

    current_kernel_vra: ( v, r, a ) of a pkg
    current_kernel_vra: ( v, r, a ) of a pkg

    # TODO: To honor the baseline classification & severity implementation.
    """
    current_kernel = get_kernel_pkg_name(current_kernel_vra_tup)
    kernel_candidate = get_kernel_pkg_name(kernel_candidate_vra_tup)
    output, result = shell_command(["yum", "updateinfo", "list", "cves", "all", "kernel"])
    if result != 0:
        return set()
    if kernel_candidate_vra_tup is None or compare(current_kernel, kernel_candidate) > -1:
        return get_cve_set_for_kernel(output, current_kernel, current_kernel)
    return get_cve_set_for_kernel(output, current_kernel, kernel_candidate)


def get_cve_set_for_kernel(shell_output, current_kernel, kernel_candidate):
    """
    Get a set of cves that will be addressed by upgrading kernel to the candidate, the set
    of cves also including the cves addressed in the current kernel

    shell_output: the whole output from shell command
    current_kernel: a current running kernel patch. In format: name-version-release.arch
    kernel_candidate: a candidate kernel patch. In format: name-version-release.arch
    kernel_regex: the regex exp that loosely matches a kernel's naming format
    """
    shell_output = shell_output.replace('\ni', '\n') # remove i from the line beginning
    cve_entries = shell_output.split('\n')
    cve_set = set()
    length = len(cve_entries)
    start = 0  # first line
    end = len(cve_entries) - 1 # last line
    kernel_regex = LivePatch.KERNEL_PATTERN
    # Omit lines that are not related to cve information
    while len(re.findall(kernel_regex, cve_entries[start])) == 0 and start <= end:
        start += 1
    while len(re.findall(kernel_regex, cve_entries[end])) == 0 and end > 0:
        end -= 1
    while start <= end:
        # current kernel always installed, thus get cves addressed by current kernel in the set first
        # if current kernel is newer than the kernel on this line
        while start <= end and compare(current_kernel, re.findall(kernel_regex, cve_entries[start])[0]) == 1:
            start += 1
        # if current kernel and the kernel on this line is same
        while start <= end and compare(current_kernel, re.findall(kernel_regex, cve_entries[start])[0]) == 0:
            cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[start])[0])
            start += 1
        while start <= end and compare(kernel_candidate, re.findall(kernel_regex, cve_entries[end])[0]) == -1:
            end -= 1
        while start <= end and compare(kernel_candidate, re.findall(kernel_regex, cve_entries[end])[0]) == 0:
            cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[end])[0])
            end -= 1
        # Get everything in between into set
        while start <= end:
            cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[start])[0])
            cve_set.add(re.findall(LivePatch.CVE_PATTERN, cve_entries[end])[0])
            start += 1
            end -= 1
    return cve_set

LIVEPATCH_ENABLED = live_patching_enabled()

