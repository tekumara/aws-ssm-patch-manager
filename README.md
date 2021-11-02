# aws-ssm-patch-manager

Reverse engineering [AWS Systems Manager Patch Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-patch.html).

## PatchLinux.sh

TLDR:

- SCAN: compare the baseline to installed packages and generate an inventory
- INSTALL: run `apt upgrade` for all packages in the baseline and generate an inventory

In detail:

1. Check prereqs are installed eg: python, apt
1. Create and chdir to _/var/log/amazon/ssm/patch-baseline-operations/_
1. Download and extract the [patch-baseline-operations tar file](https://github.com/tekumara/aws-ssm-patch-manager/blob/main/Makefile#L22) from the region-specific bucket.
1. Run modules from the tar file:

```
import common_startup_entrance
common_startup_entrance.execute("os_selector", "PatchLinux", "{{SnapshotId}}",\
        "{{Operation}}", "{{InstallOverrideList}}", \
        "{{RebootOption}}", "{{BaselineOverride}}")
```

`{{..}}` contain SSM document parameters that are substituted before execution by SSM.

[_common_startup_entrance_](patch-baseline-operations/common_startup_entrance.py) comes from the tar file and does the following:

1. Fetch snapshot_info for the instance using [get_deployable_patch_snapshot_for_instance](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetDeployablePatchSnapshotForInstance.html)
1. [Download](patch-baseline-operations/common_os_selector_methods.py#L282) the [patch baseline snapshot](patch-baseline-snapshot.json). The contents is similar to the output of the [get-patch-baseline](https://docs.aws.amazon.com/systems-manager/latest/userguide/patch-manager-cli-commands.html#patch-manager-cli-commands-get-patch-baseline) cli command. [Patch baselines](https://docs.aws.amazon.com/systems-manager/latest/userguide/about-patch-baselines.html) define which patches are automatically approved.
1. [Save snapshot](patch-baseline-operations/common_os_selector_methods.py#L336) to [snapshot.json](patch-baseline-operations/snapshot.json).
1. [main_entrance.py](patch-baseline-operations/main_entrance.py) is launched and passed [snapshot.json](patch-baseline-operations/snapshot.json).
1. [Identify the OS](patch-baseline-operations/main_entrance.py#L251) and call relevant package manager entrance file, eg: for Ubuntu import [apt_entrance.py](patch-baseline-operations/apt_entrance.py) and run `execute` passing the snapshot object.
1. The package manager [scans or installs all the approved patchs](patch-baseline-operations/patch_apt/apt_operations.py#L27). In the case of Ubuntu:
   - SCAN: compare the apt cache to the baseline and identify installed_updates, installed_other, installed_rejected, missing_updates, not_applicable_packages.
   - INSTALL: run `apt upgrade` and then compare the cache to the baseline.
1. [Generate](patch-baseline-operations/main_entrance.py#L266) a patch compliance summary ([example](patch-inventory-from-last-operation.json)) and save the patch state (the install state of packages in the baseline) to _/var/log/amazon/ssm/patch-configuration/patch-states-configuration.json_ ([example](patch-states-configuration.json))
1. Saves it to _/var/log/amazon/ssm/patch-configuration/patch-inventory-from-last-operation.json_
1. Upload the patch compliance summary using [put_inventory](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_PutInventory.html) if the hash has changed.
