# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common.baseline import Baseline

class DnfBaseline(Baseline):
    """
    Child class of Patch Common Baseline object
    Overrides functionality for pattern matching of package
    """
    def __init__(self, baseline_dict):
        super(DnfBaseline, self).__init__(baseline_dict)

    def match_include_patterns(self, package_bean):
        """
        Method for determining if an individual package bean is explicitly included by the baseline.
        :param package_bean : DnfPackage object
        """
        return package_bean.match_include_patterns(self.include) \
         and (package_bean.has_metadata() or self.approved_patches_enable_non_security)

    def match_exclude_patterns(self, package_bean):
        """
        Method for determining if an individual package bean is explicitly excluded by the baseline.
        :param package_bean : DnfPackage object
        """
        return package_bean.match_exclude_patterns(self.exclude)

    def categorize_override_list_install(self, all_packages = {}):
            """
            Method for categorizing patches from a override_list install.
            """

            cpa_failed = []
            for na in all_packages:

                matches = []
                compliance_pkgs = self.assign_compliance_to_list_of_packages(all_packages[na])
                for package in compliance_pkgs:
                    if package.matches_install_override_list:
                        matches.append(package)

                # if versions of this package name, arch matched the cpa list.
                if(len(matches) > 0):
                    # get the first occurence of the highest version
                    highest_version = self._get_highest_versioned_package(matches)
                    # If the highest version matches the CPA list and is not the currently installed version => cpa_failed
                    if highest_version.matches_install_override_list and highest_version.compare_version(highest_version.current_edition) > 0:
                        cpa_failed.append(highest_version)

            # now just do a regular scan of every package.
            (missing, installed, installed_rejected, installed_other, not_applicable) = \
            self.categorize_packages_scan(all_packages)

            return (missing, cpa_failed, installed, installed_rejected, installed_other, not_applicable)
