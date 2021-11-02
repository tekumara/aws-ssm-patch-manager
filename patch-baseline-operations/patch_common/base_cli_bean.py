# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from datetime import datetime
import logging
import unicodedata
from patch_common import rpm_version
from patch_common.constant_repository import FILTER_VALUE_WILDCARDS
from patch_common.constant_repository import Compliance_levels

logger = logging.getLogger()

class BaseCLIBean(object):
    """
    Class for representing a base cli_bean that a baseline can tell if it matches.
    """

    def __init__(self, **kwargs):

        self.severity = self.__get_param(kwargs, "severity", "")
        self.classification = self.__get_param(kwargs, "classification", "")
        self.installed_time = self.__get_param(kwargs, "installed_time", "0")
        self.arch = self.__get_param(kwargs, "arch", "noarch")
        self.name = kwargs["name"] # name is a required parameter.
        self.installed = self.__get_param(kwargs, "installed", False)
        self.current_edition = self.__get_param(kwargs, "current_edition", None)
        self.available_edition = self.__get_param(kwargs, "available_edition", "0")
        self.locked = self.__get_param(kwargs, "locked", False)
        self.compliance = self.__get_param(kwargs, "compliance", Compliance_levels.UNSPECIFIED)
        self.matches_baseline = self.__get_param(kwargs, "matches_baseline", False)
        self.matches_install_override_list = False
        self.release_time = self.__get_param(kwargs, "release_time", "0")
        self.bugzilla_ids = self.__get_param(kwargs, "bugzilla_ids", set())
        self.cve_ids = self.__get_param(kwargs, "cve_ids", set())
        self.all_known_cves_for_update = []
        self.__update_available = None

    def __get_param(self, arg_dict, key, default):
        """
        Method for getting a key from a dict else providing a default.
        :param key - is the key to get.
        :param default - is the default ot provide if the key does not exist.
        :returns the key value form the dict or the default if one does not exist.
        """
        return arg_dict[key] if key in arg_dict else default 

    def match_by_name(self, name):
        """
        Method for determining if provided package name matches current name.
        Note: IS case sensitive as Linux packages are case sensitive.
        :return Boolean representing whether the match. 
        """
        return self.name == name

    def compare_version(self, other_version):
        """
        :param other_version: package from us
        :return: -1 if self is older than other_version, 0 if equal, > 0 if self is newer
        """
        raise NotImplementedError("Must implement compare version")
    
    def get_filter_functions(self):
        """
        Method for getting the filter functions used by baseline filter
        :return: map with key being the filter key,
        value being the function which does the filtering,
        the value should return true if this package bean
        fits the filter values
        """
        return {
            "CLASSIFICATION": self.__classification_filter,
            "SEVERITY": self.__severity_filter
        }

    def has_metadata(self):
        """
        Method to determine if a package has metadata associated with it
        :return: True if classification and severity are not empty
        """
        return self.classification is not "" and self.severity is not ""

    def __severity_filter(self, severities):
        """
        Method for checking if a package matches the list of privded severities.
        :severities is a list of severities (as strings) from the baseline.
        :returns True if packages severity is contained in the baseline list and false otherwise.
        """
        return self.__passes_filter(self.severity, severities)

    def __classification_filter(self, classifications):
        """
        Method for checking if a package matches the list of privded classifications.
        :classifications is a list of classifications (as strings) from the baseline.
        :returns True if packages classification is contained in the baseline list and false otherwise.
        """
        return self.__passes_filter(self.classification, classifications)

    def __passes_filter(self, object_to_compare, list_of_objects):
        """
        Method for checking if a list of objects has a wild card, exists or is in a list of objects.
        :object_to_compare the value to check is in the list.
        :list of objects is a list of strings to compare the object to.
        :Returns true if matches and false if not.
        """
        if FILTER_VALUE_WILDCARDS in list_of_objects:
            return True

        if not object_to_compare:
            return False

        return object_to_compare.lower() in map(lambda x: x.lower(), list_of_objects)

    @property
    def release_time(self):
        '''
        Method for getting release time of the package
        :return: time in second since epoch
        '''
        return self.__release_time

    @release_time.setter
    def release_time(self, release_time):
        '''
        Method for setting release time of the package
        :param release_time: time in seconds since epoch
        '''
        self.__release_time = release_time

    def get_timestamp(self):       
        """
        Method for getting timestamp as required by common package.
        TODO - Update common package to not need "get_timestamp()" as a method.
        """
        try:
            return datetime.utcfromtimestamp(float(self.release_time))
        except ValueError:
            return datetime.utcfromtimestamp(0)

    @property
    def matches_install_override_list(self):
        """
        Method for getting whether the package matches a CPA list. Defaults to false.
        """
        return self.__matches_install_override_list

    @matches_install_override_list.setter
    def matches_install_override_list(self, matches):
        """
        Method setting whether or not something matches an override list.
        :param matches is a boolean representing whether the package matches an install_override_list
        """
        self.__matches_install_override_list = matches

    @property
    def available_edition(self):
        """
        Method for getting the available edition.
        """
        return self.__available_edition

    @available_edition.setter
    def available_edition(self, available_edition):
        """
        Method setting the available edition.
        :param available_edition is the available_edition to set.
        """
        self.__available_edition = available_edition

    @property
    def update_available(self):
        """
        True if the available edition is newer than the current one
        """
        if self.__update_available:
            return self.__update_available

        if not self.available_edition or not self.current_edition or self.available_edition == '0':
            return False
        return rpm_version.compare(self.current_edition, self.available_edition) < 0

    @update_available.setter
    def update_available(self, available):
        """
        Method for setting whether an update is available.
        :param boolean representing whether an update is available.
        """
        self.__update_available = available

    @property
    def matches_baseline(self):
        """
        Method for getting whether the package matches the baseline
        """
        return self.__matches_baseline

    @matches_baseline.setter
    def matches_baseline(self, matches_baseline):
        """
        Method setting whether the package matches the baseline.
        :param boolean representing whether it matches the baseline.
        """
        self.__matches_baseline = matches_baseline

    @property
    def compliance(self):
        """
        Method for getting the compliance.
        :returns the compliance as a string.
        """
        return self.__compliance

    @compliance.setter
    def compliance(self, compliance):
        """
        Method for getting the compliance.
        :param compliance is the compliance to set as a string.
        """
        self.__compliance = compliance

    @property
    def current_edition(self):
        """
        Method for getting the currently installed edition.
        :returns the installed edition as a string.
        """
        return self.__current_edition

    @current_edition.setter
    def current_edition(self, current_edition):
        """
        Method for setting the currently installed version.
        :param current_edition is the current edition to set as a string.
        """
        self.__current_edition = current_edition

    @property
    def installed_time(self):
        """
        Method for returning the timestamp.
        """
        return self.__installed_time

    @installed_time.setter
    def installed_time(self, timestamp):
        """
        Method for setting the timestamp
        :param timestamp as a string.
        """
        self.__installed_time = timestamp

    @property
    def installed(self):
        """
        Method for returning if the bean is an installed object.
        """
        return self.__installed

    @installed.setter
    def installed(self, installed):
        """
        Method for setting the installed
        """
        self.__installed = installed

    @property
    def locked(self):
        """
        Method for returning the locked.
        """
        return self.__locked

    @locked.setter
    def locked(self, locked):
        """
        Method for setting the locked
        """
        self.__locked = locked

    @property
    def severity(self):
        """
        Method for returning the severity as a List<string> of severity.
        """
        return self.__severity

    @severity.setter
    def severity(self, severity):
        """
        Method for setting the severity
        :param severity is a List<string> of severity.
        """
        self.__severity = severity

    @property
    def classification(self):
        """
        Method for returning the classification as a List<string>
        """
        return self.__classification

    @classification.setter
    def classification(self, classification):
        """
        Method for setting the classification.
        :param classification is a list<string> of classifications the package has.
        """
        self.__classification = classification

    @property
    def arch(self):
        """
        Method for returning the architecture (x86_64)
        """
        return self.__arch

    @arch.setter
    def arch(self, arch):
        """
        Method for setting the architecture (x86_64)
        """
        self.__arch = arch

    @property
    def name(self):
        """
        Method for returning the name of the package.
        """
        return self.__name

    @name.setter
    def name(self, name):
        """
        Method for setting the name of the package.
        """
        self.__name = name
    
    """
    Methods for defining built-in Python equality comparers. 
    These are defining the methods Python looks for in an equality comparison. 
    "hello world" > "hello world" is calling string.__gt__(self, other) or "hello world".__gt__("hello world")
    For more information on standard operators as functions, please see: https://docs.python.org/2/library/operator.html
    """

    def __lt__(self, other):
        return self.name < other.name

    def __gt__(self, other):
        return self.name > other.name

    def __eq__(self, other):
        return self.name == other.name

    def __le__(self, other):
        return self.name <= other.name

    def __ge__(self, other):
        return self.name >= other.name

    def __ne__(self, other):
        return self.name != other.name