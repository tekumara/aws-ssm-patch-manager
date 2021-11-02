# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common.package_inventory import PackageInventory
from patch_common import rpm_version
from patch_dnf.dnf import DNF
from patch_dnf.dnf_baseline import DnfBaseline
import logging

logger = logging.getLogger()


def generate_report(dnf, baseline, operation_type, override_list=None):
    """
    Method that handles scanning for, reporting on, and analyzing DNF packages.
    :param baseline: Baseline Object
    :baseline is the provided baseline (of the Baseline class).
    :param operation_type can be either "scan" or "install".
    :param override_list a list of rules to override installation decisions.
    :returns a PackageInventory object with the appropriate variables instantiated.
    """

    # Get list of installed packages
    all_installed_dnf_packages = dnf.get_all_installed_na_packages_dict()
    # Need to evaluate baseline rules using metadata
    missing, cpa_failed, installed, installed_rejected, installed_other, not_applicable = _report_updates(
        dnf, baseline, all_installed_dnf_packages, override_list)

    # Sort results
    missing.sort(key=lambda x: x.taxonomy)
    cpa_failed.sort(key=lambda x: x.taxonomy)
    installed.sort(key=lambda x: x.taxonomy)
    installed_rejected.sort(key=lambda x: x.taxonomy)
    installed_other.sort(key=lambda x: x.taxonomy)
    not_applicable.sort(key=lambda x: x.taxonomy)

    logger.info(
        "Installed count: %i, Installed Other count: %i, Failed count: %i, Not Applicable count: %i, Missing count: %i, Installed Rejected count: %i",
        len(installed), len(installed_other), len(cpa_failed), len(not_applicable), len(missing), len(installed_rejected)
    )

    return PackageInventory(operation_type=operation_type,
                            pkg_type="dnf",
                            installed_pkgs=installed,
                            installed_other_pkgs=installed_other,
                            installed_rejected_pkgs=installed_rejected,
                            missing_pkgs=missing,
                            not_applicable_pkgs=not_applicable,
                            failed_pkgs=cpa_failed,
                            override_list=override_list)


def _report_updates(dnf, baseline, installed_na_packages, override_list):
    """
    :param dnf: DNF object
    :param baseline: Baseline object
    :param installed_na_packages: Dict mapping (package_name, arch) => DnfPackage object
    :param override_list: list of packages in the Install Override List
    :return: Lists returning installed, installed_rejected, installed_other, not_applicable, missing package lists
    """

    package_na_to_report = {}
    override_list_na_to_report = {}
    package_cves_to_report = {}

    enabled_modules = dnf.get_all_enabled_modules()

    all_available_updates = dnf.get_all_available_updates()
    all_available_updates_dict = {update.taxonomy: update for update in all_available_updates}
    # Get packages to report from metadata
    updates_available_from_metadata = dnf.get_all_available_updates_with_metadata()
    _add_packages_to_report_dicts(updates_available_from_metadata, dnf, baseline, installed_na_packages, override_list,
                                 package_na_to_report, override_list_na_to_report, enabled_modules, package_cves_to_report, all_available_updates_dict)

    # Get packages to report without metadata
    updates_available_without_metadata = _remove_packages_with_metadata(dnf, all_available_updates)
    _add_packages_to_report_dicts(updates_available_without_metadata, dnf, baseline, installed_na_packages, override_list,
                                 package_na_to_report, override_list_na_to_report, enabled_modules, None, None)

    # Add all other installed packages to report, these will be reported as installed_other or installed_rejected
    _add_installed_packages_to_report(installed_na_packages, package_na_to_report, override_list_na_to_report, baseline)

    # combine packages that match baseline with packages in override list
    package_na_to_report = _combine_baseline_packages_and_override_list(package_na_to_report, override_list_na_to_report)

    # Add installation times to packages which are installed
    dnf.set_installation_time_for_packages(package_na_to_report)

    missing, cpa_failed, installed, installed_rejected, installed_other, not_applicable = baseline.categorize_override_list_install(package_na_to_report)

    _update_missing_package_with_cves(missing,package_cves_to_report)

    return missing, cpa_failed, installed, installed_rejected, installed_other, not_applicable


def _add_packages_to_report_dicts(available_updates, dnf, baseline, installed_na_packages, override_list,
                                 package_na_to_report, override_list_na_to_report, enabled_modules,
                                 package_cves_to_report, all_available_updates_dict):
    """
    Method to go through available updates and update appropriate dictionary if they match the baseline or
    install override list and have some version installed
    :param available_updates: list of DnfPackage objects
    :param dnf: DNF object
    :param baseline: DnfBaseline object
    :param installed_na_packages: (Name, Arch) => DnfPackage dictionary for packages which are installed
    :param override_list: OverrideList object
    :param package_na_to_report: (Name, Arch) => DnfPackage dictionary for packages which match baseline
    :param override_list_na_to_report: (Name, Arch) => DnfPackage dictionary for packages which match Install Override List
    :param enabled_modules: (module_name) => list of enabled module_version
    :param package_cves_to_report: Dict of (name, arch) => CVE Set
    :param all_available_updates_dict: Dict of all_available_updates
    """
    for package_update in available_updates:
        package_update.assign_match_override_list(override_list)
        package_update.assign_match_baseline(baseline)
        package_update.assign_installed(installed_na_packages)

        #Remove updates FROM the metadata that aren't available from the package manager.
        if all_available_updates_dict is not None and package_update.taxonomy not in all_available_updates_dict:
            continue

        # If the candidate update is older than what is already installed, ignore the update
        if package_update.current_edition is not None and \
                rpm_version.compare(package_update.available_edition, package_update.current_edition) < 0:
            continue

        # If the candidate update is a part of a module stream which is not enabled, ignore the update
        if not package_update.is_enabled_by_module_stream(enabled_modules):
            continue

        if package_update.matches_install_override_list and package_update.installed:
            _update_dict_with_most_recent_package(override_list_na_to_report, baseline, package_update)
        elif package_update.matches_baseline:
            if package_update.installed and package_update.update_available and \
                    _package_has_rejected_dependencies(dnf, baseline, package_update):
                # Package is an update to installed package, but has rejected dependencies so don't add to report
                continue
            _update_dict_with_most_recent_package(package_na_to_report, baseline, package_update)
            _check_packages_for_cves(package_update, package_cves_to_report)


