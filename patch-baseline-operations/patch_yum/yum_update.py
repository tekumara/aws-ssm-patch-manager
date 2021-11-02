# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common.constant_repository import ExitCodes
from patch_common.livepatch_utils import LIVEPATCH_ENABLED
from patch_common.livepatch_utils import remove_not_current_kernel_livepatches
from patch_common.metrics_service import append_runtime_metric_file_info
from patch_common.metrics_service import append_runtime_metric_traceback
import sys
import logging
import yum_base
import yum_display
import yum_metadata
import yum.Errors
import yum.i18n
import yum.plugins
from yum_package import YumPackage

logger = logging.getLogger()

def yum_update(baseline, override_list=None):
    """
    Uses the yum apis to update eligible packages.
    :param baseline: yum baseline
    :type baseline: yum_baseline.YumBaseline
    :param override_list: a list of patches to override installation decisions
    :return 0 if operation if success, 1 otherwise, 194 meaning restart the agent
    """

    yb = yum_base.setup_yum_base(baseline)

    update_metadata = yum_metadata.get_update_metadata(yb.repos.listEnabled())
    pkgs = _get_updatable_packages(yb, baseline, update_metadata, override_list)

    # Only import the kernel-livepatch plugin when livepatch is enabled.
    # Because kernel-livepatch is both interactive and core type plugin
    # Thus was not imported by default. The plugin also take care of logic of removing the
    # least common used kernel when there are more than installonly_limit of kernels
    # on the instance
    if LIVEPATCH_ENABLED == True:
        logger.info('Loading kernel-livepatch plugin.')
        pkgs = remove_not_current_kernel_livepatches(pkgs)
        yb.plugins._importplugins(yum.plugins.ALL_TYPES)

    pkg_tups = [ pkg.naevr for pkg in pkgs if pkg.check_requires(yb, baseline, override_list) ]
    has_dependency_check_failures = len(pkg_tups) < len(pkgs)
    for pkg_tup in pkg_tups:
        _update(yb, pkg_tup)

    # 0 -> nothing more to do, probably empty transaction set, i.e. no package to _update
    # 1 -> fatal error, should log
    # 2 -> continue the process
    # else -> unknown
    try:
        result, resultmsgs = yb.buildTransaction()
    except yum.plugins.PluginYumExit as e:
        logger.error(yum.i18n.exception2msg(e))
        append_runtime_metric_traceback()
        return ExitCodes.FAILURE
    except yum.Errors.YumBaseError as e:
        logger.error(yum.i18n.exception2msg(e))
        append_runtime_metric_traceback()
        return ExitCodes.FAILURE
    except KeyboardInterrupt:
        logger.warn('Exiting on user cancel')
        append_runtime_metric_traceback()
        return ExitCodes.FAILURE
    except IOError as e:
        logger.error(yum.i18n.exception2msg(e))
        append_runtime_metric_traceback()
        return ExitCodes.FAILURE
    except Exception as e:
        logger.exception(e)
        append_runtime_metric_traceback()
        return ExitCodes.FAILURE
    else:
        logger.debug("yum update result code: %d, message: %s", result, str(resultmsgs))
        if result == 0:
            logger.info("No updates, skipping.")
            if has_dependency_check_failures:
                append_runtime_metric_file_info("Yum has dependency check failure")
                return ExitCodes.DEPENDENCY_CHECK_FAILURE
            else:
                return ExitCodes.SUCCESS
        elif result == 1:
            logger.error("yum update failed with result code: 1, message: %s", resultmsgs)
            append_runtime_metric_file_info(str(resultmsgs))
            return ExitCodes.FAILURE
        elif result == 2:
            yum_display_callback = yum_display.YumDisplayCallBack()
            yb.processTransaction(rpmDisplay=yum_display_callback)
            # code 194 means success and amazon ssm agent need to do a reboot
            if has_dependency_check_failures:
                append_runtime_metric_file_info(str(resultmsgs))
                return ExitCodes.REBOOT_WITH_DEPENDENCY_CHECK_FAILURE
            else:
                return ExitCodes.REBOOT
        else:
            logger.error(resultmsgs)
            append_runtime_metric_file_info(str(resultmsgs))
            return ExitCodes.FAILURE
    finally:
        yum_base.release_lock(yb)


def _update(yb, pkg_tup):
    """
    Requests a package to be updated to a particular version.

    :param yb: yum base from yum library
    :param pkg_tup: (name, arch, epoch, version, release)
    """
    # NOTE: Despite the log statement, the package will not be updated if yum is given a version previous to the one currently installed.
    logger.info("Package name: %s, arch: %s to be updated to epoch: %s, version: %s, release: %s",
                pkg_tup[0], pkg_tup[1], pkg_tup[2], pkg_tup[3], pkg_tup[4])
    yb.update(name=pkg_tup[0],
              arch=pkg_tup[1],
              epoch=pkg_tup[2],
              version=pkg_tup[3],
              release=pkg_tup[4])

