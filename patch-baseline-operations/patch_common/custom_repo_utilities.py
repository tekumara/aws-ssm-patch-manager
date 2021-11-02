import logging
import os
import shutil

from patch_common import instance_info

REPO_SUFFIX = ".repo"

logger = logging.getLogger()

# initialize sources destinations
RETRY_ATTEMPTS = 3

# Quickest way to determine if custom repo creation / destruction caused exception
# All rollback and retries of custom repos are handled in this module
# so other modules need a way to know if an exception was by this module.
CUSTOM_REPOS_FAILED = False


# TODO Add UT


class OperatingSystemSettings:
    """
    Where repositories should be placed for the package manager and a directory to use for backups
    As way of an example, default values are for Yum on Amazon Linux
    """

    def __init__(self):
        pass

    temp_repo_destination = "/var/log/amazon/ssm/yum-configuration/repos.d/"
    repo_source = "/etc/yum.repos.d/"
    cache_cleanup = lambda: os.system("yum clean")
    snapshot_id = "b4c3e27a-9ac4-4eca-b0b0-8628d4f7aca3"


class RepoConfigurator:
    def __init__(self, os_settings, baseline):
        """
        :param os_settings: knows where files should be put
        :type os_settings: OperatingSystemSettings
        :param baseline: contains the sources, if any
        :type baseline: patch_common.baseline.Baseline
        """
        self._baseline = baseline
        self._os_settings = os_settings
        self._repos_backed_up = False
        self._temp_directory = os.path.join(os_settings.temp_repo_destination, os_settings.snapshot_id)

    def setup_custom_repos(self):
        """
        Backs up existing configuration files into the requested temporary directory and put in the sources from the
        baseline
        """
        if self._baseline.sources and len(self._baseline.sources) > 0:
            try:
                logger.info("Setting up custom repos.")

                if not self._has_sources():
                    logger.error("Baseline did not have any repositories for this Product (%s)", instance_info.product)
                    raise Exception("No sources contained the product: %s. "
                                    + "Add the product to a source to use the custom repository configuration"
                                    % instance_info.product)

                _retry_wrapper(self._create_temp_repo_directory)

                # Backup and remove original .repo files
                _rollback_wrapper(self._restore_repos, self._backup_repos)
                self._repos_backed_up = True

                # Attempt to create the custom repo's. If it fails execute the two methods provided to:
                # 1) Clean up any custom repo files that WERE created.
                # 2) Move the default .repo files back to their original directory.
                _rollback_wrapper(self.cleanup_custom_repos, self._create_custom_repos)

                self._os_settings.cache_cleanup()
            except:
                CUSTOM_REPOS_FAILED = True
                raise

    def _backup_repos(self):
        """
        Move the original repo files into the backup location
        :return:
        """
        self._move_repo_files(
            self._os_settings.repo_source,
            self._temp_directory)

    def _restore_repos(self):
        """
        Restore repo files from the backup location
        """
        self._move_repo_files(
            self._temp_directory,
            self._os_settings.repo_source)

    def _has_sources(self):
        for source in self._baseline.sources:
            for product in source["products"]:
                if instance_info.product == product or product == "*":
                    return True

    def cleanup_custom_repos(self):
        """
        Cleaning up the custom repo files created, restores the original ones.
        """
        # best to skip if sources were not backed up, either due to failure, or no sources
        if self._repos_backed_up:
            logger.info("Cleaning up custom repos.")
            try:
                _retry_wrapper(lambda: self._cleanup_directory(self._os_settings.repo_source))

                # Attempt to cleanup the custom repo's.
                _retry_wrapper(
                    lambda: self._move_repo_files(
                        self._temp_directory, self._os_settings.repo_source)
                )
                self._os_settings.cache_cleanup()
            except:
                CUSTOM_REPOS_FAILED = True
                raise

    def _cleanup_directory(self, directory):
        """
        Method for cleaning up .repo files from the provided directory
        :param directory: location of the .repo files to clean up.
        :type directory: str
        """
        # if the directory exists, then clean it up.
        if os.path.isdir(directory):
            logger.info("Cleaning up directory %s", directory)
            path = os.path.abspath(directory)
            full_path = None
            sources = os.listdir(directory)
            for file in sources:
                if file.endswith(REPO_SUFFIX):
                    logger.info("Removing file: %s from %s", file, directory)
                    full_path = os.path.join(path, file)
                    os.remove(full_path)
        else:
            logger.error("Directory %s does not exist.", directory)

    def _create_temp_repo_directory(self):
        """
        Method for checking the existence of the temp repo location and creating it if it doesn't exist.
        """
        destination = self._temp_directory
        if not os.path.exists(destination):
            logger.info("Creating temp repo destination directory at %s", destination)
            os.makedirs(destination)
        else:
            logger.info("Temp repo destination directory %s already exists.", destination)

    def _move_repo_files(self, source, destination):
        """
        Method for moving repo files from one location to another.
        :param source: directory to move files from.
        :type source: str
        :param destination: directory to move files to
        :type destination: str
        """
        sources = os.listdir(source)
        logger.info("Moving .repo files from %s to %s", source, destination)

        for file in sources:
            if file.endswith(".repo"):
                logger.info("Moving file: %s", file)
                shutil.move(os.path.join(source, file), destination)

    def _create_custom_repos(self):
        """
        Method for creating actual custom .repo files and saving them to the required repository
        from the provided configuration in the snapshot.
        """
        for source in self._baseline.sources:
            # filter on product
            for product in source["products"]:
                if instance_info.product == product or product == "*":
                    logger.info("Creating custom repo %s", source["name"])
                    repo_file = os.path.join(self._os_settings.repo_source, source["name"] + ".repo")
                    with open(repo_file, "w+") as f:
                        f.write(source["configuration"])


def _retry_wrapper(retryable):
    """
    Method wrapper handles retries of methods
    :param retryable: method to retry
    """
    for x in range(0, RETRY_ATTEMPTS):
        logger.info("Executing %s with args", retryable.__name__)
        try:
            retryable()
        except:
            if x == RETRY_ATTEMPTS - 1:
                logger.error("All retries failed, raising Exception.")
                raise
            else:
                logger.error("Execution failed, attempting retry.")


def _rollback_wrapper(rollback_method, retryable):
    """
    Method wrapper handles rollbacks of methods based on predefined rollback steps passed in.
    :param rollback_method: in case of exception
    :param retryable: method to retry
    """
    func_name = retryable.__name__
    logger.info("Executing lambda %s" % func_name)
    try:
        retryable()
    except:
        try:
            logger.error("Execution failed. Attempting rollback of %s", func_name)
            rollback_method()
        except:
            logger.error("Rollback of method %s failed.", func_name)
            raise
        raise
