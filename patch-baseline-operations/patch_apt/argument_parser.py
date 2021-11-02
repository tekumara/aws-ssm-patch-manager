# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import argparse


def parse_args():
    parser = argparse.ArgumentParser(description="Patch this instance using a pre-configured patch baseline.")
    parser.add_argument("-d", "--debug",
                        action="store_true", default=False,
                        help="Print debug messages to stdout")
    parser.add_argument("--snapshot-json",
                        action="store",
                        help="Path to json containing snapshot information.")
    parser.add_argument("--reboot-option",
                        action="store",
                        help="Parameter to specify reboot behavior")
    return parser.parse_args()
