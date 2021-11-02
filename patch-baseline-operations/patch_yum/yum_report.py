# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import sys

import yum_base
import yum_package
import yum_metadata
from patch_common.package_inventory import PackageInventory
from patch_common.metrics_service import append_runtime_metric_traceback

import yum_update_notice
import yum_package

logger = logging.getLogger()


# TODO not UTed
def yum_report(baseline, operation_type, override_list=None):
    """
    :param baseline: baseline
    :type baseline: patch_yum.yum_baseline.YumBaseline
    :param operation_type: scan or install
    :type operation_type: str
    """
    yb = None
    try:
        yb = yum_base.setup_yum_base(baseline)
        update_metadata = yum_metadata.get_update_metadata(yb.repos.listEnabled())
        (installed, installed_other, missing, not_applicable, installed_rejected, failed) = _report_package(yb, baseline, update_metadata, override_list)

        return PackageInventory(
            operation_type=operation_type,
            pkg_type="yum",
            installed_pkgs=installed,
            installed_other_pkgs=installed_other,
            not_applicable_pkgs=not_applicable,
            missing_pkgs=missing,
            installed_rejected_pkgs=installed_rejected,
            failed_pkgs=failed,
            override_list=override_list
        )
    except Exception as e:
        logger.error("Unable to generate a yum package report.")
        logging.exception(e)
        append_runtime_metric_traceback()
        return None
    finally:
        if yb is not None:
            yum_base.release_lock(yb)


def _get_package_installed(yb):
    """
    :param yb: yum base from yum
    :return: installed packages as a list of YumPackage
    """
    na2pkg = {}  # {(name, arch) -> set(package)}
    package_installed = []
    for pkg in sorted(yb.rpmdb.returnPackages()):
        name_arch = (pkg.name, pkg.arch)

        yum_pkg = yum_package.YumPackage(
            (pkg.name, pkg.arch, pkg.epoch, pkg.version, pkg.release),
            installed_time=_get_package_installed_time(pkg)
        )
        if name_arch in na2pkg and na2pkg[name_arch]:
            na2pkg[name_arch].append(yum_pkg)
        else:
            na2pkg[name_arch] = [yum_pkg]

    for name_arch in na2pkg:
        na2pkg[name_arch].sort(reverse=True)
        package_installed.append(na2pkg[name_arch][0])

    return package_installed

def _get_package_installed_time(pkg):
    """
    Method to help get the installed time of a RPM installed package
    :param pkg: installed package as an instance of RPMInstalledPackage
    :return: installed time in EPOCH timestamp if exists, otherwise None
    """
    try:
        # Magic method to get the install time
        return pkg.tagByName('INSTALLTIME')
    except:
        # Ignore if we can't get the installed time
        pass


def _get_package_in_baseline(yb, baseline, update_metadata):
    """
    :param yb: yum base from yum
    :param baseline: yum baseline from us
    :return: list of YumPackage matching the baseline
    """
    available_pkgs = yum_metadata.get_available_pkgs(yb)
    available_pkgtups = set([p.naevr for p in available_pkgs])

    # second find the qualified packages which are applicable to arch and in baseline
    package_in_baseline = []
    na2pkgs = baseline.get_na2pkgs(update_metadata.get_notices(), available_pkgs)

    for na in na2pkgs:
        for pkg in na2pkgs[na]:
            if pkg.arch not in yb.arch.archlist:
                continue
            # in case notices reference packages not in the current repo setup
            if pkg.naevr in available_pkgtups:
                package_in_baseline.append(pkg)
            break

    return package_in_baseline

def _report_package(yb, baseline, update_metadata, override_list=None):
    """
    :param yb: yum base from yum
    :param baseline: yum baseline from us
    :param update_metadata: update metadata from yum
    :return: tuples of installed, installed other,
             missing and not applicable arrays of yum packages
    """
    package_installed = _get_package_installed(yb)
    package_in_baseline = _get_package_in_baseline(yb, baseline, update_metadata)

    # convert existing list of packages to {(n, a) -> pkg}
    na2pkg_installed = {}
    for pkg in package_installed:
        na2pkg_installed[(pkg.name, pkg.arch)] = pkg

    na2pkg_in_baseline = {}
    package_cves_dict = {}
    for pkg in package_in_baseline:
        check_pkgs_for_cves(pkg, na2pkg_installed, package_cves_dict)
        na2pkg_in_baseline[(pkg.name, pkg.arch)] = pkg

    na2pkg_in_override_list = get_na2pkg_with_override_list(yb, update_metadata, override_list) or {}

    ret_installed = []
    ret_installed_other = []
    ret_missing = []
    ret_not_applicable = []
    ret_installed_rejected = []
    ret_failed = []

    # package installed but not in baseline
    for na in na2pkg_installed:
        if na not in na2pkg_in_baseline:
            if baseline.block_rejected_patches and na2pkg_installed[na].is_rejected(baseline):
                ret_installed_rejected.append(na2pkg_installed[na])
            else:
                ret_installed_other.append(na2pkg_installed[na])

    # package not installed but in baseline
    for na in na2pkg_in_baseline:
        if na not in na2pkg_installed:
            ret_not_applicable.append(na2pkg_in_baseline[na])

    # packages installed and in the override list
    for na in na2pkg_in_override_list:
        if na in na2pkg_installed:
            # if the installed is older than override list, i.e. failed to install with the override list
            if na2pkg_installed[na].compare_version(na2pkg_in_override_list[na]) < 0:
                ret_failed.append(na2pkg_in_override_list[na])

    # package installed and in baseline
    for na in na2pkg_in_baseline:
        if na in na2pkg_installed:
            # if the installed is older than in baseline, i.e. missing or failed
            if na2pkg_installed[na].compare_version(na2pkg_in_baseline[na]) < 0:

                if na in na2pkg_in_override_list:
                    # if the version in override list is older than in baseline, missing
                    if na2pkg_in_override_list[na].compare_version(na2pkg_in_baseline[na]) < 0:
                        update_missing_pkg_with_cves(na2pkg_in_baseline[na],package_cves_dict)
                        ret_missing.append(na2pkg_in_baseline[na])
                else:
                    update_missing_pkg_with_cves(na2pkg_in_baseline[na],package_cves_dict)
                    # mark pkgs as missing when it is in the baseline but not in the override list
                    ret_missing.append(na2pkg_in_baseline[na])

            # if the installed is newer than in baseline, i.e. no update
            else:
                # use the compliance, classification and severity attr from baseline
                na2pkg_installed[na].compliance = na2pkg_in_baseline[na].compliance
                na2pkg_installed[na].classification = na2pkg_in_baseline[na].classification
                na2pkg_installed[na].severity = na2pkg_in_baseline[na].severity
                ret_installed.append(na2pkg_installed[na])

    ret_installed.sort(key=lambda x: (x.name, x.arch))
    ret_installed_other.sort(key=lambda x: (x.name, x.arch))
    ret_missing.sort(key=lambda x: (x.name, x.arch))
    ret_not_applicable.sort(key=lambda x: (x.name, x.arch))

    return ret_installed, ret_installed_other, ret_missing, ret_not_applicable, ret_installed_rejected, ret_failed


