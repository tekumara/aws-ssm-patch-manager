#!/usr/bin/python3

# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import boto3
import json
import logging
import os
import signal
import sys

from patch_apt import argument_parser
from patch_apt.apt_operations import AptOperations
from patch_apt.custom_repositories import CustomRepositories
from patch_apt.patch_baseline_operations import PatchBaselineOperations
from patch_apt.patch_snapshot import PatchSnapshot

LOG_DIRECTORY = "/var/log/amazon/ssm/"
LOG_FILE = "apply_patch_baseline_apt.log"


def main(patch_snapshot):
    """
    Orchestrates the patching.
    :param options: containing the patching snapshot.
    :return: the exit code of the complete patching operation.
    """

    logging.info("Starting APT patching operation.")

    logging.info("Loading patch snapshot from %s", patch_snapshot)

    # Create dependencies.
    apt_operations = AptOperations()
    custom_repositories = CustomRepositories(patch_snapshot.snapshot_id)
    patch_baseline_operations = PatchBaselineOperations(custom_repositories, apt_operations)

    return patch_baseline_operations.run_patch_baseline(patch_snapshot)
