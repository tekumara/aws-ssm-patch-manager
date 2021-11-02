# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import ast
import re

regex = r'\{(.*?)\}'
logger = logging.getLogger()

class BootTimeParser():
    """
    Parser for parsing the result of the sysctl kern.boottime command. Example of response being parsed:
        "kern.boottime: { sec = 1606256448, usec = 851279 } Tue Nov 24 22:20:48 2020" as string
    """
    def parse(self, response):
        """
        Method for parsing output of kern.boottime command.
        :param - response is the string output from sysctl kern.boottime is the clock time when system booted.
        :return - float that represents time of last reboot since linux epoch in seconds
        """
        try:
            # response should be "{ sec = 1606256448, usec = 851279 } Tue Nov 24 22:20:48 2020" 
            result = re.search(regex, response)
            # group 0 should be: "{ sec = 1606256448, usec = 851279 }"
            pre_dict = result.group(0)
            boottime_in_sec = ast.literal_eval(pre_dict\
                .replace("=", ":")\
                .replace(" sec ", " \"sec\" ")\
                .replace(" usec ", " \"usec\" "))["sec"]

            # this is in sec since linux epoch
            return float(boottime_in_sec)
        except IndexError as index_error: 
            logger.exception(index_error)
            raise Exception("Expected kern.boottime response %s failed parsing. Failing command."%(response))
        except Exception as e:
            logger.exception(e)
            raise Exception("Failed to parse resepone of kern.boottime command: %s"%(response))

    