def _get_updatable_packages(yb, baseline, update_metadata, override_list=None):
    """
    Finds packages that match the baseline.

    :param yb: YumBase from yum
    :param baseline: to match packages against
    :param update_metadata: info matched against the baseline
    :param override_list: a list of patches to override installation decisions
    :return: a list of YumPackage to be updated
    """

    # Get all packages from the repo.
    known_pkgs = yum_metadata.get_available_pkgs(yb)
    known_pkgtuples = set([p.naevr for p in known_pkgs])
    na2_pkgs_known = get_na2_hash_package_list(known_pkgs)

    # Get installed packages with updates available.
    updatable_pkgs = yb.up.getUpdatesTuples()

    # Get all matching packages from notices.
    (matching_pkgs, na2_pkgs_known) = check_packages_with_notices(update_metadata, updatable_pkgs, na2_pkgs_known, known_pkgtuples, baseline, override_list)

    # Replace any matching packages from notices with later package versions that also matched the baseline and did not have any notices.
    matching_pkgs = check_packages_without_notices(yb, baseline, na2_pkgs_known, matching_pkgs, override_list)

    return matching_pkgs

def get_na2_hash_package_list(pkgs):
    """
    Method for converting a list of pkgs to a hash of form {(name, arch) => [pkg, pkg, ...]}
    :param pkgs is a list of packages with attributes .name and .arch on them.
    :returns list of pkgs to a hash of form {(name, arch) => [pkg, pkg, ...]}
    """
    na2_pkgs_known = {}
    for pkg in pkgs:
        if not (pkg.name, pkg.arch) in na2_pkgs_known:
            na2_pkgs_known[(pkg.name, pkg.arch)] = [pkg]
        else:
            na2_pkgs_known[(pkg.name, pkg.arch)].append(pkg)

    return na2_pkgs_known

def check_packages_with_notices(update_metadata, updatable_pkgs, na2_pkgs_known, known_pkgtuples, baseline, override_list):
    """
    Method for checking packages with notices against the baseline.
    :param updatable_pkgs - is a list of packages with available updates as tuples of the form [(latest_available_update, currently_installed package), (latest_available_update, currently_installed package), ...]
    :param na2_pkgs_known - is a a dict of packages available from the repo of form {(name, arch) => [YumPackage, YumPackage, ...]}
    :param known_pkgtuples - is a set of {(name, arch, epoch, version, release)} of known packages.
    :param baseline is the baseline for this operation.
    :param override_list is the cpa list if any.
    :returns (matching_packages, na2_pkgs_known) where matching_packages is a dictionary of packages that matched the baseline of
    form {(name, arch) => package} and the dict of na2_pkgs_known with packages that were already checked via notices removed.
    """
    matching_pkgs = {}
    for update in sorted(updatable_pkgs, key=lambda x: x[1]):
        installed_pkg_tup = update[1]

        notices = update_metadata.get_applicable_notices(installed_pkg_tup)

        new_package = None
        if len(notices) > 0:
            (new_package, na2_pkgs_known) = get_matching_package_from_notices(notices, installed_pkg_tup, na2_pkgs_known,\
            known_pkgtuples, baseline, override_list)

        if new_package:
            matching_pkgs[(new_package.name, new_package.arch)]= new_package

    return (matching_pkgs, na2_pkgs_known)

def get_matching_package_from_notices(notices, installed_pkg_tup, na2_pkgs_known, known_pkgtuples, baseline, override_list = None):
    """
    Method for getting a package from a list of notices for package that matches the baseline.
    :param notices - is a list of notices from yum for a particular package.
    :param installed_pkg_tup - is the currently installed version of the package the notices were retrieved for.
    :param na2_pkgs_known is a dictionary of {(name, arch) => [YumPackage, YumPackage,...]} of all packages in the repo.
    :param known_pkgtuples is a set of {(name, arch, epoch, version, release)} of known packages.
    :param baseline is the baseline for this operation.
    :override list is the cpa list if any.
    :returns tuple (pkg, na2_pkgs_known)latest package from notices that match the baseline(if available) else None and the na_2pkgs_known with packages that were checked
    during this call removed.
    """

    matching_pkg = None
    for (new_pkgtup, notice) in notices:
        notice_pkg = YumPackage.from_tuple_notice(new_pkgtup, notice)
        # Remove from full list of packages
        # remove from na2_pkgs_known
        # Filter packages from notice out of na2_pkgs_known so we don't match against baseline and override list twice
        na2_pkgs_known = remove_from_known_packages(notice_pkg, na2_pkgs_known)

        # Do not choose the one that's already installed, as yum will take that as meaning we want to update to the latest version
        if notice_pkg.is_matched(baseline, override_list) and (notice_pkg.epoch != installed_pkg_tup[2] or notice_pkg.version != installed_pkg_tup[3] or notice_pkg.release != installed_pkg_tup[4]):
            if  new_pkgtup in known_pkgtuples and not matching_pkg:
                matching_pkg = notice_pkg
                # since notices are ordered new->old, first match should be kept
                # We don't break here to keep removing all packages found in notices from the known_pkgs list.
            else:
                logger.warn("package: %s not available from repo", str(new_pkgtup))

    return(matching_pkg, na2_pkgs_known)

