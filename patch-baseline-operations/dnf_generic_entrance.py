# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys

sys.path.insert(1, "./")
sys.path.insert(1, "./botocore/vendored")

import logging
import os
import shutil

from patch_common.baseline import Baseline
from patch_common.constant_repository import ExitCodes
from patch_common.custom_repo_utilities import OperatingSystemSettings
from patch_common.custom_repo_utilities import RepoConfigurator
from patch_dnf import dnf_main
from patch_dnf.dnf import DNF
from patch_dnf.dnf_baseline import DnfBaseline
from patch_common.metrics_service import append_runtime_metric_traceback



# initialize logging
LOGGER_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOGGER_DATEFORMAT = "%m/%d/%Y %X"
LOGGER_LEVEL = logging.INFO
LOGGER_STREAM = sys.stdout

logging.basicConfig(format=LOGGER_FORMAT, datefmt=LOGGER_DATEFORMAT, level=LOGGER_LEVEL, stream=LOGGER_STREAM)
logger = logging.getLogger()


def execute(snapshot, override_list=None):
    """
    Entrance method for the dnf patch baseline package. This file will be run by the common package which will run it
    based on the operating system found in the snapshot and the name of the script.

    REQUIRED: execute() is the required method for os specific execution entrance points. (ie, common calls execute())

    :param snapshot: representing the json snapshot
    :type snapshot: patch_common.snapshot.Snapshot
    :param override_list: a list of patches to override installation decisions
    :param debug: whether or not to run in debug mode, which is an optional way to setup logging.
    :return: (exit_code, inventory)
              exit_code = the exit code returned from the package (may be different if inventory report upload fails.
              inventory = PackageInventory object (found in patch_common) for the inventory report upload. May be None,
                        but inventory report upload will fail, altering the exit code and failing the overall operation
                        (though updating will have still have succeeded).
    """

    settings = OperatingSystemSettings()
    settings.temp_repo_destination = "/var/log/amazon/ssm/dnf-configuration/repos.d/"
    settings.repo_source = "/etc/yum.repos.d/"
    settings.cache_cleanup = lambda: os.system("dnf clean all")
    settings.snapshot_id = snapshot.snapshot_id
    configurator = RepoConfigurator(settings, snapshot.patch_baseline)
    dnf = DNF()

    try:
        inventory = None

        # TODO @lawleh - 02.19.20 - self destruct this main script and actual logic
        # os.remove(os.path.abspath(sys.argv[0]))
        # shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "patch_dnf"))
        baseline = DnfBaseline(snapshot.patch_baseline_dict)
        # configurator.setup_custom_repos() will only affect repos in yum.repos.d
        # Since dnf supports defining repos in dnf.conf we will disable all repos before adding custom sources
        if baseline.sources and len(baseline.sources) > 0:
            dnf.disable_enabled_repos()

        # Add custom sources to yum.repos.d directory
        configurator.setup_custom_repos()

        # Refresh metadata cache to ensure repository information is up to date
        dnf.refresh_repository_cache()

        (exit_code, inventory) = dnf_main.dnf_main(baseline, snapshot.operation, override_list)

        return exit_code, inventory

    except Exception as e:
        logger.exception("An exception occurred, exiting.")
        append_runtime_metric_traceback()
        return ExitCodes.FAILURE, inventory
    finally:
        # re-enable disabled repos
        configurator.cleanup_custom_repos()
        dnf.enable_disabled_repos()
