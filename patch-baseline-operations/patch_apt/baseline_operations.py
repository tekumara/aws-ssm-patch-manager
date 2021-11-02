# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

def apply_patch_baseline(packages, patch_snapshot):
    """
    Apply patch baseline to all packages to get missing/installed/installed_other/not_applicable pkgs
    :param packages: a list of all packages
    :param patch_snapshot: patch snapshot object which contains patch baseline attributes
    :return: few lists of packages in different patch states
    """
    installed_packages = []
    installed_other_packages = []
    installed_rejected_packages = []
    missing_packages = []
    not_applicable_packages = []

    for pkg in packages:
        is_matched, has_upgrades = pkg.match_baseline(patch_snapshot)
        if is_matched:
            if pkg.is_installed:
                if has_upgrades:
                    # Match baseline, installed and upgradable pkgs -> Missing
                    missing_packages.append(pkg)
                else:
                    # Match baseline, installed but not upgradable pkg -> Installed
                    installed_packages.append(pkg)
            else:
                # Match baseline but not installed pkg -> NotApplicable
                not_applicable_packages.append(pkg)
        else:
            # Not match baseline but installed pkgs -> InstalledRejected or InstalledOther
            if pkg.is_installed:
                if pkg.is_installed_rejected(patch_snapshot):
                    installed_rejected_packages.append(pkg)
                else:
                    installed_other_packages.append(pkg)

    return installed_packages, installed_other_packages, installed_rejected_packages, missing_packages, not_applicable_packages


def apply_override_list(packages, override_list=None):
    """
    This method needs to be run after apply_patch_baseline if exists override list
    so that it will override filtered versions and upgradable versions

    :param packages: a list of all packages
    :param override_list: InstallOverideList object form patch common pkg
    :return: a list matched packages
    """
    if override_list is not None:
        return [ pkg for pkg in packages if pkg.match_override_list(override_list) == (True, True) ]


def upgradables_sanity_check(upgradable_packages, patch_snapshot, override_list=None):
    """
    Sanity check for upgradable pkgs with the override list and rejected patches from the baseline

    :param upgradable_packages: upgradable packages
    :param cache: apt cache to help with the sanity check
    :param patch_snapshot: patch snapshot which contains the rejected patches
    :param override_list: override list
    :return: a list of pass-check pkgs and a list of fail-check pkgs
    """
    pass_check_pkgs = []
    fail_check_pkgs = []
    for pkg in upgradable_packages:
        if pkg.adjust_candidate(upgradable_packages, patch_snapshot, override_list):
            pass_check_pkgs.append(pkg)
        else:
            fail_check_pkgs.append(pkg)
    return pass_check_pkgs, fail_check_pkgs


def find_final_missing_pkgs(missing_packages, failed_packages):
    """
    Find out the final missing packages for install operation after installation
    :param missing_packages: missing packages according to baseline
    :param failed_packages: failed packages after installation
    :return: a list of missing packages
    """
    missing_pkgs_map = _build_packages_map(missing_packages)
    failed_pkgs_map = _build_packages_map(failed_packages)

    still_missing_pkgs = []
    for pkg_name in missing_pkgs_map:
        if pkg_name not in failed_pkgs_map:
            still_missing_pkgs.append(missing_pkgs_map[pkg_name])
        else:
            if missing_pkgs_map[pkg_name].compare_version(failed_pkgs_map[pkg_name]) > 0:
                still_missing_pkgs.append(missing_pkgs_map[pkg_name])
    return still_missing_pkgs


def _build_packages_map(packages):
    """
    Build a map of pkgs where pkg full name is the key and the Package object is the value
    :param packages: a list packages to be mapped
    :return: pkgs map
    """
    return { pkg.fullname: pkg for pkg in packages }
