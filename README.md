# aws-ssm-patch-manager

Reverse engineering [AWS Systems Manager Patch Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-patch.html).

## PatchLinux.sh

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
1. [Download](patch-baseline-operations/common_os_selector_methods.py#L282) the [patch baseline snapshot](patch-baseline-snapshot.json). The contents is similar to the output of the [get-patch-baseline](https://docs.aws.amazon.com/systems-manager/latest/userguide/patch-manager-cli-commands.html#patch-manager-cli-commands-get-patch-baseline) cli command.
1. Save patch state (the install state of packages in the baseline) to _/var/log/amazon/ssm/patch-configuration/patch-states-configuration.json_

.....TODO....

1. Generate a patch compliance summary ([example](patch-inventory-from-last-operation.json)).
1. Upload the patch compliance summary using [put_inventory](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_PutInventory.html) and saves it to _/var/log/amazon/ssm/patch-configuration/patch-inventory-from-last-operation.json_
