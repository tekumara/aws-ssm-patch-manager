#!/usr/bin/env python

import sys

sys.path.insert(1, "./")
sys.path.insert(1, "./botocore/vendored")

import logging
import os
import shutil

from patch_common.metrics_service import append_runtime_metric_traceback
from patch_zypp_cli import zypp_main_cli
from patch_zypp_cli.zypp_baseline import ZyppBaseline
from patch_common.constant_repository import ExitCodes
from patch_common.custom_repo_utilities import OperatingSystemSettings
from patch_common.custom_repo_utilities import RepoConfigurator
from cli_wrapper.zypper_cli import ZypperCLI
from cli_wrapper.ZYpp import ZYpp


# initialize logging
LOGGER_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOGGER_DATEFORMAT = "%m/%d/%Y %X"
LOGGER_LEVEL = logging.INFO
LOGGER_STREAM = sys.stdout

logging.basicConfig(format=LOGGER_FORMAT, datefmt=LOGGER_DATEFORMAT, level=LOGGER_LEVEL, stream=LOGGER_STREAM)
logger = logging.getLogger()


def execute(snapshot, override_list=None):
    """
    Entrance method for the zypp patch baseline package.

    REQUIRED: execute() is the required method for os specific execution entrance points. (ie, common calls execute())

    :param snapshot: representing the json snapshot
    :type snapshot: patch_common.snapshot.Snapshot
    :param debug: whether or not to run in debug mode, which is an optional way to setup logging.
    :return: (exit_code, inventory)
              exit_code = the exit code returned from the package (may be different if inventory report upload fails.
              inventory = PackageInventory object (found in patch_common) for the inventory report upload. May be None,
                        but inventory report upload will fail, altering the exit code and failing the overall operation
                        (though updating will have still have succeeded).
    """

    settings = OperatingSystemSettings()
    settings.temp_repo_destination = "/var/log/amazon/ssm/zypp-configuration/repos.d/"
    settings.repo_source = "/etc/zypp/repos.d/"
    settings.cache_cleanup = lambda: os.system("zypper clean")
    settings.snapshot_id = snapshot.snapshot_id
    configurator = RepoConfigurator(settings, snapshot.patch_baseline)

    try:
        inventory = None
        # self destruct this main script and actual logic
        os.remove(os.path.abspath(sys.argv[0]))
        shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "patch_zypp_cli"))

        # Create the repo
        configurator.setup_custom_repos()

        baseline = ZyppBaseline(snapshot.patch_baseline_dict)


        zb = ZYpp(ZypperCLI())
        (exit_code, inventory) = zypp_main_cli.zypp_main(zb, baseline, snapshot.operation, override_list)

        configurator.cleanup_custom_repos()

        return exit_code, inventory

    except Exception as e:
        logger.exception("An exception occurred, exiting.")
        configurator.cleanup_custom_repos()
        append_runtime_metric_traceback()
        return ExitCodes.FAILURE, inventory
