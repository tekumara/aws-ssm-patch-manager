from patch_common.exceptions import PatchManagerError
from patch_common import retryable_client
from botocore.exceptions import ClientError
from patch_common.constant_repository import ExitCodes
import re

class SSMClient():


    def __init__(self, instance_id, region, logger):
        """
        Constructor
        :param - instance_id is the instance_id of the current instance.
        :param - region is the region the current instance is in.
        :param - logger is the logging.getLogger() object for printing to logs.
        """
        self.logger = logger
        self.instance_id = instance_id
        self.region = region
        self.client = retryable_client.RetryableClient("ssm", self.instance_id, self.region, self.logger)

    def describe_patch_baselines(self, operating_system, parser=None):
        """
        Method for calling describe_patch_baseline.
        :param - operating_system is the operating_system of the current instance.
        :param - parser is an object with a .parse() method that will take as input the result of a page of describe_patch_baselines() result.
        :return - the result of parser.parse or a list of pages form the request.
        """
        try:
            operation_parameters = None
            return self.client.call_pageable_client(self.client.default_client, "describe_patch_baselines", operation_parameters, parser)
        
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDeniedException':
                raise PatchManagerError("DescribePatchBaselines had access denied.",
                                    ExitCodes.DESCRIBE_PATCH_BASELINES_ACCESS_DENIED)
            else:
                raise PatchManagerError("DescribePatchBaselines failed", ExitCodes.DESCRIBE_PATCH_BASELINES_API_ERROR, e)
        except Exception as e:
            raise PatchManagerError("DescribePatchBaselines failed.", ExitCodes.DESCRIBE_PATCH_BASELINES_ERROR, e)

    def get_patch_baseline(self, baseline_id):
        """
        Method for calling describe_patch_baseline.
        :param - baseline_id is the id of the baseline to retrieve.
        :return - the baseline dict response from botocore.
        """
        try:
            method_name = "get_patch_baseline"
            operation_parameters = {"BaselineId" : baseline_id}
            return self.client.call_client(self.client.default_client, method_name, operation_parameters)
        
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDeniedException':
                raise PatchManagerError("%s had access denied."%(method_name),
                                    ExitCodes.GET_PATCH_BASELINE_ACCESS_DENIED)
            else:
                raise PatchManagerError("%s failed"%(method_name), ExitCodes.GET_PATCH_BASELINE_API_ERROR, e)
        except Exception as e:
            raise PatchManagerError("%s failed."%(method_name), ExitCodes.GET_PATCH_BASELINE_ERROR, e)  

class DescribePatchBaselinesParser():
    """
    Class for parsing the pages of the pageable describe_patch_baseline api call from botocore.
    """

    def __init__(self, operating_system):
        """
        Constructor
        :param - operating_system is the operating system used to make the call.
        """
        self.operating_system = operating_system
        self.baseline_id_regex = "pb-[0-9a-f]{17}"
        self.baseline_prog = re.compile(self.baseline_id_regex)

    def parse(self, page):
        """
        Method for parsing a page from the pageable describe_patch_baseline boto call.
        :returns a list of baseline_ids or []
        """
        possible_baselines = []
        for baseline in page["BaselineIdentities"]:
            if (baseline["OperatingSystem"] == self.operating_system):
                baseline_id = self.baseline_prog.search(baseline["BaselineId"])
                possible_baselines.append(baseline_id.group(0))

        return possible_baselines