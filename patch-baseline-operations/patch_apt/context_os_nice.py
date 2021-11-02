# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from contextlib import contextmanager
import os
import errno


@contextmanager
def os_nice():
    old_priority = os.nice(0)
    try:
        # Check that we will be able to restore the priority by trying to nice down.
        os.nice(-1)
        # It is confirmed that we can restore the priority (niced down). Now nice up.
        os.nice(20)
    except OSError as e:
        if e.errno in (errno.EPERM, errno.EACCES): # Operation not permitted. We can continue with default priority.
            pass
        else:
            raise
    yield
    # stop being nice
    os.nice(old_priority - os.nice(0))
