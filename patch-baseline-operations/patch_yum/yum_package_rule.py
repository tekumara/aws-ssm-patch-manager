# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from datetime import datetime
import yum_package_filter_group
import yum_update_notice
import logging

logger = logging.getLogger()

class YumPackageRule:
    def __init__(self, baseline_rule, date_time_now):
        """
        :param baseline_rule: BaselineRule object from patch_common
        """
        self.approval_timestamp = baseline_rule.approval_timestamp
        self.compliance = baseline_rule.compliance
        self.filter_group = yum_package_filter_group. \
            YumPackageFilterGroup(baseline_rule.filter_group)
        self.enable_non_security = baseline_rule.enable_non_security

    def test_notice(self, package):
        """
        :param package: update notice from yum
        :return: True if the notice is wanted, False otherwise
        """
        if not package.is_non_security or self.enable_non_security:
            return self.filter_group.test_notice(package) and \
                   package.get_updated_time() < self.approval_timestamp
        else:
            return False
