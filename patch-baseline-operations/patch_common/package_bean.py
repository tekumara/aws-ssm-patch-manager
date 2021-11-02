# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Base marker class representing a piece of package metadata,
# which contains necessary information for filtering
class PackageBean:
    def __init__(self):
        raise Exception()

    def get_filter_functions(self):
        """
        get the filter functions used by baseline filter
        :return: map with key being the filter key,
        value being the function which does the filtering,
        the value should return true if this package bean
        fits the filter values
        """
        raise Exception()

    def get_timestamp(self):
        """
        get the timestamp of this package bean
        :return: datatime object
        """
        raise Exception()

    def get_packages(self):
        """
        get package included in this package bean
        :return: array of packages
        """
        raise Exception()

    def match_include_patterns(self, patterns):
        """
        whether this package bean match the given pattern
        :param patterns: array of strings (possibly, regex)
        :return: true / false
        """
        raise Exception()

    def match_exclude_patterns(self, patterns):
        """
        whether this package bean match the given pattern
        :param patterns: array of strings (possibly, regex)
        :return: true / false
        """
        raise Exception()