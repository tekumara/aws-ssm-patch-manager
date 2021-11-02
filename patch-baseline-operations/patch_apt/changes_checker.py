import logging
from patch_common.package_matcher import match_package, generate_package_data, APT_CODES
from patch_apt.constants import PACKAGE_LOGGING_SEPARATOR, ProblemType
from patch_apt.change import Change

logger = logging.getLogger()
# TODO: generalize logging messages


def get_pending_changes(cache):
    """
    Get pending changes from the apt cache, includes packages to be installed/upgraded/deleted/broken
    :param cache: apt cache to be checked
    :return: tuple of maps of packages for installs/upgrades/deletes/brokens,
             where the key is the pkg name and value is pkg object
    """
    installs = {}
    upgrades = {}
    deletes = {}
    brokens = {}
    for pkg in cache:
        if pkg.marked_install:
            installs[pkg.name] = pkg
        elif pkg.marked_upgrade:
            upgrades[pkg.name] = pkg
        elif pkg.marked_delete:
            deletes[pkg.name] = pkg
        elif pkg.is_now_broken or pkg.is_inst_broken:
            brokens[pkg.name] = pkg
    return installs, upgrades, deletes, brokens


def format_pending_changes(changes):
    """
    Format logging of pending changes
    :param changes: A list of packages that could be changed
    :return: string of formatted log
    """
    installs, upgrades, deletes, brokens = changes

    return "Install: %s\n Upgrade: %s\n Delete: %s\n Broken packages: %s" \
           % (_format_pending_pkgs(installs.values()),
              _format_pending_pkgs(upgrades.values()),
              _format_pending_pkgs(deletes.values()),
              _format_pending_pkgs(brokens.values()))


def _format_pending_pkgs(pending_pkgs):
    """
    Format logging of pending changes
    :param pending_pkgs: A list of packages that could be changed
    :return: string of formatted log
    """
    if pending_pkgs:
        return PACKAGE_LOGGING_SEPARATOR.join(
                [ _format_pending_pkg(pkg) for pkg in pending_pkgs]
            )
    return "N/A"


def _format_pending_pkg(pkg):
    """
    Format logging of pending package change
    :param pkg: pending package that could be changed
    :return: string of formatted log
    """
    if pkg.candidate or pkg.installed:
        if pkg.is_installed and pkg.marked_upgrade:
            return "%s(%s->%s)" % (pkg.fullname, pkg.installed.version, pkg.candidate.version)
        else:
            return "%s(%s)" % (pkg.fullname, pkg.installed.version if pkg.is_installed else pkg.candidate.version)
    return pkg.fullname


def _check_broken_packages(problems, main_pkg_ver, brokens_before, brokens_after=None, deletes_after=None):
    """
    Check the broken packages before and after the fix
    :param problems: a map of solvable problems in the format of pkg_name:Change
    :param main_pkg_ver: the main PackageVersion triggered the pending changes
    :param brokens_before: a map of pending broken packages after marking (not committed yet) a package to upgrade
                           but 'BEFORE' fixing dependencies, e.g. upgrading B from v1 to v2 could make A broken
                           as A has v1 installed and is depending on B v1
    :param brokens_after: a map of pending broken packages after marking (not committed yet) a package to upgrade
                           and 'AFTER' fixing dependencies
    :param deletes_after: a map of packages that are pending deletion after marking (not committed yet)
                          a package to upgrade and 'AFTER' fixing dependencies, e.g. upgrading B from v1 to v2
                          could make A broken as A has v1 installed and is depending on B v1, after fix,
                          A v1 could be marked to be removed to fix it. In this case, the fix is not acceptable
    :return: True if pass check, otherwise False
    """
    pass_check = True
    # If no fix and before fix broken, there exists broken pkg -> fail
    # If exists fix and after fix broken, there still exists broken pkg -> fail the fix
    brokens = brokens_after if brokens_after is not None else brokens_before
    if brokens:
        # This is corresponding to ProblemType.BROKEN
        pass_check = False
        logger.warning("Can't upgrade %s from %s to %s because the following packages would be broken: %s",
                       main_pkg_ver.name, main_pkg_ver.installed_version, main_pkg_ver.version,
                       _format_pending_pkgs(brokens.values()))
    if deletes_after:
        # After fix, get a list of package names are marked to be deleted that are broken before so that we can know
        # if there is any package that the only way to fix the broken pkg is to remove the pkg -> fail
        brokens_to_be_deleted = [deletes_after[pkg_name] for pkg_name in brokens_before if pkg_name in deletes_after]
        if brokens_to_be_deleted:
            pass_check = False
            logger.warning("Can't upgrade %s from %s to %s because the following broken packages would be deleted: %s",
                           main_pkg_ver.name, main_pkg_ver.installed_version, main_pkg_ver.version,
                           _format_pending_pkgs(brokens_to_be_deleted))
            # Treat DELETE_BROKEN as solvable problems
            for pkg in brokens_to_be_deleted:
                problems[pkg.name] = Change(pkg, problem=ProblemType.DELETE_BROKEN)
    return pass_check



