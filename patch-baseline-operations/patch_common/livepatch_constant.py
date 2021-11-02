# These are the scenarios where CVE checks are necessary, after doing a CVE check, we are
# able to determine if the kernel is compliant or not, then we take corresponding actions 
# The four element in the tuple means:
#   1. The status of kernel candidate package after the _report_package method in yum_report.py.
#         For Scan operation, possible states: installed, installed_other, installed_rejected, missing, not_applicable
#         For Install operation, possible states: installed, installed_other, installed_rejected, missing, failed, not applicable
#   2. Does the kernel exist in the PatchStateConfiguration().patch_states, aka, is the kernel pending a reboot
#         False-does not exist, True-does exist
#   3. The status of kernel livepatch candidate(for current kernel) after the _report_package method in yum_report.py
#   4. Does the livepatch exist in the PatchStateConfiguration().patch_states. Livepatches don't need a reboot,
#         so if they exist in in the psc.patch_states, we have to clean them up and report them correctly
#   Scan and install share the first half of the lists, install has additional status failed for package thus we include that in the
#      second half of dict.
# The opposite of following is that when livepatching is missing or failed or not applicable.
LIVEPATCH_SCENARIOS = dict.fromkeys(
    [
        # For both scan and install operation
        ('installed', True, 'installed', True),
        ('installed', True, 'installed', False),
        ('installed', False, 'installed', True),
        ('installed', False, 'installed', False),
        ('installed', True, 'installed_other', True),
        ('installed', True, 'installed_other', False),
        ('installed', False, 'installed_other', True),
        ('installed', False, 'installed_other', False),
        ('installed', True, 'installed_rejected', True),
        ('installed', True, 'installed_rejected', False),
        ('installed', False, 'installed_rejected', True),
        ('installed', False, 'installed_rejected', False),
        ('installed_other', True, 'installed_other', True),
        ('installed_other', True, 'installed_other', False),
        ('installed_other', False, 'installed_other', True),
        ('installed_other', False, 'installed_other', False),
        ('installed_other', True, 'installed', True),
        ('installed_other', True, 'installed', False),
        ('installed_other', False, 'installed', True),
        ('installed_other', False, 'installed', False),
        ('installed_other', True, 'installed_rejected', True),
        ('installed_other', True, 'installed_rejected', False),
        ('installed_other', False, 'installed_rejected', True),
        ('installed_other', False, 'installed_rejected', False),
        ('installed_rejected', True, 'installed_rejected', True),
        ('installed_rejected', True, 'installed_rejected', False),
        ('installed_rejected', False, 'installed_rejected', True),
        ('installed_rejected', False, 'installed_rejected', False),
        ('installed_rejected', True, 'installed', True),
        ('installed_rejected', True, 'installed', False),
        ('installed_rejected', False, 'installed', True),
        ('installed_rejected', False, 'installed', False),
        ('installed_rejected', True, 'installed_other', True),
        ('installed_rejected', True, 'installed_other', False),
        ('installed_rejected', False, 'installed_other', True),
        ('installed_rejected', False, 'installed_other', False),
        ('missing', True, 'installed', True),
        ('missing', True, 'installed', False),
        ('missing', False, 'installed', True),
        ('missing', False, 'installed', False),
        ('missing', True, 'installed_other', True),
        ('missing', True, 'installed_other', False),
        ('missing', False, 'installed_other', True),
        ('missing', False, 'installed_other', False),
        ('missing', True, 'installed_rejected', True),
        ('missing', True, 'installed_rejected', False),
        ('missing', False, 'installed_rejected', True),
        ('missing', False, 'installed_rejected', False),

    ], 'do_cve_check'
)

# All the rest scenarios would fall under no_cve_check