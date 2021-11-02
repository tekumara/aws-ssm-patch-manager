# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.


class BasePackage:
    compliance_critical = "CRITICAL"
    compliance_high = "HIGH"
    compliance_medium = "MEDIUM"
    compliance_low = "LOW"
    compliance_informational = "INFORMATIONAL"
    compliance_unspecified = "UNSPECIFIED"
    compliance_level = {
        compliance_critical: 5,
        compliance_high: 4,
        compliance_medium: 3,
        compliance_low: 2,
        compliance_informational: 1,
        compliance_unspecified: 0
    }

    def __init__(self, name, arch, compliance):
        self.name = name
        self.arch = arch
        self.compliance = compliance

    def compare_name_arch(self, othr):
        if self.name < othr.name:
            return -1
        elif self.name > othr.name:
            return 1
        elif self.arch < othr.arch:
            return -1
        elif self.arch > othr.arch:
            return 1
        else:
            return 0

    def compare_version(self, othr):
        """
        :param othr: package from us
        :return: -1 if self is older than othr, 0 if equal, > 0 if self is newer
        """
        raise Exception()

    def compare_compliance(self, othr):
        return BasePackage.compliance_level[self.compliance] - \
               BasePackage.compliance_level[othr.compliance]

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

    def duplicate(self):
        """
        create a duplicate of self
        :return: duplicate of self
        """
        raise Exception()

    def __lt__(self, other):
        return compare_package(self, other) < 0

    def __gt__(self, other):
        return compare_package(self, other) > 0

    def __eq__(self, other):
        return compare_package(self, other) == 0

    def __le__(self, other):
        return compare_package(self, other) <= 0

    def __ge__(self, other):
        return compare_package(self, other) >= 0

    def __ne__(self, other):
        return compare_package(self, other) != 0


def compare_package(this, other):
    """
    :param this: package from us
    :param other: package from us
    :return: -1 if this package should be less than other package, 0 if equal,
    1 if this package should be larger than other package.
    """
    ret = this.compare_name_arch(other)
    if ret != 0:
        return ret
    ret = this.compare_version(other)
    if ret != 0:
        return ret
    return this.compare_compliance(other)
