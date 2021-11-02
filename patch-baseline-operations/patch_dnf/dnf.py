# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import re
from patch_dnf.dnf_cli import DnfCLI
from patch_dnf.updateinfo_xml_parser import generate_packages_with_metadata
from patch_dnf.dnf_package import DnfPackage
from patch_common.cli_invoker import CLIInvokerException
import logging


class DNF:
    """
    Class for representing the DNF package manager.
    """
    RPM_DATE_FORMATS = ["%a %d %b %Y %I:%M:%S %p %Z", "%a %b %d %H:%M:%S %Y"]

    def __init__(self):
        self.dnfCli = DnfCLI()
        self.disabled_repos = []
        self.logger = logging.getLogger()

    def refresh_repository_cache(self):
        """
        Method for refreshing the repository cache to make sure we have up to date repository information
        """
        self.dnfCli.clean_all().execute()
        self.dnfCli.make_cache().execute()

    def get_all_installed_na_packages_dict(self):
        """
        Method for getting all installed DNF packages.
        :returns a dictionary mapping the tuple (name, arch) to a DNF Package object
        """
        installed_packages = self.dnfCli.list_installed().execute()[0].strip().split("\n")

        # Matches `name.arch    version-release   repository`
        # Ex: `NetworkManager.x86_64         1:1.22.8-5.el8_2        @rhel-8-baseos-rhui-rpms`
        output_regex = r"(\S*)[\.](\S*)(\s*)(\S*)[\-](\S*)(\s*)(\S*)"

        installed = {}
        start_index = _get_start_index_of_regex(installed_packages, output_regex)
        if start_index in range(0, len(installed_packages)):
            for raw_package_string in installed_packages[start_index:]:
                if raw_package_string and len(raw_package_string.split()) >= 2:
                    installed_package = DnfPackage.from_raw_dnf_string(raw_package_string, package_is_installed=True)
                    installed[(installed_package.name, installed_package.arch)] = installed_package

        return installed

    def get_all_available_updates(self):
        """
        Method for getting all DNF packages with updates.
        :returns a DnfPackage list of all DNF packages with upgrades
        """
        packages_with_updates = self.dnfCli.list_upgrades().execute()[0].strip().split("\n")

        upgradeable_packages = []

        # Matches `name.arch    version-release   repository`
        # Ex: `CUnit.i686           2.1.3-17.el8           rhel-8-appstream-rhui-rpms`
        output_regex = r"(\S*)[\.](\S*)(\s*)(\S*)[\-](\S*)(\s*)(\S*)"

        start_index = _get_start_index_of_regex(packages_with_updates, output_regex)
        if start_index in range(0, len(packages_with_updates)):
            for raw_package_string in packages_with_updates[start_index:]:
                if raw_package_string and len(raw_package_string.split()) >= 2:
                    dnf_package = DnfPackage.from_raw_dnf_string(raw_package_string, package_is_installed=False)
                    upgradeable_packages.append(dnf_package)

        return upgradeable_packages

    def get_all_enabled_modules(self):
        """
        Method for getting all Module streams that are enabled
        :return: dict of module_name => list of enabled module versions
        """
        raw_enabled_modules = self.dnfCli.list_enabled_modules().execute()[0].strip().split("\n")

        modules = {}
        # header from this CLI call not localized, can rely on header
        i = _get_index_after_header(raw_enabled_modules, "Name")
        while i in range(0, len(raw_enabled_modules)):
            # python36    3.6 [d][e]   build, common [d]    Python programming language, version 3.6
            raw_module = raw_enabled_modules[i].split()
            if len(raw_module) == 0:
                # Blank line indicates end of repositories streams. Check if another repository has more streams listed.
                i = _get_index_after_header(raw_enabled_modules, "Name", starting_index=i)
            else:
                i += 1
                module_name = raw_module[0]
                module_version = raw_module[1]
                if module_name in modules:
                    modules[module_name].append(module_version)
                else:
                    modules[module_name] = [module_version]

        return modules

    def set_installation_time_for_packages(self, package_na_dict):
        """
        Method for retrieving the installation time for all given packages
        Sets the corresponding field for all package objects
        :param installed_packages: list of DNFPackage objects which are installed
        """

        # RPM commands do not sync with metadata and do not contain any headers in cli output
        raw_installation_times = self.dnfCli.list_installation_times().execute()[0].strip().split("\n")
        installed_time_dict = {}
        for raw_installed_time in raw_installation_times:
            self.logger.debug("Raw Installed Time: %s", raw_installed_time)
            # Ex: python3-configobj-5.0.6-11.el8.noarch 1587618855
            raw_output_list = raw_installed_time.split()
            self.logger.debug("Raw Output List Length: %i", len(raw_output_list))
            if len(raw_output_list) == 2:
                package_taxonomy = raw_output_list[0]  # python3-configobj-5.0.6-11.el8.noarch
                installed_time_string = raw_output_list[1]  # 1587618855
                installed_time_dict[package_taxonomy] = installed_time_string
                self.logger.debug("Adding package to dict: %s", package_taxonomy)

        for package_na in package_na_dict:
            for package in package_na_dict[package_na]:
                # If package is the exact version installed
                if package.installed and package.latest_edition == package.current_edition:
                    # rpm command does not output epoch of installed packages
                    taxonomy_without_epoch = \
                        "{}-{}-{}.{}".format(package.name, package.version, package.release, package.arch)
                    if taxonomy_without_epoch in installed_time_dict:
                        package.installed_time = installed_time_dict[taxonomy_without_epoch]
                    else:
                        self.logger.warn("Unable to retrieve installation time for package: %s", taxonomy_without_epoch)

    def get_all_available_updates_with_metadata(self):
        """
        Method for getting all DNF packages with updates through updateinfo XML file along with all important information.
        :returns a DnfPackage list of all installed DNF packages with upgrades.
        """
        return generate_packages_with_metadata()

    def get_all_dependencies_for_package(self, package):
        """
        Method for retrieving all dependencies of a particular package
        :param package: DNFPackage Object
        :return: a DnfPackage list of all dependencies of the given package
        """

        package_dependencies = self.dnfCli.get_dependencies_for(package.taxonomy).execute()[0].strip().split("\n")
        dnf_package_dependencies = []

        # Repoquery does not have header in the cli that is always present.
        # However, all valid lines should NOT contain any spaces
        for dependency in package_dependencies:
            if " " not in dependency:
                dnf_package_dependencies.append(DnfPackage(
                    taxonomy=dependency,
                    name="",
                    arch="",
                    epoch="",
                    version="",
                    release=""
                ))

        return dnf_package_dependencies

    def install_packages(self, pkgs_to_install, debug_logs_enabled=False):
        """
        Method to install qualified installable patches
        :param pkgs_to_install: List of packages in naevr string format
        :param debug_logs_enabled: Boolean to determine if debug logs should be printed
        """
        for package in pkgs_to_install:
            try:
                install_output = self.dnfCli.install_packages(package.taxonomy).execute()[0].strip().split("\n")
                if debug_logs_enabled:
                    for line in install_output:
                        print(line)
            except CLIInvokerException as e:
                self.logger.warn("Failed to install package: {}".format(package.taxonomy))

    def disable_enabled_repos(self):
        """
        Method that disables enabled repositories
        """
        enabled_repos = self.dnfCli.get_repositories("--enabled").execute()[0].strip().split("\n")[0:]

        index_after_header = _get_index_after_header(enabled_repos, "repo id")
        if index_after_header < 0:
            # Even when cache is cleared and repos are changed, there is no expected additional output in this command.
            # list should always start at index 1
            index_after_header = 1
        if index_after_header in range(0, len(enabled_repos)):
            for repo_name in enabled_repos[index_after_header:]:
                repo_name = repo_name.split(" ")[0]
                self.logger.warn("Disabling repo '{}' from /etc/dnf/dnf.conf file".format(repo_name))
                self.disabled_repos.append(repo_name)
                self.dnfCli.disable_repository(repo_name).execute()

    def enable_disabled_repos(self):
        """
        Method that enables repos that were disabled in self.disable_enabled_repos
        """
        while self.disabled_repos:
            repo_name = self.disabled_repos.pop(0)
            self.logger.info("Enabling disabled repo '{}'".format(repo_name))
            self.dnfCli.enable_repository(repo_name).execute()


def _get_start_index_of_regex(cli_output, regex, starting_index=0):
    pattern = re.compile(regex)
    for i in range(starting_index, len(cli_output)):
        line = cli_output[i].strip()
        matches = pattern.match(line)
        if matches:
            return i

    return -1


def _get_index_after_header(cli_output, header, starting_index=0):
    for i in range(starting_index, len(cli_output)):
        if header in cli_output[i]:
            return i + 1
    return -1