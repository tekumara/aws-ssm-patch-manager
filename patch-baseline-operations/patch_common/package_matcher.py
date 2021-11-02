import re
import fnmatch
import logging

logger = logging.getLogger()

# n = name
# a = architecture
# e = epoch
# v = version
# r = release
FULL_PACKAGE_PROPERTIES = "naevr"

# Default codes used to generate package matching data from metadata
# To use the default codes, the package needs to have all data for naevr
DEFAULT_CODES = ['n', 'na', 'nvra', 'nv', 'nvr', 'envra', 'nevra', 'nevr', 'v', 'vr', 'evr', 'naevr']

# Special codes for APT because no epoch and release for APT pkgs
APT_CODES = ['n', 'v', 'na', 'nv', 'av', 'nav']


def generate_package_data(naevr, codes=DEFAULT_CODES, formatter = None):
    """
    Method to generate package data that can be used to match package
    :param naevr package metadata in the format of (name, arch, epoch, version, release)
    :param codes a list of code to be generated from the given metadata
    :param formatter is a method for formatting combinations of patterns. For example, 
    if you specify (curl.x86_64) with a version and you want a dot (.) after arch instead
    of a colon (:), the formatter is what formats combinations. If no formatter is provided,
    the default get_format method is used. 
    :return: a list of package data that can be used for package matching
    """
    properties = set()
    for code in codes:
        properties.update(list(code))

    for p in properties:
        if p not in FULL_PACKAGE_PROPERTIES:
            raise Exception("Provided unsupported package property '%s' in the requested codes %s", p, codes)

        if naevr[FULL_PACKAGE_PROPERTIES.index(p)] is None:
            raise Exception("%s is in the requested codes but not value in metadata %s", p, naevr)
    if formatter:
        return [formatter(code) % get_metadata_tuple(naevr, code) for code in set (codes)]
    else:
        return [get_format(code) % get_metadata_tuple(naevr, code) for code in set(codes)]


def get_metadata_tuple(naevr, code):
    """
    Get metadata tuple from given code, e.g. 'nav' -> (name, arch, version)
    :param naevr package metadata in the format of (name, arch, epoch, version, release)
    :param code string code to be generated from the given metadata, e.g. 'nav'
    :return: tuple of requested metadata, e.g. (name, arch, version)
    """
    return tuple([naevr[FULL_PACKAGE_PROPERTIES.index(c)] for c in code])


def get_format(code):
    """
    Get data format to generate package data that will be used to match pkgs, e.g. 'nav' -> '%s.%s:%s'
    See more examples of code -> format pairs in the unit tests"
    :param code: code to be generated, e.g. 'nav'
    :return: generated format
    """
    format = ""
    for i in range(0, len(code)):
        format += "%s"
        if i < len(code) - 1:
            if code[i + 1] == 'a': # arch always preceded by dot
                format += '.'
            elif code[i] == 'e' or code[i] == 'a': # epoch and arch always followed by colon
                format += ':'
            else:
                format += '-'
    return format


def is_applicable_regex(string):
    """
    Method to check if a string is regex or not, this can be used for ZYPP and APT

    :param string: a string to be checked
    :return: True for applicable regex, False otherwise
    """
    # the regex below is copied from yum
    return re.compile('[*?]|\[.+\]').search(string) is not None


def match_package_data(str_to_match, pkg_data, regex_checker=None):
    """
    Match a provided string with a provided package data

    :param str_to_match: string to be matched
    :param pkg_data: a set/list of pkg data in string that can be used to match pkg
    :param regex_checker: a supplier method to check whether the string is a regex or not
    :return: boolean to indicate whether the pkg is matched with the string or not
    """
    # convert all to lower case so that it won't be case sensitive
    # Todo add case-sensitive matching if needed
    str_to_match = str_to_match.lower()
    pkg_data = [each.lower() for each in pkg_data]

    if str_to_match in pkg_data:
        return True

    if regex_checker:
        is_regex = regex_checker(str_to_match)
    else:
        is_regex = is_applicable_regex(str_to_match)

    if is_regex:
        regexp_match = re.compile(fnmatch.translate(str_to_match)).match
        for item in pkg_data:
            if regexp_match(item):
                return True

    return False


