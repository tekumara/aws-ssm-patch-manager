# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

FILTER_VALUE_WILDCARDS = "*"

class YumPackageFilter:
    def __init__(self, key, values):
        """        
        :param key: property to filter on 
        :param values: to accept
        """
        self.key = key
        self.values = values

    def test_notice(self, package):
        """
        :param package: package wrapper
        :return: True if the notice is wanted, False otherwise
        """
        value = package.get_filter_key_value(self.key)
        if FILTER_VALUE_WILDCARDS in self.values:
            return True
        elif value is None:
            return False
        return value in self.values
