import boto3
import json
import logging
import os
import re
import ruamel.yaml as yaml

from patch_common.shell_interaction import download_from_url

logger = logging.getLogger()


def download_from_s3(s3_uri, file_path, region):
    """
    Download file from provided S3 URI

    :param s3_uri: S3 URI in the format of s3://<bucket>/<folder>/.../<file>
    :param file_path: local file path to save the downloaded file
    :param region: aws region the machine is managed through. This region must be in the same partition as the s3 bucket
    :return:
    """
    pattern = "^s3://([^/]+)/(.*?([^/]+))$"
    result = re.compile(pattern).match(s3_uri)
    if result is None:
        raise Exception("Provided S3 URI %s is not matching the pattern %s.", s3_uri, pattern)
    else:
        try:
            s3_client = boto3.client("s3", region_name=region)
            s3_client.download_file(result.group(1), result.group(2), file_path)
            return True
        except Exception:
            logger.error("Unable to download file from S3: %s.", s3_uri)
            raise


def download_file(remote_path, local_file_path, region):
    """
    Download remote file to given local file path

    :param remote_path: remote path to be downloaded, support to download HTTPS URL and S3 URI
    :param local_file_path: local file to save the downloaded file
    :param region: aws region the machine is managed through
    :return: True if successfully downloaded the file, False otherwise
    """
    downloaded = False
    if remote_path.startswith("https://"):
        downloaded = download_from_url(remote_path, local_file_path)

    elif remote_path.startswith("s3://"):
        downloaded = download_from_s3(remote_path, local_file_path, region)
    else:
        raise Exception("Only support to download with https urls and s3 uri, %s is invalid", remote_path)

    return downloaded


def is_access_denied(content):
    """
    Determine whether it is access denied when it is using HTTPS url
    When provided s3 https url but no access to it, CURL or WGET output will contain a string indicating access denied, e.g.
        <Error><Code>AccessDenied</Code><Message>Access Denied</Message>

    :param content: content of the downloaded file
    :return: True for access denied file, False otherwise
    """
    if type(content) is str:
        key_words = ["Error", "AccessDenied", "Access Denied"] # [Error, Code, Message]
        for key in key_words:
            if key not in content:
                return False
        return True
    return False


def load_yaml_file(file_path):
    """
    Method to load yaml format file
    @param file_path: local file path to be loaded
    :return:
    """
    yaml_path = None
    try:
        yaml_path = os.path.abspath(file_path)

        with open(yaml_path, 'r') as fp:
            return yaml.load(fp)
    except Exception:
        logger.error("Unable to load yaml file: %s. Please make sure the file you provided is in YAML format.", yaml_path)
        raise


def load_json_file(file_path):
    """
    Loads the json format file
    @param file_path: local file path to be loaded
    :return:  content in json format
    """
    json_path = None
    try:
        json_path = os.path.abspath(file_path)
        with open(json_path, 'r') as fp:
            return json.load(fp)
    except Exception:
        logger.error("Unable to load json file: %s. Please make sure the file you provided is in JSON format.", json_path)
        raise