def match_package_data_strict(strs_to_match, pkg_data, regex_checker=None):
    """
    Match provided strings with provided package data, which is a strict matching

    :param strs_to_match: a list of strings to be matched
    :param pkg_data: a set/list of pkg data in string that can be used to match pkg
    :param regex_checker: a supplier method to check whether the string is a regex or not
    :return: boolean to indicate whether the pkg is matched with all provided strings or not
    """
    for str_to_match in strs_to_match:
        is_matched = match_package_data(str_to_match, pkg_data, regex_checker)
        if not is_matched:
            return False
    # True only when the pool matches all strings in the list
    return True


def match_package(matches, pkg_data, regex_checker=None):
    """
    :param matches: a list of strings/lists for matching
    :param pkg_data: a set/list of pkg data in string that can be used to match pkg
    :param regex_checker: a supplier method to check whether the string is a regex or not
    :return: True to matches, False otherwise
    """

    for match in matches:
        match_type = type(match)
        if match_type is list or match_type is set:
            # match is a list of strings and the pkg needs to match all strings in the list
            if match_package_data_strict(match, pkg_data, regex_checker):
                return True
        else:
            # Found the type for the rejected patches could also be unicode not just str
            # Hence, match could be a string or unicode
            # Just in case there could be other string types, convert it to str below
            if match_package_data(str(match), pkg_data, regex_checker):
                return True

    return False

# # TODO : Make package attribute consistent across different os.
def get_package_title(operating_system, package):
    """
    :param operating_system: operating system
    :param package: package
    :return: the package title for package and os combination
    """
    if operating_system.lower() in ["debian", "raspbian", "ubuntu"]:
        return get_format('nav') % (package.name, package.architecture, package.version)
    elif operating_system.lower() == "macos":
        return "%s.%s"%(package.name, package.version)
    else:
        return get_format('naevr') % (package.name, package.arch, package.epoch, package.version, package.release)


def get_package_id(operating_system, package):
    """
    :param operating_system: operating system
    :param package: package
    :return: the package id for package and os combination
    """
    if operating_system.lower() in ["debian", "raspbian", "ubuntu"]:
        return get_format('na') % (package.name, package.architecture)
    elif operating_system.lower() == "macos":
        return "%s"%(package.name)
    else:
        return get_format('na') % (package.name, package.arch)

def get_package_patch_severity(operating_system, package):
    """
    :param operating_system: operating system
    :param package: package
    :return: the package patch severity for package and os combination
    """
    return package.priority if operating_system.lower() in ["debian", "raspbian", "ubuntu"] else package.severity

def get_package_severity(operating_system, package):
    """
    :param operating_system: operating system
    :param package: package
    :return: the package severity for package and os combination
    """
    return package.compliance_level if operating_system.lower()  in ["debian", "raspbian", "ubuntu"] else package.compliance

def get_package_classification(operating_system, package):
    """
    For Debian & Ubuntu, if a package is security patch, classification would return "security", if not, return ""
    :param operating_system: operating system
    :param package: package
    :return: the package classification for package and os combination
    """
    if operating_system.lower() in ["debian", "raspbian", "ubuntu"]:
        if package.candidate_pkg_ver and package.candidate_pkg_ver.is_security:
            return "Security"
        else:
            return ""
    return package.classification or ""

def get_package_cves(operating_system, package):
    """
    :param operating_system: operating system
    :param package: package
    :return: the cves which this package helps remediate
    """
    unsupported_operating_systems = ["ubuntu", "debian", "macos", "raspbian"]
    if operating_system.lower() not in unsupported_operating_systems:
        return ",".join(package.all_known_cves_for_update)
    else:
        return ""
