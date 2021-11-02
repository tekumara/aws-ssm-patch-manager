# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Constants for the patch baseline operations APT.
"""

from patch_common.package_matcher import get_format

COMPLIANCE_UNSPECIFIED = "UNSPECIFIED"
COMPLIANCE_INFORMATIONAL = "INFORMATIONAL"
COMPLIANCE_LOW = "LOW"
COMPLIANCE_MEDIUM = "MEDIUM"
COMPLIANCE_HIGH = "HIGH"
COMPLIANCE_CRITICAL = "CRITICAL"
SORTED_COMPLIANCE_LEVEL = [
    COMPLIANCE_UNSPECIFIED,
    COMPLIANCE_INFORMATIONAL,
    COMPLIANCE_LOW,
    COMPLIANCE_MEDIUM,
    COMPLIANCE_HIGH,
    COMPLIANCE_CRITICAL
]

FILTER_KEY_PRODUCT = "PRODUCT"
FILTER_KEY_SECTION = "SECTION"
FILTER_KEY_PRIORITY = "PRIORITY"

FILTER_VALUE_WILDCARDS = "*"
FILTER_VALUE_SECURITY = "security"
DEBIAN_SECURITY_SITE = "security.debian.org"

FULL_PACKAGE_VERSION_NAME_FORMAT = get_format("nav")

PACKAGE_LOGGING_SEPARATOR = "; "

class ChangeType():
    INSTALL = "install"
    UPGRADE = "upgrade"
    DELETE = "delete"
    BROKEN = "broken"
    # The following change types exist but we do not double check them
    KEEP = "keep"
    DOWNGRADE = "downgrade"
    REINSTALL = "reinstall"


class ProblemType():
    # This indicates that the package will be broken even after fix or when no fix
    BROKEN = 'broken'
    # This indicates that the package is not auto-removable and not auto-installed but needs to be deleted
    DELETE = "delete"
    # This indicates that the package was broken before some potential fix and after fix trial, it is marked as delete
    # which means that the ONLY way to fix broken is to delete the broken package
    DELETE_BROKEN = "delete-broken"
    # This indicates that no auto installation is allowed
    NO_AUTO_INSTALL = 'no-auto-install'
    # This indicates that the package is mentioned in the baseline/overrideList but has another version approved/matched
    VERSION_CONFLICT = "version-conflict"
    # This indicates that the package is rejected and needs to be blocked for install/upgrades
    BLOCKED_REJECTED = "blocked-rejected"
