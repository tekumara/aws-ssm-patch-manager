# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import operator
from patch_common import base_package
from patch_common import baseline_filter_group
from patch_common import baseline_rule_group
from patch_common import package_matcher
from patch_common.constant_repository import Compliance_levels

logger = logging.getLogger()

class Baseline(object):
    def __init__(self, baseline_dict):
        """
        :param baseline_dict: dict representation of baseline
        """
        # self.account_id = baseline_dict["accountId"]
        self.baseline_id = baseline_dict["baselineId"]
        self.name = baseline_dict["name"]

        self.sources = baseline_dict.get("sources") or []
        self.operating_system = baseline_dict["operatingSystem"]

        self.global_filters = baseline_filter_group. \
            BaselineFilterGroup(baseline_dict["globalFilters"])
        self.approval_rules = baseline_rule_group. \
            BaselineRuleGroup(baseline_dict["approvalRules"], self.operating_system)

        # TODO, make this split into cve, adv, bz
        self.include = baseline_dict["approvedPatches"]
        self.exclude = baseline_dict["rejectedPatches"]

        self.includeComplianceLevel = \
            baseline_dict.get("approvedPatchesComplianceLevel") or \
            base_package.BasePackage.compliance_unspecified
        self.approved_patches_enable_non_security = baseline_dict.get("approvedPatchesEnableNonSecurity") or False
        self.rejected_patches_action = baseline_dict.get("rejectedPatchesAction")

        self.created_time = baseline_dict["createdTime"]
        self.modified_time = baseline_dict["modifiedTime"]
        # self.description = baseline_dict["description"]


    def match_include_patterns(self, package_bean):
        """
        Method for determining if an individual package bean is explicitly included by the baseline.
        :param package_bean
        """
        for pattern in self.include:
            if package_bean.match_by_name(pattern):
                return True
        return False

    def match_exclude_patterns(self, package_bean):
        """
        Method for determining if an individual package bean is explicitly excluded by the baseline.
        :param package_bean
        """
        for pattern in self.exclude:
            if package_bean.match_by_name(pattern):
                return True
        return False

    def __set_compliance_attributes(self, package, matches, compliance):
        """
        Method for setting the "matches_baseline" and "compliance" attributes on a package. 
        :param package - a BaseCLIBean with the complianceand matching_baseline attributes on the instance.
        :param matches - a boolean representing whether the package matches the baseline.
        :param compliance - is the compliance to assign to the package.compliance attribute.
        """    
        package.compliance = compliance
        package.matches_baseline = matches
        return package

    def assign_compliance(self, package_bean):
        """
        Method for determining if a package matches the baseline. And assigning
        the appropriate compliance. Sets the package.matches_baseline and package.compliance attributes.
        :param package_bean is a base_cli_bean to check if it matches baseline.
        :returns the package with compliance and matches_baseline attributes set.
        """
        if self.match_exclude_patterns(package_bean):
            return self.__set_compliance_attributes(package_bean, False, Compliance_levels.UNSPECIFIED)

        matched = False
        compliances = []
        if self.match_include_patterns(package_bean):
            compliances.append(self.includeComplianceLevel)
            matched = True

        if self.global_filters.test_package_bean(package_bean):
            if self.approval_rules.test_package_bean(package_bean):
                compliances.extend(self.approval_rules.get_compliances(package_bean))
                matched = True
        
        compliance_level = self.get_highest_compliance(compliances)
        return self.__set_compliance_attributes(package_bean, matched, compliance_level)      

    def categorize_packages_scan(self, all_packages):
        """
        Method for categorizing a list of packages into the appropriate reporting buckets.
        :param - all_packages is a 2-dimensional array where the 1D element represents a package and the 2D array are
        the different versions of that package as BaseCLIBeans. 

        For example, [[kernel.x86_64:4.14.109-80.92.amzn1, kernel.x86_64:4.14.114-82.97.amzn1, kernel.x86_64:4.14.114-83.126.amzn1],[...]].
        The idea behind this baseline logic is that we have a complete list of all available package versions. An 'available' package version
        is simply a version that is greater than the currently installed version. If these versions have the BaseCLIBean info on them
        (classification, severity, etc... even if they DON'T have a classification or severity),the Baseline can determine which one to report as 
        Missing, Installed, InstalledOther, etc...
        """
        missing = []
        installed = []
        installed_rejected = []
        installed_other = []
        not_applicable = []

        # Loop through all packages for that (name, arch)
        for na in all_packages: 
            # Sometimes the same package has multiple classifications and severities. 
            # We want to get the package that matches the baseline with the highest version follows by the highest compliance, else just the highest version/
            # compliance non-matching package if none match.
            package = self.__get_package_that_should_be_reported(all_packages[na], na)
            if package.installed:
                if self.match_exclude_patterns(package):
                    # if package is installed, matches exclude patterns => installed_rejected.
                    installed_rejected.append(package)
                elif not package.matches_baseline:
                    # if package is installed, does not match baseline => installed_other.
                    installed_other.append(package)
                else:
                    # if package is installed, does not matche exclude pattern, matches baseline,
                    # update available => missing
                    if package.update_available:
                        missing.append(package)
                    else:
                    # if package is installed, does not matche exclude pattern, matches baseline,
                    # no update available => installed
                        installed.append(package)
            else:
                # If package is not installed, matches baseline => Not Applicable
                if package.matches_baseline:
                    not_applicable.append(package)

        return (missing, installed, installed_rejected, installed_other, not_applicable)

    def __get_package_that_should_be_reported(self, package_versions, na):
        """
         Method for getting the highest compliance of the package that matches baseline and reporting that classification and severity else get highest compliance of package that does not match baseline.
        :param package_versions - List of packages, one for each version and classificaiton / severity combo for versions.
        :param na - the name arch of the packages being checked. 
        :returns Package instance object
        """
        # loop through all of the available versions of the package and get the list of packages of the highest version
        # that matches the baseline. This is a list because the same version may be reported twice with a different classification and severity.
        compliance_pkgs = self.assign_compliance_to_list_of_packages(package_versions)
        highest_versioned_packages = self._get_highest_versioned_packages_that_match_baseline(compliance_pkgs)
        self.__set_remediated_cves_for_highest_versioned_packages(compliance_pkgs, highest_versioned_packages)
            
        if len(highest_versioned_packages) > 0:
            return self.__get_package_with_highest_compliance(highest_versioned_packages)
        else:
            # if no version matched baseline, return first installed version/class/sev combo.
            if len(package_versions) > 0:
                return self._get_highest_versioned_package(package_versions)
                
            raise Exception("Installed package did not have any versions to report. Not even the installed one: %s"%(str(na)))

    def _get_highest_versioned_package(self, compliance_pkgs):
        """
        Method for getting the first occurence of the highest matching package. 
        :param compliance_pkgs is a list of packages with the compliance assigned.
        :return the first occurence of the highest versioned package in the list. 
        """

        highest_package = compliance_pkgs[0]
        for package in compliance_pkgs:
            edition_to_compare = package.available_edition if package.available_edition else package.current_edition
            if(highest_package.compare_version(edition_to_compare) < 0):
                highest_package = package

        return highest_package

    def _get_highest_versioned_packages_that_match_baseline(self, compliance_pkgs):
        """
        Method to get the highest versioned package that matches the baseline and it's highest compliance.
        :compliance_pkgs is a list of packages of same name / architecture, same or different versions and classifications that have their compliance
        assigned.
        For example: [kernel.x86_64:4.14.109-80.92.amzn1, kernel.x86_64:4.14.109-80.92.amzn1, kernel.x86_64:4.14.114-82.97.amzn1, kernel.x86_64:4.14.114-83.126.amzn1]
        The first two packages have the same edition but may have a different classification and severity.
        The second two package have a different edition from each other and the first. They may have the same or different classification and severity.
        This method just pulls out the package version that should be reported, regardless of how many times it is repeated.
        :return List<BaseCLIBean> of the packages of the edition that should be reported. 
        """          
        highest_versions = []

        for package in compliance_pkgs:
            edition_to_compare = package.available_edition if package.available_edition else package.current_edition

            if package.matches_baseline:
                # if there is no candidate, choose it.
                if len(highest_versions) == 0:
                    highest_versions.append(package)
                # if this newer version is greater, replace highest packages list.
                else:
                    if highest_versions[0].compare_version(edition_to_compare) < 0:     
                        highest_versions = [package]
                    # else it is the same version but might have a different classification and severity so we want to add it. 
                    elif highest_versions[0].compare_version(edition_to_compare) == 0:
                        highest_versions.append(package)

        return highest_versions

    def __get_package_with_highest_compliance(self, packages):
        """
        Method for returning the package with the highest compliance form a list of packages.
        :param packages is a list of packages with the compliance assigned. 
        """
        current_package = packages[0]
        for package in packages:
            if Compliance_levels.COMPLIANCE_LEVELS[package.compliance] > Compliance_levels.COMPLIANCE_LEVELS[current_package.compliance]:
                current_package = package
       
        return current_package

    def __set_remediated_cves_for_highest_versioned_packages(self, compliance_pkgs, highest_versioned_packages):
        """
        Method for setting the total remediated cves
        We report all CVEs that will be fixed by applying the latest update.
        This includes the package we are reporting as missing and any intermediary updates that we are skipping over
        :param compliance_pkgs: list of all BaseCLIBean candidate versions for a particular package
        :param highest_versioned_packages: list of all the highest BaseCLIBean versions that match the baseline
        """
        if len(highest_versioned_packages) == 0:
            return
        highest_versioned_package = highest_versioned_packages[0]
        all_known_cves_for_update = set()
        for pkg in compliance_pkgs:
            # If package > Installed version and <= Highest versioned package
            if pkg.update_available and highest_versioned_package.compare_version(pkg.available_edition) >= 0:
                # Add CVEs to total remediated CVE set
                all_known_cves_for_update.update(pkg.cve_ids)

        # Set remediated cve set for all highest versioned packages
        for pkg in highest_versioned_packages:
            if not pkg.all_known_cves_for_update or len(pkg.all_known_cves_for_update) == 0:
                pkg.all_known_cves_for_update = list(all_known_cves_for_update)

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
                if highest_version.matches_install_override_list and highest_version.installed == False:
                    cpa_failed.append(highest_version)
       
        # now just do a regular scan of every package.
        (missing, installed, installed_rejected, installed_other, not_applicable) = \
        self.categorize_packages_scan(all_packages)

        return  (missing, cpa_failed, installed, installed_rejected, installed_other, not_applicable)

    def assign_compliance_to_list_of_packages(self, packages):
        """
        Method for assigning compliance to a list of packages (includes matches_baseline, matches_install_override_list attributes)
        :param packages is a list of packages. 
        :return list of packages with compliance assigned.
        """
        compliance_pkgs = []
        for package in packages:
            compliance_pkg = self.assign_compliance(package) 
            compliance_pkgs.append(compliance_pkg)
        
        return compliance_pkgs        

    def get_highest_compliance(self, compliances):
        """
        Method for getting the highest compliance level from a list of compliances. 
        :param is the available compliances to choose the highest from 
               as a list of strings. e.g., ["high", "Medium", "LOW"]
        :returns compliance level as a lower case string.
        """
        final_level =  0 # set default to lowest.
        final_level_name = Compliance_levels.UNSPECIFIED
        upper_compliances = [compliance.upper() for compliance in compliances]
        for level in Compliance_levels.COMPLIANCE_LEVELS:
            if level.upper() in upper_compliances and Compliance_levels.COMPLIANCE_LEVELS[level]> final_level:
                final_level = Compliance_levels.COMPLIANCE_LEVELS[level]
                final_level_name = level
        return final_level_name

    def get_name_arch2pkgs(self, package_beans):
        """
        :param package_beans: array of package_bean from us
        :return: array of packages approved along with corresponding compliance level
        """

        # first find all packages can be included and corresponding compliance level
        # adding included package, removing excluded package
        packages_with_compliance = []
        for package_bean in package_beans:
            compliances = []

            # gather all compliance for this package bean
            # if a package bean is explicit rejected
            if package_bean.match_exclude_patterns(self.exclude):
                continue
            if package_bean.match_include_patterns(self.include):
                compliances.append(self.includeComplianceLevel)

            if self.global_filters.test_package_bean(package_bean):
                compliances.extend(self.approval_rules.get_compliances(package_bean))

            packages_without_compliance = package_bean.get_packages()
            for package_without_compliance in packages_without_compliance:
                # explicit reject always win
                if package_without_compliance.match_exclude_patterns(self.exclude):
                    continue
                if package_without_compliance.match_include_patterns(self.include):
                    package_with_compliance = package_without_compliance.duplicate()
                    package_with_compliance.compliance = self.includeComplianceLevel
                    packages_with_compliance.append(package_with_compliance)

                # add package bean compliance to package
                for compliance in compliances:
                    package_with_compliance = package_without_compliance.duplicate()
                    package_with_compliance.compliance = compliance
                    packages_with_compliance.append(package_with_compliance)

        # for all package with compliance in baseline, find the newest version / compliance combination
        name_arch2pkg = {}  # {(name, arch) -> set(package)}
        for package in packages_with_compliance:
            name_arch = (package.name, package.arch)  # (name, arch)
            if name_arch in name_arch2pkg and name_arch2pkg[name_arch]:
                name_arch2pkg[name_arch].add(package)
            else:
                name_arch2pkg[name_arch] = set([package])

        for name_arch in name_arch2pkg:
            name_arch2pkg[name_arch] = list(name_arch2pkg[name_arch])
            name_arch2pkg[name_arch].sort(reverse=True)

        return name_arch2pkg

    @property
    def block_rejected_patches(self):
        return self.rejected_patches_action is not None and self.rejected_patches_action.lower() == 'block'

    @property
    def has_rejected_patches(self):
        return bool(self.exclude)
