# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import datetime

from patch_common import baseline_filter_group


class BaselineRule:
    def __init__(self, dict, date_time_now, operating_system):
        """
        :param dict:
        {
            "approveAfterDays": 0,
            "approveUntilDate": "YYYY-MM-DD"
            "complianceLevel": "HIGH",
            "enableNonSecurity" : False
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
        :param date_time_now: the creation time of package rule group,
        used by approveAfterDays attr. 
        """
        if "approveUntilDate" in dict and dict["approveUntilDate"] is not None:
            self.approval_timestamp = datetime.datetime.strptime(dict.get("approveUntilDate"), "%Y-%m-%d") + datetime.timedelta(days=1)
        else:
            self.approval_timestamp = date_time_now - datetime.timedelta(days=dict.get("approveAfterDays") or 0)

        self.compliance = dict.get("complianceLevel") or "UNSPECIFIED"
        self.filter_group = baseline_filter_group.BaselineFilterGroup(dict["filterGroup"])
        self.enable_non_security = dict.get("enableNonSecurity") or False
        self.operating_system = operating_system

    def test_package_bean(self, package_bean):
        """
        :param package_bean: package bean from us
        :return: True if the package_bean is wanted, False otherwise
        """
        allow_packages_without_metadata = True
        if self.operating_system.lower() != "suse":
            allow_packages_without_metadata = self.enable_non_security or package_bean.has_metadata()

        return self.filter_group.test_package_bean(package_bean) and \
               package_bean.get_timestamp() < self.approval_timestamp and allow_packages_without_metadata
