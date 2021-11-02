# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import yum_package
import yum_package_filter_group
import yum_package_rule_group
import yum_update_notice
import logging

logger = logging.getLogger()

class YumBaseline:
    def __init__(self, baseline):
        """
        :param baseline: Baseline object from patch_common
        """
        # self.account_id = baseline.account_id
        self.baseline_id = baseline.baseline_id
        self.name = baseline.name

        self.global_filters = yum_package_filter_group. \
            YumPackageFilterGroup(baseline.global_filters)
        self.approval_rules = yum_package_rule_group. \
            YumPackageRuleGroup(baseline.approval_rules)

        self.include = baseline.include
        self.exclude = baseline.exclude

        self.includeComplianceLevel = baseline.includeComplianceLevel

        self.created_time = baseline.created_time
        self.modified_time = baseline.modified_time
        # self.description = baseline.description
        self.approved_patches_enable_non_security = baseline.approved_patches_enable_non_security
        self.block_rejected_patches = baseline.block_rejected_patches
        self.has_rejected_patches = baseline.has_rejected_patches

    def test_notice(self, notice):
        """
        :param notice: update notice from yum
        :return: True if the notice is wanted, False otherwise
        """
        if not self.global_filters.test_notice(notice):
            return False

        if self.approval_rules.test_notice(notice):
            return True

        return self._test_notice_explicit(notice)

    def test_package(self, pkg):
        """
        See if the package matches the approval rules.
        :param pkg:
        :return:
        """

        pass

    def _test_notice_explicit(self, notice):
        """
        :param notice: update notice from yum
        :return: True if the notice is wanted explicitly, False otherwise
        """
        return yum_update_notice.match_notice_explicit(self.include, notice)

    def get_notice_compliances(self, notice):
        """
        :param notice: update notice from yum
        :return: array of the compliance level this notice has, can be []
        """
        # make sure global filters and excludes are considered
        if not self.test_notice(notice):
            return []

        compliances = self.approval_rules.get_compliances(notice)

        # this only applies to packages with metadata notices
        if self._test_notice_explicit(notice):
            compliances.append(self.includeComplianceLevel)
        return compliances

    def get_na2pkgs(self, notices, available_packages):
        """
        :param available_packages: all installed packages as tuples
        :param notices: array of update notice from yum
        :return: dictionary (name+arch) -> set(YumPackage) the baseline matches, ordered by compliance
        """

        # first find all packages can be included and corresponding compliance level
        # adding included package, removing excluded package
        pkgs = []
        processed_pkg_tup = set()
        for notice in notices:
            classification = yum_update_notice.get_classification_update_notice(notice)
            severity = yum_update_notice.get_severity_update_notice(notice)
            pkg_tups = yum_update_notice.get_update_notice_packages(notice)
            pkg_cves = yum_update_notice.get_cve_update_notice(notice)
            # all packages in the notices will match the same rules (since they have the same attributes
            # pick any of them
            compliances = []
            if len(pkg_tups) > 0:
                compliances = self.get_notice_compliances(yum_package.YumPackage.from_tuple_notice(pkg_tups[0], notice))

            for pkg_tup in pkg_tups:
                processed_pkg_tup.add(pkg_tup)
                # if excluded, skip
                if yum_update_notice.match_yum_package(self.exclude, pkg_tup):
                    continue

                # explicit approvals
                if yum_update_notice.match_yum_package(self.include, pkg_tup):
                    pkgs.append(
                        yum_package.YumPackage(
                            pkg_tup,
                            self.includeComplianceLevel,
                            classification=classification,
                            severity=severity,
                            cve_ids=pkg_cves
                        )
                    )
                # rule approvals
                for compliance in compliances:
                    pkgs.append(
                        yum_package.YumPackage(
                            pkg_tup,
                            compliance,
                            classification=classification,
                            severity=severity,
                            cve_ids=pkg_cves
                        )
                    )

        na2pkg = {}  # {(name, arch) -> set(YumPackage)}
        for pkg in pkgs:
            na = (pkg.name, pkg.arch)  # (name, arch)
            if na in na2pkg and na2pkg[na]:
                na2pkg[na].add(pkg)
            else:
                na2pkg[na] = set([pkg])

        # check for notice-less packages
        for pkg in available_packages:
            if pkg.naevr not in processed_pkg_tup:
                na = (pkg.naevr[0], pkg.naevr[1])
                
                # Skip excluded packages
                if yum_update_notice.match_yum_package(self.exclude, pkg.naevr):
                    continue

                # Check notice-less packages against the approved patches list
                if (yum_update_notice.match_yum_package(self.include, pkg.naevr) and self.approved_patches_enable_non_security == True):
                    candidate = yum_package.YumPackage(pkg.naevr, self.includeComplianceLevel, buildtime=pkg.buildtime)

                    if na2pkg.get(na) is not None:
                        na2pkg[na].add(candidate)
                    else:
                        na2pkg[na] = set([candidate])

                candidate_compliances = self.get_notice_compliances(pkg)

                for compliance in candidate_compliances:
                    candidate = yum_package.YumPackage(pkg.naevr, compliance, buildtime=pkg.buildtime)

                    if na2pkg.get(na) is not None:
                        na2pkg[na].add(candidate)
                    else:
                        na2pkg[na] = set([candidate])

        # make into a sorted list
        for na in na2pkg:
            na2pkg[na] = list(na2pkg[na])
            na2pkg[na].sort(reverse=True)

        return na2pkg
