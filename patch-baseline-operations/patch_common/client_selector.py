import logging
import boto3

from patch_common.constant_repository import ExitCodes
from patch_common.exceptions import PatchManagerError

from botocore.credentials import create_credential_resolver
from botocore.session import Session
from botocore.config import Config

logger = logging.getLogger()

# Change to use Config for retries, otherwise, it will throw SNIMissingWarning
config = Config(retries=dict(max_attempts=5))

def get_default_client(instance_id, region, client_type = "ssm"):
    """
    Return default client based on instance type, using creds from instance profile if it is ec2 instance.
    Using regular creds if it is managed instance
    :param instance_id: instance_id
    :param region: AWS region
    :param client_type: the client to create
    :return a client of the provided client type.
    """

    if is_managed_instance(instance_id):
        return boto3.client(client_type, region_name=region, config=config)

    creds = get_metadata_creds()
    if creds is None:
        raise PatchManagerError("No instance metadata found on ec2 instance", ExitCodes.NO_INSTANCE_METADATA)

    return boto3.client(client_type, region_name=region,
                        aws_access_key_id=creds.access_key,
                        aws_secret_access_key=creds.secret_key,
                        aws_session_token=creds.token,
                        config=config)

def get_fallback_client(region, client_type = "ssm"):
    return boto3.client(client_type, region_name=region, config=config)

def is_managed_instance(instance_id):
    return instance_id.startswith('mi-')

def get_metadata_creds():
    session = Session()
    session.set_config_variable('metadata_service_timeout', 1000)
    session.set_config_variable('metadata_service_num_attempts', 2)
    credential_resolver = create_credential_resolver(session)
    creds = credential_resolver.load_credentials()
    return creds
