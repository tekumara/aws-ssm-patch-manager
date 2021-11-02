# aws-ssm-patch-manager

Reverse engineering AWS Systems Manager Patch Manager.

## AWS-RunPatchBaseline PatchLinux Step

The step:

1. Checks prereqs are installed eg: python, apt
1. Creates and changes to _/var/log/amazon/ssm/patch-baseline-operations/_
1. Downloads and extracts the latest tar file from the region-specific bucket eg: _s3://aws-ssm-us-east-1/patchbaselineoperations/linux/payloads/patch-baseline-operations-1.80.tar.gz_
1. Runs modules from tar file:

```
import common_startup_entrance
common_startup_entrance.execute("os_selector", "PatchLinux", "{{SnapshotId}}",\
        "{{Operation}}", "{{InstallOverrideList}}", \
        "{{RebootOption}}", "{{BaselineOverride}}")
```

The things in `{{..}}` are the SSM document parameters and substituted before execution by SSM.

_common_startup_entrance_ comes from the tarfile and does the following:

1. Fetches snapshot_info for the instance using [get_deployable_patch_snapshot_for_instance](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetDeployablePatchSnapshotForInstance.html)
1. Downloads the snapshot from `snapshot_info['SnapshotDownloadUrl']`. The snapshot contains a [patch baseline](https://docs.aws.amazon.com/systems-manager/latest/userguide/patch-manager-cli-commands.html#patch-manager-cli-commands-get-patch-baseline) eg:

```
{
  "patchBaseline": {
    "accountId": "075727635805",
    "baselineId": "pb-0c7e89f711c3095f4",
    "name": "AWS-UbuntuDefaultPatchBaseline",
    "globalFilters": {
      "filters": [
        {
          "key": "PRODUCT",
          "values": [
            "*"
          ]
        }
      ]
    },
    "approvalRules": {
      "rules": [
        {
          "filterGroup": {
            "filters": [
              {
                "key": "PRIORITY",
                "values": [
                  "Required",
                  "Important",
                  "Standard",
                  "Optional",
                  "Extra"
                ]
              }
            ]
          },
          "complianceLevel": "UNSPECIFIED",
          "enableNonSecurity": false,
          "approveAfterDays": 7,
          "approveUntilDate": null
        }
      ]
    },
    "approvedPatches": [],
    "approvedPatchesComplianceLevel": "UNSPECIFIED",
    "approvedPatchesEnableNonSecurity": false,
    "rejectedPatches": [],
    "rejectedPatchesAction": "ALLOW_AS_DEPENDENCY",
    "createdTime": 1525194800.068,
    "modifiedTime": 1525194800.068,
    "description": "Default Patch Baseline for Ubuntu Provided by AWS.",
    "operatingSystem": "UBUNTU",
    "sources": []
  },
  "patchGroup": null,
  "patches": [],
  "enableApplicationPatches": false,
  "requiredFeatures": []
}
```

1. Saves patch state (the install state of packages in the baseline) to _/var/log/amazon/ssm/patch-configuration/patch-states-configuration.json_
1. Generates a patch compliance summary, eg:

   ```
   {
       "TypeName": "AWS:PatchSummary",
       "SchemaVersion": "1.0",
       "ContentHash": "c2786b90098d0ab8df34bdc8a9f3d2402695f385de522f6ca703ecb3a5d6e3ad",
       "CaptureTime": "2021-11-02T04:17:28Z",
       "Content": [
           {
               "BaselineId": "pb-0c7e89f711c3095f4",
               "PatchGroup": "",
               "SnapshotId": "7c64b8b8-1274-47db-8f0d-e26f6c0aae7b",
               "ExecutionId": "a7f84bef-2aa8-4853-a28f-e6e0108c8285",
               "InstalledCount": "198",
               "InstalledOtherCount": "1077",
               "InstalledRejectedCount": "0",
               "InstalledPendingRebootCount": "0",
               "NotApplicableCount": "10254",
               "MissingCount": "0",
               "FailedCount": "0",
               "CriticalNonCompliantCount": "0",
               "SecurityNonCompliantCount": "0",
               "OtherNonCompliantCount": "0",
               "OperationType": "Install",
               "OperationStartTime": "2021-11-02T04:15:51Z",
               "OperationEndTime": "2021-11-02T04:17:28Z",
               "RebootOption": "RebootIfNeeded"
           }
       ]
   }
   ```

1. Uploads the patch compliance summary using [put_inventory](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_PutInventory.html) and saves it to _/var/log/amazon/ssm/patch-configuration/patch-inventory-from-last-operation.json_
