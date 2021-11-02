# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import yum_package_filter


class YumPackageFilterGroup:
    def __init__(self, baseline_filter_group):
        """
        :param BaselineFilterGroup from patch_common
        """
        self.filters = []
        for filter in baseline_filter_group.filters or []:
            self.filters.append(yum_package_filter.YumPackageFilter(filter.key, filter.values))

    def test_notice(self, notice):
        """
        :param notice: update notice from yum 
        :return: True if the notice is wanted, False otherwise
        """
        for filter in self.filters:
            if not filter.test_notice(notice):
                return False
        return True
