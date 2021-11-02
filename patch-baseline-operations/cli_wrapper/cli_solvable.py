# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
from xml.etree.ElementTree import Element
from patch_common.base_cli_bean import BaseCLIBean
from patch_common.constant_repository import Compliance_levels
from patch_common import rpm_version
from patch_zypp_cli import zypp_shared_operation_methods as shared
from datetime import datetime
from patch_common.package_range_comparer import PackageRangeComparer as PRC

class CLISolvable(BaseCLIBean):
    """
    Class for representing a Solvable.
    """
    def __init__(self, xml_element):
        """
        Constructor for Solvable object.
        :param - xml_element is an xml.etree.ELementTree.Element object.
        Example: <solvable status="not-installed" name="zziplib-devel" kind="package" edition="0.13.67-10.14.1" arch="x86_64" repository="SLE-SDK12-SP4-Pool"/>
        """
        if not isinstance(xml_element, Element):
            raise TypeError("CLISolvable parameter xml_element must be type xml.etree.ElementTree.Element")

        self.xml_element = xml_element
        installed_status = self.xml_element.get('status').lower()

        BaseCLIBean.__init__(self, 
            name = xml_element.get('name'), 
            installed = "installed" in installed_status and "not-installed" not in installed_status, 
            available_edition = xml_element.get('edition'),
            arch = xml_element.get('arch'))
        
        if self.available_edition:
            self.available_version = shared.parse_version_from_edition(self.available_edition)
            self.release = shared.parse_release_from_edition(self.available_edition)

    @property
    def available_version(self):
        """
        Method for returning the version of the package.
        """
        return self.__available_version

    @available_version.setter
    def available_version(self, vrs):
        """
        Method for setting the release of the package.
        """
        self.__available_version = vrs

    @property
    def epoch(self):
        """
        Method for returning the epoch default of 0 (zypper does not use epoch's).
        """
        return "0"

    @property
    def release(self):
        """
        Method for returning the release of the package.
        """
        return self.__release

    @release.setter
    def release(self, rls):
        """
        Method for setting the release of the package.
        """
        self.__release = rls
    
    def compare_version(self, other_edition):
        """
        :param other_edition: package from us
        :return: -1 if self is older than other, 0 if equal, > 0 if self is newer
        """
        return rpm_version.compare(self.available_edition, other_edition)
    
    def match_patterns(self, patterns):
        """
        Method for determining if solvable matches a pattern from the provided list.
        :param patterns is a string list of patterns to match. e.g. ["kernel.x96_64 > 3.3.3", etc...]
        :returns True if the package matches one of the patterns and false otherwise. 
        """
        for pattern in patterns:
            package = None
            if self.available_edition:
                package = (self.name, self.arch, self.epoch, self.available_version, self.release)
            else:
                package = (self.name, self.arch, self.epoch, "", "")

            if PRC(pattern).matches_package(package):
                return True
        
        return False