def _can_be_installed_or_upgraded(pkg, patch_snapshot=None, override_list=None, auto_inst=True):
    """
    Check whether package can be installed or not
    :param pkg: apt package to be checked whether it can be installed/upgraded or not
    :param patch_snapshot: patch snapshot which contains the baseline details
    :param override_list: install override list which contains a list of approved patches
    :param auto_inst: automatically install new packages or not
    :return: True if package can be installed/upgraded, otherwise False
    """
    if not auto_inst and pkg.marked_install:
        # This is corresponding to ProblemType.NO_AUTO_INSTALL
        return False
    pkg_data = generate_package_data(
        (pkg.name, pkg.architecture(), None, pkg.candidate.version, None), APT_CODES)

    if override_list is not None:
        # Check if pkg is in the override list by comparing the id_filters
        # and double check the pkg versions by matching all filers in the override list
        # For example,  if we want to install/upgrade package A to version x
        # but the override list contains package A with version y then we don't allow install/upgrade
        if match_package(override_list.id_filters, pkg_data) and \
                not match_package(override_list.all_filters, pkg_data):
            # This is corresponding to ProblemType.VERSION_CONFLICT
            return False
    else:
        # For rejected patches, only when matched, fail the check
        # TODO: check if we have other versions approved by baseline?
        if patch_snapshot and patch_snapshot.has_rejected_patches and patch_snapshot.block_rejected_patches \
                and match_package(patch_snapshot.rejected_patches, pkg_data):
            # This is corresponding to ProblemType.BLOCKED_REJECTED
            return False
    return True


def _check_pending_installs_and_upgrades(main_pkg_ver, installs_and_upgrades,
                                         patch_snapshot=None, override_list=None, auto_inst=True):
    """
    Check pending installations and upgrades match the baseline or override list
    :param main_pkg_ver: the main package version triggered the pending changes
    :param installs_and_upgrades: a list of package to be installed or upgraded
    :param patch_snapshot: patch snapshot which contains the baseline details
    :param override_list: install override list which contains a list of approved patches
    :param auto_inst: automatically install new packages or not
    :return: True if pass the check, otherwise False
    """
    failed_check_pkgs = []
    for pkg in installs_and_upgrades:
        if pkg.name != main_pkg_ver.name and \
                not _can_be_installed_or_upgraded(pkg, patch_snapshot, override_list, auto_inst):
            failed_check_pkgs.append(pkg)

    if failed_check_pkgs:
        logger.warning("Can't upgrade %s from %s to %s because the following packages can't be installed or upgraded: %s",
                       main_pkg_ver.name, main_pkg_ver.installed_version, main_pkg_ver.version,
                       _format_pending_pkgs(failed_check_pkgs))
        return False
    return True


def _check_pending_deletes(problems, main_pkg_ver, deletes=None):
    """
    Check pending deletes. Fail if exists pending deletes are not auto-removable or not auto-installed
    :param problems: a map of solvable problems in the format of pkg_name:Change
    :param main_pkg_ver: the main package version triggered the pending changes
    :param deletes: a list of pkgs that are pending to be deleted to upgrade targeted main pkg version
    :return: True if pass the check, otherwise False
    """
    if deletes:
        # If exists deleting not auto removable pkg or not auto installed, fail check
        failed_check_pkgs = [ pkg for pkg in deletes if not pkg.is_auto_removable or not pkg.is_auto_installed ]
        if failed_check_pkgs:
            logger.warning(
                "Can't upgrade %s from %s to %s because the following packages would be deleted: %s",
                main_pkg_ver.name, main_pkg_ver.installed_version, main_pkg_ver.version,
                _format_pending_pkgs(failed_check_pkgs))
            # Treat DELETE as solvable problems, especially for reverse dependencies
            for pkg in failed_check_pkgs:
                problems[pkg.name] = Change(pkg, problem=ProblemType.DELETE)
            return False
    return True


def check_pending_changes(main_pkg_ver, changes_before_fix=None, changes_after_fix=None,
                          patch_snapshot=None, override_list=None, auto_inst=True, check_deletes=True):
    """
    Check whether the pending changes match the baseline or override list
    :param main_pkg_ver: the main package version triggered the pending changes
    :param changes_before_fix: all changes (in a map where the package name is the key and pkg object is the value)
     before fixing broken packages, including installs/upgrades/deletes/brokens
    :param changes_after_fix: all changes after fixing broken packages, including installs/upgrades/deletes/brokens
    :param patch_snapshot: patch snapshot which contains the baseline details
    :param override_list: install override list which contains a list of approved patches
    :param auto_inst: automatically install new packages or not
    :param check_deletes: boolean indicates whether checking pending deletes or not
    :return: A tuple of (pass_check, solvable_problems), where pass_check indicates whether the pending changes
    pass the check or not and solvable_problems contains a map of pkg_name:Change
    NOTE: right now, we only treat problem type with DELETE_BROKEN to be solvable, all others are unsolvable
    TODO: add other problem types to the solvable_problems map once we add corresponding logic
    """
    pass_check = True
    problems = {}

    if changes_before_fix:
        (installs_before, upgrades_before, deletes_before, brokens_before) = changes_before_fix
        deletes_after, brokens_after = None, None

        # a list of package objects for both installs and upgrades before fix
        installs_and_upgrades = list(installs_before.values()) + list(upgrades_before.values())
        if changes_after_fix:
            (installs_after, upgrades_after, deletes_after, brokens_after) = changes_after_fix
            installs_and_upgrades = list(installs_after.values()) + list(upgrades_after.values())

        if not _check_broken_packages(problems, main_pkg_ver, brokens_before, brokens_after, deletes_after):
            pass_check = False

        if not _check_pending_installs_and_upgrades(main_pkg_ver, installs_and_upgrades,
                                                    patch_snapshot, override_list, auto_inst):
            pass_check = False

        if check_deletes:
            deletes = deletes_before if deletes_after is None else deletes_after
            if not _check_pending_deletes(problems, main_pkg_ver, list(deletes.values())):
                pass_check = False

    return pass_check, problems
