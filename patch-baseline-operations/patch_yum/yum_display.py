# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import yum.rpmtrans

logger = logging.getLogger()


class YumDisplayCallBack(yum.rpmtrans.RPMBaseCallback):
    def __init__(self):
        yum.rpmtrans.RPMBaseCallback.__init__(self)
        self.ts_current = -1

    def event(self, package, action, te_current, te_total, ts_current, ts_total):
        """
        @param package: A yum package object or simple string of a package name
        @param action: A yum.constant transaction set state or in the obscure 
                       rpm repackage case it could be the string 'repackaging'
        @param te_current: Current number of bytes processed in the transaction
                           element being processed
        @param te_total: Total number of bytes in the transaction element being
                         processed
        @param ts_current: number of processes completed in whole transaction
        @param ts_total: total number of processes in the transaction.
        """
        if self.ts_current != ts_current:
            logger.info("%s: %s Started [%s/%s]",
                        self.action[action], package, ts_current, ts_total)
            self.ts_current = ts_current

        if te_current == te_total:
            logger.info("%s: %s Finished [%s/%s]",
                        self.action[action], package, ts_current, ts_total)

    def scriptout(self, package, msgs):
        if msgs:
            print msgs,

    def verify_txmbr(self, base, txmbr, count):
        " Callback for post transaction when we are in verifyTransaction(). "
        logger.info("Verify: %u/%u: %s", count, len(base.tsInfo), txmbr)
