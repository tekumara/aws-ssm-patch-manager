# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
class PackageInventory:
    def __init__(self,
                 operation_type,
                 pkg_type,
                 installed_pkgs,
                 installed_other_pkgs,
                 not_applicable_pkgs,
                 missing_pkgs,
                 installed_rejected_pkgs=None,
                 failed_pkgs=None,
                 override_list=None,
                 installed_pending_reboot_pkgs = None,
                 current_installed_pkgs=None):
        # namely: "scan", "install"
        self.operation_type = operation_type
        # namely: "yum", "apt"
        self.pkg_type = pkg_type

        self.installed_pkgs = installed_pkgs
        self.installed_other_pkgs = installed_other_pkgs
        self.not_applicable_pkgs = not_applicable_pkgs
        self.failed_pkgs = failed_pkgs or []
        self.installed_rejected_pkgs = installed_rejected_pkgs or []
        self.missing_pkgs = missing_pkgs
        self.installed_pending_reboot_pkgs = installed_pending_reboot_pkgs or []
        self.current_installed_pkgs = current_installed_pkgs or []

        if operation_type.lower() == "install":
            # Now only when no override list is used, all missing patches should be failed
            if override_list is None:
                self.failed_pkgs.extend(missing_pkgs)
                self.missing_pkgs = []

        elif operation_type.lower() == "scan":
            # Should not have failed pkgs for scan operation. This should not have but just in case
            if len(self.failed_pkgs) > 0:
                raise Exception("Scan operation has failed packages: "  + self.failed_pkgs)

        else:
            raise Exception("Unknown operation: %s" % (operation_type))







