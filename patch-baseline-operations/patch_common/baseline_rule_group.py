# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import datetime

from patch_common import baseline_rule


class BaselineRuleGroup:
    def __init__(self, dict, operating_system):
        """
        :param dict: 
        {
            "rules": [
                {
                    "compliance": "HIGH",
                    "filterGroup": {
                        "filters": [
                            {
                                "key": "CLASSIFICATION",
                                "values": [
                                    "Security"
                                ]
                            }
                        ]
                    }
                }
            ]
        }
        """
        self.date_time_now = datetime.datetime.utcnow()
        self.rules = []
        for rule in dict.get("rules") or []:
            self.rules.append(baseline_rule.BaselineRule(rule, self.date_time_now, operating_system))

    def test_package_bean(self, package_bean):
        """
        :param package_bean: package bean from us
        :return: True if the package_bean is wanted, False otherwise
        """
        for rule in self.rules:
            if rule.test_package_bean(package_bean):
                return True
        return False

    def get_compliances(self, package_bean):
        """
        :param package_bean: package bean from us
        :return: array of compliance level this package_bean has
        """
        ret = []
        for rule in self.rules:
            if rule.test_package_bean(package_bean):
                ret.append(rule.compliance)
        return ret
