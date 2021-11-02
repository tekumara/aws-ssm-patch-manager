# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import datetime
import logging
import yum
from patch_common import package_matcher

logger = logging.getLogger()


def get_update_notice_packages(notice):
    """
    :param notice: update notice from yum 
    :return: packages in the update notice
    """
    ret = []
    for upkg in notice['pkglist']:
        for pkg in upkg['packages']:
            ret.append((pkg['name'], pkg['arch'], pkg.get('epoch') or '0', pkg['version'], pkg['release']))
    return ret


def get_update_notice_timestamp(notice):
    """
    Note: the timestamp string can be in 4 forms:
    "2016-12-06", "2016-12-06 09:43", "2016-12-06 09:43:08 UTC" or
    "2016-12-06 09:43:08", treat all as UTC

    Note: the timestamp string can be found in 2 attrs:
    "issued" and "updated", use the "updated" if present.

    :param notice: update notice from yum 
    :return: datetime object
    """

    # not sure (since this is Linux) if can be case
    # where both the "updated" and "issued" can be empty
    # string or None, if so, threat this update notice
    # as being issued at 1970 01 01
    default_datetime = datetime.datetime(1970, 1, 1)
    timestamp = notice["updated"]
    if timestamp is None:
        timestamp = notice["issued"]
    if timestamp is None:
        return default_datetime

    try:
        return datetime.datetime.strptime(timestamp[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        pass

    try:
        return datetime.datetime.strptime(timestamp[:16], "%Y-%m-%d %H:%M")
    except ValueError as e:
        pass

    try:
        return datetime.datetime.strptime(timestamp[:13], "%Y-%m-%d %H")
    except ValueError as e:
        pass

    try:
        return datetime.datetime.strptime(timestamp[:10], "%Y-%m-%d")
    except ValueError as e:
        pass

    logger.warn("Unable to parse timestamp on update notice: %s, "
                + "update notice id: %s, "
                + "example format: 1970-01-01 00:00:00, "
                + "treat this update notice issued from 1970 Jan 1st.",
                timestamp, notice['update_id'])
    return default_datetime


def get_classification_update_notice(notice):
    """
    :param notice: update notice
    :return: whether a update notice is of type security
    """
    return notice['type'].title()


def is_classification_update_notice(notice, classes):
    """
    :param notice: update notice
    :param classes: a list of classifications
    :return: whether a update notice is of type security
    """
    return get_classification_update_notice(notice).lower() in map(lambda x: x.lower(), classes)


def get_severity_update_notice(notice):
    """
    :param notice: update notice
    :return: whether a update notice is of type security
    """
    sev = notice['severity']
    if sev is None:
        # this is can often be seen in bugfix update notice
        # somethings the severity value appears and show as 'None'
        # somethings the severity value does not show and we get a python None
        # the solution is to combine that together
        sev = "None"
    return sev.title()


def is_severity_update_notice(notice, sevs):
    """
    :param notice: update notice
    :param sevs: a list of severities
    :return: whether a update notice fits the severity
    """
    return get_severity_update_notice(notice).lower() in map(lambda x: x.lower(), sevs)


def is_update_notice_match_advs(notice, advs):
    """
    :param notice: update notice
    :param advs: a list of advisory ids
    :return: whether a update notice fits the advisory ids
    """
    return notice['update_id'] in advs


def is_update_notice_match_cves(notice, cves):
    """
    :param notice: update notice
    :param cves: a list of cve ids
    :return: whether a update notice fits the cve ids
    """
    for ref in notice['references'] or []:
        if ref['type'] and ref['type'].lower() == "cve" and ref['id'] and ref['id'] in cves:
            return True
    return False


def is_update_notice_match_bzs(notice, bzs):
    """
    :param notice: update notice
    :param bzs: a list of bugzilla ids
    :return: whether a update notice fits the bugzilla ids
    """
    for ref in notice['references'] or []:
        if ref['type'] and ref['type'].lower() == "bugzilla" and ref['id'] and ref['id'] in bzs:
            return True
    return False


def match_notice_explicit(explicitList, notice):
    """
    :param explicitList: an explicit list of patches
    :param notice: update notice from yum
    :return: True if the notice is wanted explicitly, False otherwise
    """
    return is_update_notice_match_advs(notice, explicitList) or \
           is_update_notice_match_bzs(notice, explicitList) or \
           is_update_notice_match_cves(notice, explicitList)


def match_yum_package(regexes, pkg_tup):
    """
    :param regexes: list of regex for matching
    :param pkg_tup: package tuple, (n,a,e,v,r)
    :return: True to matches, False otherwise
    """
    return package_matcher.match_package(regexes, package_matcher.generate_package_data(pkg_tup), yum.misc.re_glob)

def get_cve_update_notice(notice):
    """
    :param notice: update notice
    :return: a list of cve ids
    """
    cves = []
    for ref in notice['references'] or []:
        if ref['type'] and ref['type'].lower() == "cve" and ref['id']:
            cves.append(ref['id'])
    return cves