def get_na2pkg_with_override_list(yb, update_metadata, override_list=None):
    """
    TODO combine this method with method get_na2pkg in yum_baseline.py - 06/04/18 ouyangx@

    :param yb: all installed packages as tuples
    :param update_metadata: array of update notice from yum
    :param override_list: a list of patches to override installation decisions
    :return: dictionary (name+arch) -> set(YumPackage) the baseline matches, ordered by compliance
    """
    if override_list is not None:
        notices = update_metadata.get_notices()
        available_pkgs = yum_metadata.get_available_pkgs(yb)
        available_tuples = set([p.naevr for p in available_pkgs])

        pkgs = []
        processed_pkg_tup = set()

        for notice in notices:
            classification = yum_update_notice.get_classification_update_notice(notice)
            severity = yum_update_notice.get_severity_update_notice(notice)

            pkg_tups = yum_update_notice.get_update_notice_packages(notice)

            for pkg_tup in pkg_tups:
                processed_pkg_tup.add(pkg_tup)

                notice_pkg = yum_package.YumPackage(
                    pkg_tup,
                    classification=classification,
                    severity=severity)
                if notice_pkg.is_applicable(yb, available_tuples) and notice_pkg.match_override_list(override_list):
                    pkgs.append(notice_pkg)

        # check for notice-less packages
        for pkg in available_pkgs:
            if pkg.naevr not in processed_pkg_tup:
                yum_pkg = yum_package.YumPackage(pkg.naevr, buildtime=pkg.buildtime)
                if yum_pkg.is_applicable(yb, available_tuples) and yum_pkg.match_override_list(override_list):
                    pkgs.append(yum_pkg)

        return build_na2pkg(pkgs)

def build_na2pkg(pkgs):
    na2pkg = {}
    for pkg in pkgs:
        na = (pkg.name, pkg.arch)  # (name, arch)

        # {(name, arch) -> set(YumPackage)}
        if na2pkg.get(na) is not None:
            na2pkg[na].add(pkg)
        else:
            na2pkg[na] = set([pkg])

    for na in na2pkg:
        # make into a sorted list
        pkg_list = list(na2pkg[na])
        pkg_list.sort(reverse=True)
        na2pkg[na] = pkg_list[0] # {(name, arch) -> YumPackage}

    return na2pkg

def check_pkgs_for_cves(pkg, na2pkg_installed, pkg_cves_dict):
    """
    Checks if package is a valid update and also contains CVEs
    :param pkg: YumPackage object
    :param na2pkg_installed: dictonary of packages installed {(n, a) -> pkg}
    :param pkg_cves_dict: Dict of (name, arch) => CVE Set
    """
    if pkg.cve_ids and (pkg.name, pkg.arch) in na2pkg_installed and pkg.compare_version(na2pkg_installed[(pkg.name, pkg.arch)]) > 0:
        update_cves(pkg, pkg_cves_dict)

def update_cves(pkg, pkg_cves_dict):
    """
    Adds or updates CVEs that are related to a given package
    :param pkg: YumPackage Object
    :param pkg_cves_dict: Dict of (name, arch) => CVE Set
    """
    cve_set = pkg_cves_dict.get((pkg.name, pkg.arch), set())
    cve_ids = pkg.cve_ids
    update_cve_set(cve_set, cve_ids)
    pkg_cves_dict[(pkg.name,pkg.arch)] = cve_set

def update_cve_set(cve_set, cve_ids):
    for cve in cve_ids:
        cve_set.add(cve)

def update_missing_pkg_with_cves(pkg,pkg_cves_to_report):
    """
    Update missing packages with CVEs it remediates
    :param pkg: list of missing YumPackage objects
    :param pkg_cves_to_report: Dict of (name, arch) => CVE Set
    """
    if (pkg.name, pkg.arch) in pkg_cves_to_report:
        pkg.all_known_cves_for_update = list(pkg_cves_to_report[(pkg.name, pkg.arch)])
