#!/usr/bin/python3

# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import os
import signal
import sys

# This is to accommodate the the directory structure used by PatchBaselineOperationsLinux
# when it packages this script and the patch_apt module using the pubrelease target.
# TODO: Find a way to avoid modifying sys.path here
sys.path.insert(1, './')
sys.path.insert(1, '../src')

# for Python 3.8 the default sys.path doesn't contains apt module.
# Check if the python version is 3.8 or higher then add the 
# module path to sys.path
if sys.version_info[0] == 3 and sys.version_info[1] == 8 \
        and "/usr/lib/python3/dist-packages" not in sys.path:
            if os.path.isdir("/usr/lib/python3/dist-packages"):
                sys.path.append("/usr/lib/python3/dist-packages")

from patch_apt.main import main
from patch_apt.patch_snapshot import PatchSnapshot


def execute(snapshot, override_list=None):

    if os.getuid() != 0:
        print("You need to be root to run this application")
        sys.exit(1)

    # ensure that we are not killed when the terminal goes away,
    # useful if the ssh connection to an instance dies
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    # Transform the Common package PatchSnapshot Object to APT snapshot object
    # then run the main code
    exit_code, inventory = main(PatchSnapshot(snapshot))
    return exit_code, inventory

