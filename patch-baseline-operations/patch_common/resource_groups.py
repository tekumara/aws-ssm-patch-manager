from patch_common.exceptions import PatchManagerError
from patch_common import retryable_client
from botocore.exceptions import ClientError
from patch_common.constant_repository import ExitCodes
import re

class ResourceGroupsClient():

    def __init__(self, instance_id, region, logger):
        """
        Constructor
        :param - instance_id is the instance_id of the current instance.
        :param - region is the region the current instance is in.
        :param - logger is the logging.getLogger() object for printing to the logs.
        """
        self.logger = logger
        self.region = region
        self.instance_id = instance_id
        self.client = retryable_client.RetryableClient("resourcegroupstaggingapi", self.instance_id, self.region, self.logger)

    def get_resources(self, key, values, parser=None):
        """
        Method for calling the get_resources via boto from the resourcegroupstaggingapi.
        :param - key is the key to search for as a string.
        :param - values are the values to search for as a list.
        :param - parser is an object with a .parse call on it that will take as a parameter a page of pageable api call and
        return a desired format.
        :returns - the result of parser.parse or a list of pages from the pageable get_resources call.
        """
        try:
            operation_parameters = {"TagFilters":[{'Key': key,'Values': values}]}
            return self.client.call_pageable_client(self.client.default_client, "get_resources", operation_parameters, parser)
        
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDeniedException':
                raise PatchManagerError("GetResources had access denied.",
                                    ExitCodes.GET_RESOURCES_ACCESS_DENIED)
            else:
                raise PatchManagerError("GetResources failed", ExitCodes.GET_RESOURCES_API_ERROR, e)
        except Exception as e:
            raise PatchManagerError("GetResource failed.", ExitCodes.GET_RESOURCES_ERROR, e)

class ResourceGroupsParser():

    def __init__(self, region, logger):
        """
        Constructor
        :param - region is the region to expect returned from the arns.
        :param - logger is the logging.getLogger() object to print info to logs.
        """
        self.main_regex = r"(^$)|^Key=[\w\d\s_.:/=+\-@]{0,256},Values=[\w\d\s_.:/=+\-@]{0,256}(,{1}[\w\d\s_.:/=+\-@]{1,256}){0,49}"
        self.main_regex_prog = re.compile(self.main_regex)
        self.baseline_arn_regex = "^arn:aws:ssm:%s:([0-9]{12}):patchbaseline/(pb-[0-9a-f]{17})$"%(region)
        self.baseline_id_regex = "pb-[0-9a-f]{17}"
        self.baseline_prog = re.compile(self.baseline_id_regex)
        self.prog = re.compile(self.baseline_arn_regex)
        self.logger = logger

    def parse(self, result_page):
        """
        Method for parsing a page from a get_resources boto call.
        :param - result_page is a single page form the pageable get_resources api returned from boto.
        :returns - a list of baseline_ids or []
        """
        baseline_ids = []
        for resource in result_page["ResourceTagMappingList"]:
            if self.prog.match(resource['ResourceARN']):
                baseline_id = self.baseline_prog.search(resource['ResourceARN'])
                baseline_ids.append(baseline_id.group(0))
        return baseline_ids

    def parse_baseline_tags(self, tags):
        """
        Method for parsing the tags as received from the documents parameter.
        :param tags - is the BaselineTags string directly from the public document.
        """
        try:  
            if not self.main_regex_prog.match(tags):
                raise PatchManagerError("Baseline tags must match regex %s but do not. Tags provided were: %s"\
                    %(self.main_regex, tags), \
                    ExitCodes.BASELINE_TAGS_REGEX_ERROR)

            result = tags.split("Key=", 1)
            key_values = result[1].split(",Values=", 1)
            key = key_values[0].strip()
            values = key_values[1].split(",")
            if values:
                values = [value.strip() for value in values]
            else:
                values = key_values[1]
            return (key, values)
        except Exception as e:
            self.logger.exception("Exception interpreting the tags to use %s"%(tags), e)
            raise Exception(e)