def remove_from_known_packages(notice_pkg, na2_pkgs_known):
    """
    Method for removing a package that was found in a notice and already checked against the baseline from
    the list of known packages to prevent it from being checked against the baseline AGAIN without the notice information.
    :param notice_pkg is a notice package that was just checked (or just about to be checked) against the baseline.
    :na2_pkgs_known is a dictionary of known packages of shape {(name, arch) => [YumPackage, YumPackage, ...]}
    """
    if((notice_pkg.name, notice_pkg.arch) in na2_pkgs_known):
        for known in list(na2_pkgs_known[(notice_pkg.name, notice_pkg.arch)]):
            notice_pkg_tup = (notice_pkg.name, notice_pkg.arch, notice_pkg.epoch, notice_pkg.version, notice_pkg.release)
            # important to compare up to release (else causes bug where na2_pkgs_known is not in the right state for replace_latest_package_matching_baseline_in_list())
            if(known.naevr[0:5] == notice_pkg_tup[0:5]):
                na2_pkgs_known[(notice_pkg.name, notice_pkg.arch)].remove(known)

    return na2_pkgs_known


def check_packages_without_notices(yb, baseline, na2_pkgs_known, na2_matching_pkgs, override_list = None):
    """
    Method for replacing matching packages that came from notices with packages that also matched baseline, did not have a notice
    and are a later version than the version in the notices.
    :param yb - the yum base
    :param baseline - is the yum_baseline.py
    :param na2_pkgs_known - is a dictionary { (name, arch) => List<YumPackage> } of all the remaining packages that were
    :param found in the repo's with the packages found in a notice removed.
    :param notice_packages - are all of the packages found that match the baseline and were in a notice. Can be empty.
    :param na2_matching_pkgs - packages with a notice that were found to match the baseline.
    """

    # Get the list of all installed packages with their latest updates as a tuple.
    updatable_pkgs = yb.up.getUpdatesTuples()
    # eg. (('kernel', 'x86_64', '0', '3.10.0', '957.21.3.el7'), ('kernel', 'x86_64', '0', '3.10.0', '957.1.3.el7'))

    # For each installed package with update available.
    for update in sorted(updatable_pkgs, key=lambda x: x[1]):

        tuples = yb.pkgSack.packagesByTuple(update[1])
        buildtime = tuples[0].buildtime if len(tuples) > 0 else 0.0
        # Get the installed package.
        installed_pkg = YumPackage(pkg_tup=update[1], buildtime = buildtime)
        # If there is a package of that name and architecture in the repository.
        if((installed_pkg.name, installed_pkg.arch) in na2_pkgs_known):
            # Replace the package found in a notice with later version also matching baseline (if available)
            # or add candidate if no package exists in the matching list.
            na2_matching_pkgs = replace_latest_package_matching_baseline_in_list(baseline, override_list, installed_pkg, na2_pkgs_known, na2_matching_pkgs)

    return [na2_matching_pkgs[na] for na in na2_matching_pkgs]

def replace_latest_package_matching_baseline_in_list(baseline, override_list, installed_pkg, na2_pkgs_known, na2_matching_pkgs):
    """
    Method for finding the latest package from a list that matches the baseline and replacing the package in the provided matching list.
    :param baseline - is the yum baseline.
    :param override_list is the install override list.
    :param - installed_pkg is the package being checked.
    :param na2_pkgs_known is the list of known packages as a dictionary {(name, arch) => [PackageVersionA, PackageVersionB, ...]}
    :param na2_matching_pkgs is the list of latest packages found to match the baseline.
    :returns the na2_matching_pkgs list with the candidate updated or added if relevant.
    """
    for pkg in na2_pkgs_known[(installed_pkg.name, installed_pkg.arch)]:
        if pkg.is_matched(baseline, override_list):
            # If there is already a candidate in the list of matching packages
            if ((pkg.name, pkg.arch) in na2_matching_pkgs):
                # Check to see if it should replace the current candidate.
                # Do not choose the one that's already installed, as yum will take that as meaning we want to update to the latest version
                if na2_matching_pkgs[(pkg.name, pkg.arch)].compare_version(pkg) < 0 and installed_pkg.compare_version(pkg) != 0:
                    na2_matching_pkgs[(pkg.name, pkg.arch)] = pkg
            # else if there is not a candidate, set this package as the candidate.
            elif installed_pkg.compare_version(pkg) != 0:
                na2_matching_pkgs[(pkg.name, pkg.arch)] = pkg

    return na2_matching_pkgs
