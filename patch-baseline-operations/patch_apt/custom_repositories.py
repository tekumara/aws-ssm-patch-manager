# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import os
from patch_apt import file_utilities

APT_REPO_BASE_DIRECTORY = "/etc/apt"
APT_REPO_SOURCES_LIST_FILE_NAME = "sources.list"
APT_REPO_SOURCES_LIST_FILE_PATH = os.path.join(APT_REPO_BASE_DIRECTORY, APT_REPO_SOURCES_LIST_FILE_NAME)
APT_REPO_SOURCES_LIST_DIRECTORY_NAME = "sources.list.d"
APT_REPO_SOURCES_DIRECTORY = os.path.join(APT_REPO_BASE_DIRECTORY, APT_REPO_SOURCES_LIST_DIRECTORY_NAME)

logger = logging.getLogger()


class CustomRepositories:
    def __init__(self, snapshot_id):
        """
        Constructor for custom repositories
        :param snapshot_id: of the patching operation. Used for the temp location of the file.
        """

        self.default_repo_temp_directory = os.path.join("/var/log/amazon/ssm/apt-configuration", snapshot_id)
        self._default_repo_temp_sources_list_file_path = os.path.join(self.default_repo_temp_directory,
                                                                      APT_REPO_SOURCES_LIST_FILE_NAME)
        self._default_repo_temp_sources_directory = os.path.join(self.default_repo_temp_directory,
                                                                 APT_REPO_SOURCES_LIST_DIRECTORY_NAME)

    def setup_custom_repository(self, configuration):
        """
        Sets up the custom repository for the patching operation.
        1. Moves the sources.list and sources.list.d files to a temporary location.
        2. Creates the custom repository configuration as the sources.list file.
        :param configuration: of the custom repository.
        :return: None
        """
        try:
            self._store_sources_list_repositories()
        except Exception as e:
            logger.error("Failed to move sources list.")
            logger.error(e)
            raise

        try:
            self._store_sources_list_directory_repositories()
        except Exception as e:
            logger.error("Failed to move sources list directory.")
            logger.error(e)
            # Attempt to restore the directory repositories as a single file may have failed to move.
            self._restore_defaults_from_temp()
            raise

        try:
            self._create_custom_repository(configuration)
        except Exception as e:
            logger.error("Failed to create custom repository configuration.")
            logger.error(e)
            self._restore_defaults_from_temp()
            raise

    def restore_default_repositories(self):
        """
        Restores the default repositories.
        1. Removes the custom repository configuration.
        2. Restores the default sources.list and sources.list.d files to /etc/apt/
        :return: None
        """

        # Exceptions from these are logged in patch baseline operations
        self._remove_custom_repository()
        self._restore_defaults_from_temp()

    def _restore_defaults_from_temp(self):
        """
        Restores the default repositories from the temp folder and removes the temp folder.
        :return: None
        """
        self._restore_sources_list_repository()
        self._restore_sources_list_directory_repositories()
        file_utilities.remove_directory(self._default_repo_temp_sources_directory)
        file_utilities.remove_directory(self.default_repo_temp_directory)

    def _store_sources_list_repositories(self):
        """
        Stores the sources.list file in the temporary location.
        :return: None
        """
        logger.info("Storing the %s file to a temporary location %s",
                    APT_REPO_SOURCES_LIST_FILE_NAME, self.default_repo_temp_directory)
        logger.info("Creating a temporary directory for the default repositories: %s",
                    self.default_repo_temp_directory)
        file_utilities.create_directory(self.default_repo_temp_directory)

        logger.info("Moving %s to the temporary location %s",
                    APT_REPO_SOURCES_LIST_FILE_PATH, self.default_repo_temp_directory)
        file_utilities.move_file_path(APT_REPO_SOURCES_LIST_FILE_PATH, self._default_repo_temp_sources_list_file_path)

    def _store_sources_list_directory_repositories(self):
        """
        Stores the files in the sources.list.d directory in a temporary location.
        :return: None
        """
        logger.info("Storing the %s directory to a temporary location %s",
                    APT_REPO_SOURCES_LIST_DIRECTORY_NAME, self._default_repo_temp_sources_directory)
        logger.info("Creating a temporary directory directory: %s",
                    self._default_repo_temp_sources_directory)
        file_utilities.create_directory(self._default_repo_temp_sources_directory)

        logger.info("Moving sources directory default repository files from %s to %s",
                    APT_REPO_SOURCES_DIRECTORY, self._default_repo_temp_sources_directory)
        file_utilities.move_files_in_directory(APT_REPO_SOURCES_DIRECTORY, self._default_repo_temp_sources_directory)

    def _restore_sources_list_repository(self):
        """
        Restores the default sources.list file to /etc/apt/
        :return: None
        """
        logger.info("Restoring the %s file.", APT_REPO_SOURCES_LIST_FILE_NAME)
        logger.info("Moving the %s file from %s to %s",
                    APT_REPO_SOURCES_LIST_FILE_NAME,
                    self._default_repo_temp_sources_list_file_path,
                    APT_REPO_SOURCES_LIST_FILE_PATH)
        file_utilities.move_file_path(self._default_repo_temp_sources_list_file_path, APT_REPO_SOURCES_LIST_FILE_PATH)

    def _restore_sources_list_directory_repositories(self):
        """
        Restores the sources.list.d directory to /etc/apt/
        :return: None
        """
        logger.info("Restoring the %s directory", APT_REPO_SOURCES_LIST_DIRECTORY_NAME)
        logger.info("Moving default repositories from %s to %s",
                    self.default_repo_temp_directory, APT_REPO_SOURCES_DIRECTORY)
        file_utilities.move_files_in_directory(self._default_repo_temp_sources_directory, APT_REPO_SOURCES_DIRECTORY)

    @staticmethod
    def _create_custom_repository(configuration):
        """
        Creates the custom repository file as sources.list in /etc/apt/
        :param configuration: of the custom repository
        :return: None
        """
        logger.info("Adding custom repository configurations at %s",
                    APT_REPO_SOURCES_LIST_FILE_PATH)
        file_utilities.write_to_file(APT_REPO_SOURCES_LIST_FILE_PATH, configuration)

    @staticmethod
    def _remove_custom_repository():
        """
        Removes the custom repository file (sources.list) from /etc/apt/.
        :return: None
        """
        logger.info("Removing custom repository configuration file: %s",
                    APT_REPO_SOURCES_LIST_FILE_PATH)
        file_utilities.remove_file(APT_REPO_SOURCES_LIST_FILE_PATH)
