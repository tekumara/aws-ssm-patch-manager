# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
"""
Methods for creating and managing the native yum object.
"""
import logging
import time
import yum

logger = logging.getLogger()

class YyoomBase(yum.YumBase):

    def _askForGPGKeyImport(self, po, userid, hexkeyid):
        """Tell yum to import GPG keys if needed
            Instead of disabling checking signatures altogether, we just let
            yyoom import GPG keys if it needs, same way as yum -y does.
        """
        return True


def setup_yum_base(baseline):
    """
    Initilizes the yum object.

    :param baseline: yum baseline from us 
    :return: yum base from yum
    """
    yb = YyoomBase()
    yb.setCacheDir()
    acquire_lock(yb)
    yb.conf.exclude = baseline.exclude
    yb.pkgSack

    return yb


def acquire_lock(yb):
    """
    Aquires the lock on the RPM database

    :param yb: yum base from yum 
    :return: None
    """
    retry_count = 100

    # delay in seconds
    delay = 1
    # exponential backoff ratio
    ratio = 1.2
    # max_delay
    delay_max = 5
    while True:
        retry_count = retry_count - 1
        try:
            yb.doLock()
            break
        except yum.Errors.LockError, e:
            if retry_count <= 0:
                raise e
            else:
                logger.info("another process has acquired yum lock, waiting %d s and retry.", delay)
                time.sleep(delay)
                if delay * ratio > delay_max:
                    delay = delay_max
                else:
                    delay = delay * ratio


def release_lock(yb):
    """
    Release the lock on the RPM database.

    :param yb: yum base from yum 
    :return: 
    """
    yb.closeRpmDB()
    yb.doUnlock()
