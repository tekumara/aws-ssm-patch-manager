#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import logging
from patch_common import package_matcher
from datetime import datetime

logger = logging.getLogger()
UPDATE_INFO_DATE_FORMATS = [ "%a %b %d %H:%M:%S %Y", "%a %d %b %Y %I:%M:%S %p %Z"]

def convert_na2pkg_list_to_hash_list(package_list):
    """
    Method for returning a list of na2pkgs to a hash where the value is a list of packages.
    :param package_list: The list of packages to convert.
    :return: {(name,arch) => [packages]}
    """
    na2pkgs = {}
    if package_list:
        for pkg in package_list:
            if pkg and (pkg.name, pkg.arch) in na2pkgs:
                na2pkgs[(pkg.name, pkg.arch)].append(pkg)
            elif pkg:
                na2pkgs[(pkg.name, pkg.arch)] = [pkg]
    
    return na2pkgs

def append_na2pkg_hash_list_to_na2pkg_hash_list(package_hash_list_A, package_hash_list_B):
    """
    Method takes two hash lists of the form {(name, arch) => [packageA, packageB]} and adds missing from B to A.
    :param package_hash_list_A is the hash list to be appended TO.
    :param package_hash_list_B is the hash list that is looped through and appended TO package_hash_list_A
    :returns the list A with B added if no name, arch existed for it before.
    """
    for package in package_hash_list_B:
        if not (package.name, package.arch) in package_hash_list_A:
            package_hash_list_A[(package.name, package.arch)] = [package]

    return package_hash_list_A

def convert_na2pkg_list_to_hash(package_list):
    """
    Method for converting a list of na2pkgs to a hash. It is assumed the same package name and arch does not
    appear in the list.
    :param package_list: [pool items]
    :return: {(name,arch) => package}
    """
    na2pkgs = {}
    
    if package_list:
        for pkg in package_list:
            if pkg:
                na2pkgs[(pkg.name, pkg.arch)] = pkg

    return na2pkgs

def parse_release_time_from_patch_conflict(patch_conflict):
    """
    The release time is of format Wed 03 Jul 2019 04:56:12 PM UTC
    or  Wed Sep  9 20:03:15 2020 check for both formats
    :param patch_conflict: Object of type CLIPatchConflict
    :return: release time in seconds since epoch
    """
    for date_format in UPDATE_INFO_DATE_FORMATS:
        try:
            parsed_issued_date = datetime.strptime(patch_conflict.patch_release_time, date_format)
            issued_date_epoch_time = (parsed_issued_date - datetime(1970, 1, 1)).total_seconds()
            return str(issued_date_epoch_time)
        except Exception:
            pass

    logger.warn("Package %s contains unsupported date format %s. Defaulting to 01/01/1970", patch_conflict.name, patch_conflict.patch_release_time)
    return "0"

def parse_version_from_edition(edition):
    """
    Method for parsing current edition to return the version.
    Example: In suse the edition is "4.3.5-1.2.3" and the version is "4.3.5"
    """
    if(edition):
        return edition.split('-',1)[0].strip()
    else:
        return ""
        
def parse_release_from_edition(edition):
    """
    Method for parsing the release from the edition.
    :param edition is the edition to be parsed.
    Example: In suse the edition is "4.3.5-1.2.3" and the release is "1.2.3"
    """
    if edition and len(edition.split('-',1)) > 1:
        return edition.split('-',1)[1].strip()
    else:
        return ""