def _remove_packages_with_metadata(dnf, all_available_updates):
    """
    Remove all updates from updates_available_without_metadata for which we have metadata on
    :param dnf: DNF
    :param all_available_updates: list of DnfPackage representing all available updates
    :return: deduped list of updates_without_metadata
    """
    all_available_updates_dict = {update.taxonomy: update for update in all_available_updates}
    updates_with_metadata = dnf.get_all_available_updates_with_metadata()
    for update in updates_with_metadata:
        if update.taxonomy in all_available_updates_dict:
            del all_available_updates_dict[update.taxonomy]

    return all_available_updates_dict.values()


def _combine_baseline_packages_and_override_list(package_na_to_report, override_list_na_to_report):
    """
    Combine packages from provided dictionaries into single dictionary
    :param package_na_to_report: (name, arch) => DnfPackage
    :param override_list_na_to_report: (name, arch) => DnfPackage
    :return: single dictionary with (name, arch) => DnfPackage
    """
    combined_packages_to_report = {}
    for na in package_na_to_report:
        combined_packages_to_report[na] = [ package_na_to_report[na] ]
    for na in override_list_na_to_report:
        if na not in combined_packages_to_report:
            combined_packages_to_report[na] = [ override_list_na_to_report[na] ]
        else:
            combined_packages_to_report[na].append(override_list_na_to_report[na])
    return combined_packages_to_report


def _add_installed_packages_to_report(installed_na_packages, package_na_to_report, override_list_na_to_report, baseline):
    """
    Add all installed packages that haven't been found already to report list
    :param installed_na_packages: installed (Name, Arch) => DnfPackage
    :param package_na_to_report: packages to report (Name, Arch) => DnfPackage
    :param override_list_na_to_report: install override list (Name, Arch) => DnfPackage
    """
    for na in installed_na_packages:
        if na not in override_list_na_to_report:
            # Add to package list if installed is a higher version than current
            _update_dict_with_most_recent_package(package_na_to_report, baseline, installed_na_packages[na])


def _update_dict_with_most_recent_package(na_package_dict, baseline, package):
    """
    Update version and compliance of package if package version >= current version in the dictionary
    :param na_package_dict: Dict of (name, arch) => package
    :param baseline: Baseline Object
    :param package: DnfPackage Object
    """
    if (package.name, package.arch) not in na_package_dict:
        na_package_dict[(package.name, package.arch)] = package

    package_in_dict = na_package_dict[(package.name, package.arch)]
    baseline.assign_compliance(package)
    if package_in_dict is None or package_in_dict.compare_version(package.latest_edition) < 0:
        na_package_dict[(package.name, package.arch)] = package
    elif package_in_dict.compare_version(package.latest_edition) == 0:
        # Update compliance level if higher than previous
        package_in_dict.compliance = package.compliance


def _package_has_rejected_dependencies(dnf, baseline, package):
    """
    Determine if package has a dependency that is explicitly rejected
    :param dnf: DNF object
    :param baseline: Baseline object
    :param package: DnfPackage object
    :return: True if package has rejected dependency, False otherwise
    """
    # Check if any dependencies are rejected and if we should block rejected patches as dependencies
    if baseline.has_rejected_patches and baseline.block_rejected_patches:
        package_dependencies = dnf.get_all_dependencies_for_package(package)
        for package_dependency in package_dependencies:
            if package_dependency.taxonomy_matches_pattern(baseline.exclude):
                logger.warn("Package {0} has a blocked dependency {1}".format(package.taxonomy, package_dependency.taxonomy))
                return True
    return False


def _check_packages_for_cves(package_update, cve_dict):
    """
    Checks if package has an available update and contains CVEs
    :param package_update: DnfPackage object
    :param cve_dict: Dict of (name, arch) => CVE Set
    """
    if package_update.cve_ids and \
            package_update.installed and package_update.update_available:
        _update_cve_dict_with_most_recent_package(cve_dict, package_update)


def _update_cve_dict_with_most_recent_package(cve_package_dict, package):
    """
    Adds or updates CVEs that are related to a given package
    :param cve_package_dict: Dict of (name, arch) => CVE Set
    :param package: DnfPackage Object
    """
    cve_set = cve_package_dict.get((package.name, package.arch), set())
    cve_ids = package.cve_ids
    _update_cve_set(cve_set, cve_ids)
    cve_package_dict[(package.name, package.arch)] = cve_set


def _update_cve_set(cve_set, cve_ids):
    for cve in cve_ids:
        cve_set.add(cve)


def _update_missing_package_with_cves(missing_packages, package_cves_to_report):
    """
    Update missing packages with CVEs it remediates
    :param missing: list of missing DnfPackage objects
    :param package_cves_to_report: Dict of (name, arch) => CVE Set
    """
    for package in missing_packages:
        if (package.name, package.arch) in package_cves_to_report:
            package.all_known_cves_for_update = list(package_cves_to_report[(package.name, package.arch)])
