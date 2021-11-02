# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common import baseline_filter


class BaselineFilterGroup:
    def __init__(self, dict):
        """        
        :param dict: key values pairs, i.e. 
        {
            "filters": [
                {
                    "key": "CLASSIFICATION",
                    "values": [
                        "Security"
                    ]
                }
            ]
        }
        """
        self.filters = []
        for filter in dict.get("filters") or []:
            self.filters.append(baseline_filter.BaselineFilter(filter))

    def test_package_bean(self, package_bean):
        """
        :param package_bean: package bean from us
        :return: True if the package_bean is wanted, False otherwise
        """
        for filter in self.filters:
            if not filter.test_package_bean(package_bean):
                return False
        return True
