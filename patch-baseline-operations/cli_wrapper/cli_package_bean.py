# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common.base_cli_bean import BaseCLIBean
from patch_common import rpm_version
from xml.etree.ElementTree import Element
from patch_zypp_cli import zypp_shared_operation_methods as shared
from patch_common.package_range_comparer import PackageRangeComparer as PRC


class CLIPackageBean(BaseCLIBean):
    """
    Class for holding CLIPackages that can be used by the common package for filtering.
    """

    def __init__(self, **kwargs):
        """
        Initialization method for a CLIPackageBean
        :param - source_object is either a tuple of order:
        (severity, classification, arch, name, timestamp, installed, current_edition, available_edition, locked, compliance, matches_baseline).
        """
        self.source_object = kwargs
        if "xml_element" in self.source_object and isinstance(self.source_object["xml_element"], Element):
            BaseCLIBean.__init__(self, arch = self.source_object["xml_element"].get('arch'),
                name = self.source_object["xml_element"].get('name'),
                available_edition = self.source_object["xml_element"].get('edition'),
                available_version = self.source_object["xml_element"].get('version'),
                installed = "yes" in self.source_object["xml_element"].get('installed').lower()
            )
        else:
            BaseCLIBean.__init__(self, **self.source_object)

    def __eq__(self, other):
        return self.name == other.name and self.arch == other.arch and self.version == other.version and self.release == other.release

    def __hash__(self):
        return hash((self.name, self.arch, self.version, self.release))

    def compare_version(self, other_edition):
        """
        :param other_edition: package from us
        :return: -1 if self is older than other, 0 if equal, > 0 if self is newer
        """
        this_edition = self.available_edition if self.available_edition else self.current_edition
        return rpm_version.compare(this_edition, other_edition)

    @property
    def epoch(self):
        """
        Method for returning the default epoch value as it is used for package inventory. 
        Note: Zypper does not use epoch's per https://en.opensuse.org/openSUSE:Package_naming_guidelines
        """
        return "0"
    
    @property
    def version(self):
        """
        Current edition as required by package compliance in common package.
        """
        # if the available_version is None or "" it means the package that is being reported is the installed
        # version and the current version should be reported.
        if not self.available_edition:
            return shared.parse_version_from_edition(self.current_edition)
        else:
            return shared.parse_version_from_edition(self.available_edition)
    
    @property
    def release(self):
        """
        Current release as required by package compliance in common package.
        """
        # if the available_version is None or "" it means the package that is being reported is the installed
        # version and the current version should be reported.
        if not self.available_edition:
            return shared.parse_release_from_edition(self.current_edition)
        else:
            return shared.parse_release_from_edition(self.available_edition)

    def match_patterns(self, patterns):
        """
        Method for determining if package matches a pattern from the provided list.
        :param patterns is a string list of patterns to match. e.g. ["kernel.x96_64 > 3.3.3", etc...]
        :returns True if the package matches one of the patterns and false otherwise. 
        """
        for pattern in patterns:
            prc = PRC(pattern)
            if PRC(pattern).matches_package((self.name, self.arch, self.epoch, self.version, self.release)):
                return True
        
        return False