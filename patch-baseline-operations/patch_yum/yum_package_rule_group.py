# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import datetime
import yum_package_rule


class YumPackageRuleGroup:
    def __init__(self, baseline_rule_group):
        """
        :param baseline_rule_group: BaselineRuleGroup object from patch_common
        """
        self.date_time_now = datetime.datetime.utcnow()
        self.rules = []
        for rule in baseline_rule_group.rules or []:
            self.rules.append(yum_package_rule.YumPackageRule(rule, self.date_time_now))

    def test_notice(self, notice):
        """
        :param notice: update notice from yum 
        :return: True if the notice is wanted, False otherwise
        """
        for rule in self.rules:
            if rule.test_notice(notice):
                return True
        return False

    def get_compliances(self, notice):
        """
        :param notice: update notice from yum 
        :return: array of compliance level this notice has
        """
        ret = []
        for rule in self.rules:
            if rule.test_notice(notice):
                ret.append(rule.compliance)
        return ret
