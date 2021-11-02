# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import datetime
import logging

from patch_common.constant_repository import ExitCodes
from patch_common.metrics_service import append_runtime_metric_file_info

class PatchBaselineOperations:
    """
    Class to handle the run patch baseline request.
    """
    def __init__(self, custom_repositories, apt_operations):
        """
        Constructor of the PatchBaselineOperations class.
        :param custom_repositories: to create/restore custom repositories.
        :param apt_operations: to execute patching operations.
        """
        self.custom_repositories = custom_repositories
        self.apt_operations = apt_operations


    def run_patch_baseline(self, patch_snapshot):
        """
        Runs the patch baseline for the patch snapshot.
        :param patch_snapshot: to run the patch baseline.
        :return: exit code of the SSM run command.
        """
        start_time = datetime.datetime.utcnow()

        # Setup a custom repository if specified.
        configuration = patch_snapshot.get_custom_repository_configuration()
        if configuration is not None:
            self.custom_repositories.setup_custom_repository(configuration)
            # Only calling clean and not refresh because the patching operation calls update.
            self.apt_operations.clean_retrieved_packages()

        # Execute apt operation on snapshot
        apt_result, package_inventory = self.apt_operations.execute_patch_operation(patch_snapshot)

        # Upload the results of the patching operation to inventory.
        # package inventory can be None if anything went wrong with the patching operation.
        inventory_success = False
        if package_inventory:
            try:
                end_time = datetime.datetime.utcnow()

                inventory_success = True
            except Exception:
                logging.exception("Unable to upload report to SSM inventory.")

        # Restore the default repositories
        # Capturing the success of the custom repository restore to fail the command if needed.
        custom_repository_restore_success = False
        try:
            if configuration is not None:
                logging.info("Custom repository was used. Restoring the default repositories.")
                self.custom_repositories.restore_default_repositories()
                logging.info("Cleaning the APT cache.")
                self.apt_operations.refresh_cache()
            custom_repository_restore_success = True
        except Exception:
            logging.exception("Unable to restore the default repositories.")
            logging.error("To manually restore the default repositories, move the files located in the directory: %s",
                          self.custom_repositories.default_repo_temp_directory)

        exit_code = self._transform_exit_code(apt_result,
                                              inventory_success,
                                              custom_repository_restore_success)

        logging.info("Patching operation completed. Exit code: %s", exit_code)

        return exit_code, package_inventory

    @staticmethod
    def _transform_exit_code(exit_code, inventory_success, custom_repository_restore_success):
        """
        Transforms the exit code to account for inventory success/failure.
        :param exit_code: to transform.
        :param inventory_success: of uploading the report to SSM inventory.
        :return: the transformed exit code.
        """
        if exit_code == ExitCodes.REBOOT and \
                (not inventory_success or not custom_repository_restore_success):
            logging.error("Patching operation was success but post operation failed. " +
                          "Rebooting instance and exiting with failure.")
            append_runtime_metric_file_info("Patching operation was success but post operation failed. " +
                          "Rebooting instance and exiting with failure.")
            return ExitCodes.REBOOT_WITH_FAILURES
        elif exit_code == ExitCodes.SUCCESS and \
                (not inventory_success or not custom_repository_restore_success):
            logging.error("Patching operation was success but post operation failed. " +
                          "Exiting with failure.")
            append_runtime_metric_file_info("Patching operation was success but post operation failed. " +
                          "Exiting with failure.")
            return ExitCodes.FAILURE
        else:
            return exit_code
