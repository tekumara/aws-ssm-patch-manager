# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common.baseline import Baseline

class ZyppBaseline(Baseline):
    """
    Child class of Patch Common Baseline object
    Overrides functionality for pattern matching of package
    """
    def __init__(self, baseline_dict):
        super(ZyppBaseline, self).__init__(baseline_dict)

    def match_include_patterns(self, package_bean):
        """
        Method for determining if an individual package bean is explicitly included by the baseline.
        :param cli_object is a cli_package_bean or cli_solvable object.
        :returns True if matches and false if not.
        """
        return package_bean.match_patterns(self.include)

    def match_exclude_patterns(self, cli_bean):
        """
        Method for determining if an individual package bean is explicitly excluded by the baseline.
        :param cli_object is a cli_package_bean or cli_solvable object.
        :returns True if matches and false if not.
        """
        return cli_bean.match_patterns(self.exclude)