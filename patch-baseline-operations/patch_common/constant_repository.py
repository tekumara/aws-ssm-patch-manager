import inspect

class Get_Baseline_To_Snapshot_Keys():
    """
    GetPatchBaseline Keys avaialble on a snapshot and their snapshot equivalent keys (as values).
    """
    KEYS = {
        "ApprovedPatchesEnableNonSecurity": "approvedPatchesEnableNonSecurity",
        "BaselineId": "baselineId",
        "Name": "name",
        "PatchGroups": "patchGroup", # this is special because in the snapshot it is a single patch group.
        "RejectedPatches": "rejectedPatches",
        "GlobalFilters": "globalFilters",
        "PatchFilters": "filters",
        "Sources": "sources",
        "Configuration": "configuration",
        "Products": "products",
        "ApprovalRules": "approvalRules",
        "PatchRules": "rules",
        "PatchFilterGroup": "filterGroup",
        "Key": "key",
        "Values" : "values",
        "ApproveUntilDate": "approveUntilDate",
        "ApproveAfterDays": "approveAfterDays",
        "ComplianceLevel": "complianceLevel",
        "EnableNonSecurity": "enableNonSecurity",
        "Description": "description",
        "ApprovedPatchesComplianceLevel": "approvedPatchesComplianceLevel",
        "OperatingSystem": "operatingSystem",
        "ApprovedPatches": "approvedPatches",
        "RejectedPatchesAction": "rejectedPatchesAction",
        "CreatedDate":"createdTime",
        "ModifiedDate":"modifiedTime"
    }

class Compliance_levels():
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"
    UNSPECIFIED = "UNSPECIFIED"
    COMPLIANCE_LEVELS = {
        CRITICAL: 5,
        HIGH: 4,
        MEDIUM: 3,
        LOW: 2,
        INFORMATIONAL: 1,
        UNSPECIFIED: 0
    }


class Compliance_string_formatting():
    INSTALL_TIME = "%Y-%m-%dT%H:%M:%SZ"


class Snapshot_keys():
    """
    Snapshot keys available on the .json object
    """
    INSTANCE_ID = "instanceId"
    OPERATION = "operation"
    PATCH_BASELINE = "patchBaseline"
    PATCH_GROUP = "patchGroup"
    PRODUCT = "product"
    REGION = "region"
    SNAPSHOT_ID = "snapshotId"
    INSTALL_OVERRIDE_LIST = "installOverrideList"
    BASELINE_OVERRIDE = "baselineOverride"
    REBOOT_OPTION = "rebootOption"
    ASSOCIATION_ID = "associationId"
    ASSOCIATION_SEVERITY = "associationSeverity"

class InstallOverrideList_keys():
    """
    Keys from install override list .yaml file
    """
    PATCHES = "patches"
    ID = "id"
    TITLE = "title"


class ExitCodes():
    """
    Exit codes returned by the package manager specific pieces.

    * >=130 Mostly standard linux errors, do not use
    * 150 - 160 are reserved for errors on the Document
    * 255>= invalid
    """
    SUCCESS = 0
    FAILURE = 1
    DEPENDENCY_CHECK_FAILURE = 2
    REBOOT = 194
    REBOOT_WITH_FAILURES = 195
    REBOOT_WITH_DEPENDENCY_CHECK_FAILURE = 196
    # get_deployable_snapshot
    ASSOCIATION_ERROR = 130
    ASSOCIATION_API_ERROR = 131
    ASSOCIATION_ACCESS_DENIED = 132
    GET_PATCH_BASELINE_ERROR = 133
    GET_PATCH_BASELINE_API_ERROR = 134
    GET_PATCH_BASELINE_ACCESS_DENIED = 135
    DESCRIBE_PATCH_BASELINES_ERROR = 136
    DESCRIBE_PATCH_BASELINES_API_ERROR = 137
    DESCRIBE_PATCH_BASELINES_ACCESS_DENIED = 138
    GET_RESOURCES_ERROR = 139
    GET_RESOURCES_API_ERROR = 140
    GET_RESOURCES_ACCESS_DENIED = 141
    PATCH_ASSOCIATIONS_BASELINE_ERROR = 142
    SNAPSHOT_ERROR = 143
    SNAPSHOT_API_ERROR = 144
    SNAPSHOT_ACCESS_DENIED = 145
    SNAPSHOT_UNSUPPORTED_OS = 146
    SNAPSHOT_COULDNT_SAVE = 147
    NO_INSTANCE_METADATA = 148
    PUT_INVENTORY_ERROR = 149
    SNAPSHOT_INVALID = 150
    UPTIME_COULDNT_FIND = 151
    CONFIGURATION_FILE_ERROR = 152
    BASELINE_TAGS_REGEX_ERROR = 153
    BASELINE_OVERRIDE_ACCESS_DENIED = 160
    BASELINE_OVERRIDE_INVALID = 161
    BASELINE_OVERRIDE_DOWNLOAD_ERROR = 162
    BASELINE_OVERRIDE_MISSING_OS = 163
    BASELINE_OVERRIDE_MULTIPLE_OVERRIDES_PROVIDED_FOR_OS = 165
    BASELINE_OVERRIDE_UNSUPPORTED_OPERATING_SYSTEM = 166
    BASELINE_OVERRIDE_AND_INSTALL_OVERRIDE_PROVIDED = 167


