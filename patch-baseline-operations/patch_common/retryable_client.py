from patch_common import client_selector
from botocore.exceptions import ClientError
from patch_common.constant_repository import ExitCodes

class RetryableClient():  
    "Class for encapsulating current retry pattern found in common_os_selector_methods"

    def __init__(self, client_type, instance_id, region, logger):
        """
        Constructor
        :param - client_type is the client_type as a string such as "ssm"
        :param - instance_id is the instance_id of the current instance.
        :param - is the region of the current instance.
        :param - logger is the logging.getLogger() object for printing to logs.
        """
        self.client_type = client_type
        self.instance_id = instance_id
        self.region = region
        self.default_client = client_selector.get_default_client(instance_id, region, client_type)
        self.logger = logger
        self.retry_client = None
    
    def call_pageable_client(self, client, api, client_parameters, response_parser=None):
        """
        Method for retyring a paginating client call with a fallback client if it fails. 
        :param - client is the client to use.
        :param - api is the api to call as a str
        :param - client_parameters are the lclient parameters as a dict.
        :param - response_parser is an object with a parse() method that takes the expected page result from the paginator
        as input to parse and returns a result.
        :returns the result of parser.parse or a list of pages.
        """
        try:
            # please note, we are simply calling the client with reflection.
            paginator = getattr(client, 'get_paginator')(api)
            
            if client_parameters:
                page_iterator = paginator.paginate(**client_parameters)
            else:
                page_iterator = paginator.paginate()

            results = []
            for page in page_iterator:
                if response_parser:
                    results.extend(response_parser.parse(page))
                else:
                    results.append(page)

            return results
        except ClientError as e:
            self.logger.exception(e)
            # if we have not attempted a retry before.
            if not self.retry_client:
                if not client_selector.is_managed_instance(self.instance_id):
                    self.retry_client = client_selector.get_fallback_client(self.region, self.client_type)
                    return self.call_pageable_client(self.retry_client, api, client_parameters, response_parser)
            raise e
        except Exception as e:
            self.logger.exception(e)
            raise e
    
    def call_client(self, client, api, client_parameters, response_parser=None):
        """
        Method for retyring a client call with a fallback client if it fails. 
        :param - client is the client to use.
        :param - api is the api to call as a str
        :param - client_parameters are the lclient parameters as a dict.
        :param - response_parser is an object with a parse() method that takes the expected page result from the paginator
        as input to parse and returns a result.
        :returns the result of parser.parse or a list of pages.
        """
        try:
            # please note, we are simply calling the client with reflection.
            if client_parameters:
                result = getattr(client, api)(**client_parameters)
            else:
                result = getattr(client, api)

            if response_parser:
                return response_parser.parse(result)
            else:
                return result

        except ClientError as e:
            self.logger.exception(e)
            # if we have not attempted a retry before.
            if not self.retry_client:
                if not client_selector.is_managed_instance(self.instance_id):
                    self.retry_client = client_selector.get_fallback_client(self.region, self.client_type)
                    return self.call_client(self.retry_client, api, client_parameters, response_parser)
            raise e
        except Exception as e:
            self.logger.exception(e)
            raise e