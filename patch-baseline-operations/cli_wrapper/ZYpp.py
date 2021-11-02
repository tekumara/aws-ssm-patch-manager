# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import logging
import sys
from datetime import datetime
from patch_zypp_cli import zypp_shared_operation_methods as shared
from cli_wrapper.cli_package_bean import CLIPackageBean
from patch_common.constant_repository import ExitCodes
from patch_common.metrics_service import append_runtime_metric_file_info
import copy

logger = logging.getLogger()

class ZYpp:
    """
    This class is the interface for interacting with the wrapper library. Instead of making cli calls directly from the
    application using the cli_wrapper, this interface should be used. All logic for creating relationships, etc... is stored here.
    For example 'get_all_installed_packages()' will get all installed packages with all of their versions and possible classification and severity combos.
    different CLI calls.
    """
    def __init__(self, cli):
        """
        Initialization for the ZYpp library interface.
        :param cli - zypper cli used to make calls. This is passed in for testing and mocking purposes.
        """
        self.cli = cli

    def commit(self, list_of_packages):
        """
        Method for commiting a list of packages.
        :param list_of_packages is a list of packages to pass in as CLIPackageBeans.
        :returns a tuple of (subprocess_result_text, subprocess_exit_code).
        """
        if len(list_of_packages) == 0:
            return (None, 0)

        try:
            package_names = []
            for package in list_of_packages:
                package_names.append("{}.{}={}".format(package.name, package.arch, package.available_edition))
            logger.info("Committing packages...")
            result = self.cli.commit().execute(package_names)
            return result
        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while commit packages. %s", e)
            return(None, -1)

    def get_all_locks(self):
        """
        Method for getting all locks as CLILocks.
        :return List<CLILock>
        """
        logger.info("Getting all locks.")
        locks = self.cli.zypper_locks().execute()[0]
        logger.info("Found %s locks."%(str(len(locks))))
        return locks

    def refresh(self):
        """
        Method for refreshing Zypper repositories. Per the Zypp man pages, this means downloading metadata of packages.
        Any failures to connect to repositories surface here.
        """
        try:
            repos = self.cli.zypper_list_repos().execute()[0]
            for repo in repos:
                if repo.enabled == True:
                    refresh = self.cli.zypper_refresh().execute(items_to_append=['-r', repo.name.strip()])
                    if refresh[1] != 0:
                        logger.error("Unable to refresh Zypp repository. Command output: {}".format(refresh[0]))
                        logger.info("Please check permissions and connection to zypper repositories.")
                        append_runtime_metric_file_info("Unable to refresh Zypp repository. Command output: {}".format(refresh[0]))
                        sys.exit(ExitCodes.FAILURE)
        except Exception as e:
            logger.info("Unable to refresh zypp repository. Please check permissions and connection of repositories.")
            logger.exception(e)
            sys.exit(ExitCodes.FAILURE)

    def add_locks(self, package_names):
        """
        Method for locking packages using zypper built in lock functionality.
        :param package_names is a list of package names to lock
        """
        logger.info("Locking %s packages."%(len(package_names)))
        return self.cli.zypper_addlock().execute(package_names)

    def remove_locks(self, package_names):
        """
        Method for UNlocking packages using zypper built in lock functionality.
        :param package_names is a list of package names to unlock.
        """
        logger.info("Unlocking packages.")
        result = self.cli.zypper_removelock().execute(package_names)
        logger.info("Finished removing locks.")
        return result

    def get_all_uninstalled_packages(self):
        """
        Method for getting a list of all packages available in the repo's that are currently not installed.
        These are for not applicable packages only so we need very limited information about them.
        Otherwise the defaults will work.
        :return List<CLISOLVABLES> of all packages in repos that are not installed.
        """
        # Get packages as CLISolvable objects.
        logger.info("Getting all UNinstalled packages.")
        package_solvables = self.cli.zypper_se_type_package_uninstalled_only().execute()[0]
        logger.info("Found %s packages in repo that are not installed.", len(package_solvables))

        return package_solvables

    def get_all_installed_packages(self):
        """
        Method for getting all packages of the BaseCLIBean form with all available information and defaults on them.
        :returns - (name, arch) => [CLIPackageBean, ClIPackageBean] of all available versions of a package with different classifications and severities.
        """
        # Get all installed packages (whether or not they're on a patch) as CLIPackageBeans.
        na2pkgs_installed = \
            shared.convert_na2pkg_list_to_hash_list(self.__get_all_installed_repo_packages())

        # Get all available package versions in the repo whether installed or NOT.
        na2pkgs_versions = \
            shared.convert_na2pkg_list_to_hash_list(self.__get_all_package_versions())

        # If the version is greater than the current version, transform it to a CLIPackageBean and add it to the hash list.
        na2pkgs_with_all_versions = \
            self.__add_all_versions_to_hash_list(na2pkgs_installed, na2pkgs_versions)

        # Get all CLIPatchConflicts from patches.
        na2_patch_conflicts = \
            shared.convert_na2pkg_list_to_hash_list(self.__get_all_patch_packages())

        # Assign each CLIPackageBean version that matches a conflict the conflicts classification, severity and release time.
        # If a version matches more than one conflicts, make a copy of it for the new classification and severity and add it to the list.
        na2_all_packages = self.__assign_classification_severity_from_patches_to_packages(na2pkgs_with_all_versions, na2_patch_conflicts)

        # return the list of edvery available version, classification and severity combination.
        return na2_all_packages

    def __assign_classification_severity_from_patches_to_packages(self, na2_all_package_versions, na2_patch_conflicts):
        """
        Method for assigning all classifications and severities from patches to matching packages.
        :param na2_all_package_versions is a dict (name, arch) => [CLIPackageBean] of all package versions found (both the installed one and the ones that are available)
        :param na2_patch_conflicts is a dict of (name, arch) => [CLIPatchConflict] of all the package conflicts found on a patch.
        """
        try:
            logger.info("Assigning classification and severity from %s patch conflicts to %s packages"%(str(len(na2_patch_conflicts)),str(len(na2_all_package_versions))))
            # For every conflict (name, arch)
            for na in na2_patch_conflicts:
                # if it is an installed package we're reporting on.
                if na in na2_all_package_versions:
                    na2_all_package_versions[na] = self.__assign_list_of_conflict_attributes_to_list_of_versions(na2_all_package_versions[na], na2_patch_conflicts[na])
            return na2_all_package_versions
        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while assigning classification's and severities from patches to packages. %s", e)

    def __assign_list_of_conflict_attributes_to_list_of_versions(self, package_versions, patch_conflicts):
        """
        Method for assigning all relevant patch conflict classifications, severities and release times to all matching package_versions.
        :param package_versions is a list [CLIPackageBean, ...] with the same (name, arch) but different versions.
        :param patch_conflicts is a list [CLIPatchConflict, ...] with the same (name, arch) and same OR different versions.
        :returns a List of [CLIPackageBean, ...] with packages representing all combos of the classifications and severities included.
        """
        versions_with_conflicts = []
        try:
            for version in package_versions:
                packages_to_add = []
                for conflict in patch_conflicts:
                    # if the versions match.
                    if version.compare_version(conflict.edition) == 0:
                        # Check to see if the package version has already been assigned a classification and severity.
                        # assign the existing package instance the classification and severity.
                        new_package = copy.deepcopy(version)
                        if not version.classification or version.classification == "":
                            new_package.classification = conflict.classification
                        if not version.severity or version.severity == "":
                            new_package.severity = conflict.severity
                        new_package.bugzilla_ids = conflict.bugzilla_ids
                        new_package.cve_ids = conflict.cve_ids
                        new_package.release_time = shared.parse_release_time_from_patch_conflict(conflict)
                        packages_to_add.append(new_package)

                # add the classification and severity combos to the list of packages for this name,arch.
                if len(packages_to_add) > 0:
                    versions_with_conflicts.extend(packages_to_add)
                else:
                    versions_with_conflicts.append(version)

            return versions_with_conflicts

        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while assigning classifications and severities to different package versions of installed packages. %s", e)

    def __add_all_versions_to_hash_list(self, na2pkgs_installed, na2pkgs_versions):
        """
        Method for taking a (name, arch) => [package_list] of CLIPackageBeans and adding to the list
        every available package version.
        :param na2pkgs_installed is a dict => list of (name, arch) => [CLIPackageBeanA, CLIPackageBeanB, etc...]
        :param na2pkgs_versions => (name, arch) => [CLISolvableA, CLISolvableB, etc...]
        :returns (name, arch) => [CLIPackageBeanA, CLIPackageBeanB, CLIPackageBeanC(from CLISolvableA), etc...]
        with all sovlables added.
        """
        try:
            # Loop through every install ed package (name, arch)
            for na in na2pkgs_installed:
                # get the currently installed version
                current_version = na2pkgs_installed[na][0]
                # if there are other potential versions (not installed) available
                if na in na2pkgs_versions:
                    # for each of those potential other versions
                    for other_version in na2pkgs_versions[na]:
                        # if they are newer than the currently installed version
                        if current_version.compare_version(other_version.available_edition) == -1:

                            # Convert them to a CLIPackageBean
                            new_package = self.__create_new_package_from_solvable(other_version, current_version)
                            # Add them to the list of current / available versions.
                            if new_package:
                                na2pkgs_installed[na].append(new_package)

            return na2pkgs_installed

        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while trying to add new package versions to the list of known versions. %s", e)


    def __create_new_package_from_solvable(self, solvable, current_edition):
        """
        Method for creating a new CLIPackageBean from a CLISolvable.
        :param solvable is a CLISolvable of type 'package' to convert to a Package Bean.
        :param current_edition is the currently installed edition of the package.
        """
        try:
            new_package = copy.copy(current_edition)
            new_package.available_edition = solvable.available_edition
            return new_package
        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while creating a new CLIPackageBean from a CLISolvable. %s", e)

    def __get_all_package_versions(self):
        """
        Method returns all packages with all versions represented as separate CLISolvable types.
        :For example:
        <solvable status="not-installed" name="zypper-docker" kind="package" edition="2.0.0-15.3.2" arch="x86_64" repository="SLE-Module-Containers12-Updates"/>
        <solvable status="not-installed" name="zypper-docker" kind="package" edition="1.2.0-14.1" arch="x86_64" repository="SLE-Module-Containers12-Updates"/>
        <solvable status="not-installed" name="zypper-docker" kind="package" edition="1.1.2-11.1" arch="x86_64" repository="SLE-Module-Containers12-Updates"/>
        <solvable status="not-installed" name="zypper-docker" kind="package" edition="1.1.1-8.1" arch="x86_64" repository="SLE-Module-Containers12-Updates"/>
        zypper-docker will have 4 different CLISolvables in the list.
        :returns: List<CLISolvable>
        """
        try:
            logger.info("Getting all versions for all packages in repository...")
            result = self.cli.zypper_search_type_package().execute()
            return result[0]
        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while getting all available packages versions. %s", e)

    def __get_all_installed_repo_packages(self):
        """
        Method for getting all installed packages available in the repository.
        :return a list of CLIPackageBean objects.
        """
        try:
            # Get packages as CLISolvable objects.
            logger.info("Getting all installed packages.")
            package_solvables = self.cli.zypper_se_type_package_installed_only().execute()[0]
            logger.info("Found %s packages.", len(package_solvables))

            # Take names from Solvables and get packageinfo.
            cli_packages = self.__get_package_info_as_cli_packages(package_solvables)
            logger.info("Converted %s package solvables to %s objects from package info command.", len(package_solvables), len(cli_packages))

            return cli_packages

        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while getting all installed repo packages %s",e)

    def __get_package_info_as_cli_packages(self, packages):
        """
        Method for running 'zypper info --type package' on a list of packages and getting additional info such as
        installed versions and time.
        :param packages is a list of CLISolvables (or any object containing a .name attribute that can be used)
        :returns List<CLIPackageBean> objects with timestamp, installed, available and current edition filled in.
        """
        try:

            final = []
            for package in packages:
                final.append(CLIPackageBean(
                    name = package.name,
                    arch = package.arch,
                    current_edition = self.__grab_last_line(self.cli.rpm_q_qf_version().execute([package.name]))[0],
                    installed_time = self.__grab_last_line(self.cli.rpm_q_qf_installedtime().execute([package.name]))[0],
                    update_available = False, # in the context of this package there is NOT an update available.
                    available_edition = "", # In the context of this package there is not an availabled edition.
                    installed= True
                ))
            return final
        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while getting package info, current edition and installed time for CLISolvable. %s", e)

    def __get_patch_conflicts(self, patches):
        """
        Method for geting all of the patch conflicts from patches.
        :param patches: list of patches
        :return: list of [CLIPatchConflict] from patches
        """
        try:
            packages = []
            for patch in patches:
                if patch.conflicts:
                    packages.extend(patch.conflicts)
            return packages
        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while getting all patch conflicts from patches. %s", e)

    def __get_all_patch_packages(self):
        """
        Method for getting all INSTALLED packages on the machine that were a part of a patch. In Zypper, the only
        packages with classification and severity are packages that were found on a patch.
        :return a list of CLIPackageBean objects with all package information filled out (installed, availabled edition,
        current edition, installed date, etc...)
        """
        try:
            # Get list of patches
            logger.info("Getting all patches.")
            patches = self.cli.zypper_se_type_patch().execute()[0]
            logger.info("Found %s patch solvables.", len(patches))

            # Extract all of the patch names.
            patch_names = [patch.name for patch in patches]

            # Get list of cli_patch_objects with associated packages from 'zypper info --type patch <patch_name>' for each patch.
            logger.info("Calling 'zypper info --type patch <patch_name>'")
            cli_patch_objects = self.cli.zypper_info_type_patch().execute(patch_names)[0]
            logger.info("Found info on %s patches of the %s patch solvables.", len(cli_patch_objects), len(patch_names))

            # Add Patch Issue data to cli patch objects
            logger.info("Getting CVE data for patches")
            name_to_issue_map = self.cli.zypper_list_patch_issues().execute()[0]
            self.__add_issue_data_to_patch(name_to_issue_map, cli_patch_objects)

            # Get list of PatchConflicts from patches (PatchConflict is a package with just basic info)
            packages = self.__get_patch_conflicts(cli_patch_objects)
            logger.info("Found %s packages from the patches.", len(packages))

            return  packages

        except Exception as e:
            logger.exception("Caught exception in ZYpp interface while getting all patch packages. %s", e)

    def __add_issue_data_to_patch(self, name_to_issue_map, cli_patch_objects):
        """
        Method for setting applicable bugzilla id and cve id data to Patch conflicts
        :param patch_issue_data: list of CLIPatchIssues objects
        :param cli_patch_objects: list of CLIPatchBean objects
        """
        # Add CVE Ids and Bugzilla Ids to each Patch Conflict
        for patch in cli_patch_objects:
            if patch.name in name_to_issue_map:
                bugzilla_ids = name_to_issue_map[patch.name].bugzilla_ids
                cve_ids = name_to_issue_map[patch.name].cve_ids
                for patch_conflict in patch.conflicts:
                    patch_conflict.bugzilla_ids.update(bugzilla_ids)
                    patch_conflict.cve_ids.update(cve_ids)

    def __grab_last_line(self, response):
        """
        Method for returning the last line from a string. Some responses might return multiple lines
        where we only want the last. For example, rpm -q --qf "%{VERSION}-%{RELEASE}\n" where more than one version is
        installed.
        :param response is the tuple returned form the .execute() call of form (string_response, return_code)
        """
        if response and response[0]:
            lines = response[0].splitlines()
            return (lines[len(lines)-1], response[1])
        else:
            return response
