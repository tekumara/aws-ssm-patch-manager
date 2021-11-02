# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common import instance_info

FILTER_VALUE_WILDCARDS = "*"

class BaselineFilter:

    def __init__(self, dict):
        """        
        :param dict: key values pairs, i.e. 
        {
            "key": "CLASSIFICATION",
            "values": [
                "Security"
            ]
        }
        """
        self.key = dict["key"]
        self.values = dict["values"]

    def test_package_bean(self, package_bean):
        """
        :param package_bean: package bean from us
        :return: True if the package_bean is wanted, False otherwise
        """

        if self.key == "PRODUCT":
            return FILTER_VALUE_WILDCARDS in self.values or instance_info.product in self.values
        else:
            func_map = package_bean.get_filter_functions()
            # sanity check, indicating a bug if failure
            if self.key not in func_map.keys():
                raise Exception("Unknown filter key: %s." % (self.key))

            func = func_map[self.key]
            return func(self.values)
