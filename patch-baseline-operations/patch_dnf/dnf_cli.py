# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_common.cli_invoker import CLIInvoker

class DnfCLI:
    """
    Class for representing the DNF cli.
    """
    def list_upgrades(self):
        """
        Method for getting a list of installed packages that have updates available via the `dnf list upgrades` command.
        :return - CLIInvoker - ("response string", return_code)
        """
        return CLIInvoker(comd = ['dnf', '--showduplicates', 'list', 'available'])

    def list_installed(self):
        """
        Method for getting a list of installed packages from DNF via the `dnf list installed` command.
        :return - CLIInvoker - ("response string", return_code)
        """
        return CLIInvoker(comd = ['dnf', 'list', 'installed'])

    def list_enabled_modules(self):
        """
        Method for getting a list of enabled modules from DNF via the `dnf module list --enabled` command.
        :return: - CLIInvoker - ("response string", return_code)
        """
        return CLIInvoker(comd = ['dnf', 'module', 'list', '--enabled'])

    def list_installation_times(self):
        """
        Method get getting a list of installed packages with their installation time
        :return: CLIInvoker - ("response string", return_code)
        """
        return CLIInvoker(comd = ['rpm', '-qa', '--queryformat', '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH} %{INSTALLTIME}\n'])

    def install_packages(self, package):
        """
        Installs a specific packages. It is the equivalent of `dnf install`
        This command takes a list of package names to install. For example,
        e.g. install_packages('python2-2.7.16-12.module+el8.1.0+4148+33a50073.x86_64').execute()
        :return - CLIInvoker - ("response string", return_code)
        """
        return CLIInvoker(comd = ['dnf', 'install', '-y', package])

    def get_dependencies_for(self, package):
        """
        Method for getting a list of all dependencies of a particular package
        :param package: Full description of package name-version-arch.
            Ex: python2-2.7.16-12.module+el8.1.0+4148+33a50073.x86_64
        :return: A list of packages that are dependencies for the supplied package
        """
        return CLIInvoker(comd = ['dnf', 'repoquery', '--recursive', '--requires', '--resolve', package])

    def get_repositories(self, status):
        """
        Method for getting repositories depending on provided status
        :param status: '--all' or '--enabled' or '--disabled'
        :return CLIInvoker object
        """
        return CLIInvoker(comd = ['dnf', 'repolist', status])

    def enable_repository(self, repo_name):
        """
        Method for enabling disabled repositories
        :param repo_name
        :return: CLIInvoker object
        """
        return CLIInvoker(comd = ['dnf', 'config-manager', '--set-enabled', repo_name])

    def disable_repository(self, repo_name):
        """
        Method for disabling enabled repositories
        :param repo_name
        :return: CLIInvoker object
        """
        return CLIInvoker(comd = ['dnf', 'config-manager', '--set-disabled', repo_name])

    def clean_all(self):
        """
        Method for clearing all repository cache information
        :return: CLIInvoker object
        """
        return CLIInvoker(comd = ['dnf', 'clean', 'all'])

    def make_cache(self):
        """
        Method for refreshing the repository cache
        :return: CLIInvoker object
        """
        return CLIInvoker(comd = ['dnf', 'makecache'])