reverse_mapping_tuples = [(code, codename) for codename, code in inspect.getmembers(ExitCodes()) if codename[:2] != "__"]

exit_codes_to_meaning = {}
for code, codemeaning in reverse_mapping_tuples:
    exit_codes_to_meaning[code] = codemeaning


# Used to determine compliance for no-reboot behavior
REBOOT_EXIT_CODES = [ExitCodes.REBOOT, ExitCodes.REBOOT_WITH_DEPENDENCY_CHECK_FAILURE, ExitCodes.REBOOT_WITH_FAILURES]


class OperationType():
    """
    Operation type requested(lower cases)
    """
    SCAN = "scan"
    INSTALL = "install"


class RebootOption():
    """
    RebootOption that passed in by customers control reboot workflow
    after Scan/Install operation
    """
    NO_REBOOT = "NoReboot"
    REBOOT_IF_NEEDED = "RebootIfNeeded"


class PatchStates():
    INSTALLED = "Installed"
    INSTALLED_PENDING_REBOOT = "InstalledPendingReboot"
    INSTALLED_OTHER = "InstalledOther"
    INSTALLED_REJECTED = "InstalledRejected"
    FAILED = "Failed"
    MISSING = "Missing"
    NOT_APPLICABLE = "NotApplicable"


class PatchStatesConfigurationKeys():
    """
    Keys from local patch-state/configuration.json file
    """
    LAST_NO_REBOOT_INSTALL_OPERATION_TIME = "lastNoRebootInstallOperationTime"
    PATCH_STATES = "patchStates"
    ID = "id"
    TITLE = "title"
    STATE = "state"
    INSTALLED_TIME = "installedTime"


FILTER_VALUE_WILDCARDS = "*"
CONFIGURATION_PATH = "/var/log/amazon/ssm/patch-configuration/patch-states-configuration.json"
INVENTORY_PATH = "/var/log/amazon/ssm/patch-configuration/patch-inventory-from-last-operation.json"
CONFIGURATION_DIRECTORY = "/var/log/amazon/ssm/patch-configuration"
KERNEL_STATE_DIRECTORY = "/var/log/amazon/ssm/kernel-livepatch"
KERNEL_STATE_PATH = "/var/log/amazon/ssm/kernel-livepatch/kernel-livepatch.json"

class LivePatch():
    """
    AL2 Livepatch feature requires kernel version equal or above: kernel-4.14.165-131.185.amzn2.x86_64.

    All livepatches provided for a specific kernel version have patch name prefixed with:
    "kernel-livepatch", an example: kernel-livepatch-4.14.165-131.185-1.0-2.amzn2.x86_64
    """
    MINIMUM_REQUIRED_KERNEL = "kernel-4.14.165-131.185.amzn2.x86_64"
    DIST=".amzn2"
    CVE_PATTERN = "CVE-\d{4}-\d{4,7}"
    KERNEL_PATTERN = "kernel-[\d.]*-.*" # already querying for kernel so just need a loose match
    KERNEL_LIVEPATCH_PATTERN = "kernel-livepatch-[\d.]*-.*" # already querying for kernel livepatch so a loose match
    LIVEPATCH_PREFIX='kernel-livepatch-'
    KERNEL_PREFIX='kernel-'


class Metrics:
    """
    Keys for Pinpoint Runtime Metrics
    """
    KERNEL_LIVE_PATCH_ENABLED = "KernelLivePatchingEnabled"
    KERNEL_LIVE_PATCH_COMPLIANT = "KernelLivePatchingCompliant"
    COMPLIANCE_ITEM_CHAR_COUNT = "ComplianceItemCharCount"
    SUMMARY_ITEM_CHAR_COUNT = "SummaryItemCharCount"
    UNHANDLED_EXCEPTIONS = "UnhandledExceptions"
    HANDLED_EXCEPTIONS = "HandledExceptions"

class OperatingSystem:
    """
    Expected Operating System Names for Patch Manager
    """
    SUSE = "SUSE"
    UBUNTU = "UBUNTU"
    DEBIAN = "DEBIAN"
    RASPBIAN = "RASPBIAN"
    AMAZON_LINUX = "AMAZON_LINUX"
    AMAZON_LINUX2 = "AMAZON_LINUX_2"
    CENTOS = "CENTOS"
    RED_HAT = "REDHAT_ENTERPRISE_LINUX"
    ORACLE = "ORACLE_LINUX"
    MACOS = "MACOS"
