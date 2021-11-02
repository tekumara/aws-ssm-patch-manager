#!/usr/bin/env python
# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import copy
import sys
import os
import subprocess
import json
import logging
import uuid
from patch_common import shell_interaction
from patch_common.baseline_override import load_baseline_override
from patch_common.exceptions import PatchManagerError
from patch_common.snapshot_fetcher import download_snapshot
from patch_common.resource_groups import ResourceGroupsClient, ResourceGroupsParser
from patch_common.ssm import SSMClient, DescribePatchBaselinesParser
import datetime

sys.path.insert(1, "./")
sys.path.insert(1, "./botocore/vendored")

import boto3
from botocore.exceptions import ClientError
from patch_common import client_selector
from patch_common.constant_repository import ExitCodes, Get_Baseline_To_Snapshot_Keys


# initialize logging
LOGGER_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOGGER_DATEFORMAT = "%m/%d/%Y %X"
LOGGER_LEVEL = logging.INFO
LOGGER_STREAM = sys.stdout

logging.basicConfig(format=LOGGER_FORMAT, datefmt=LOGGER_DATEFORMAT, level=LOGGER_LEVEL, stream=LOGGER_STREAM)
logger = logging.getLogger()

def get_instance_information():
    """
    Gets the instance's id and region, from environment variables

    :return: returns the instanceId and region as a tuple.
    """
    return os.environ["AWS_SSM_INSTANCE_ID"], os.environ["AWS_SSM_REGION_NAME"]

def _launch_entrance(entrance_script, operation_type, product, script_args):
    """
    launches the requested entrance script as as separate process and returns whatever exit code that returns.

    Deals with process interactions and odd agent death issues.

    :param entrance_script: path to the script
    :param operation_type: operation to run
    :param product: of the instance
    :param script_args: arguments to send the script
    :return:
    """
    p = subprocess.Popen([sys.executable, '-u', entrance_script] + script_args, stdout=sys.stdout, stderr=sys.stderr)
    # DO NOT REMOVE THE LINE BELOW
    # IF REMOVED, invoked script may not find the necessary dependency
    (std_out, std_err) = p.communicate()
    shell_interaction.restart_agent(operation_type, product, p.returncode)
    return p.returncode

def _setup_se_linux_context():
    """
    When SE Linux is enabled, the installation script needs to be given the appropriate SE Linux context for it to
    install certain packages.
    Will swallow errors if it can't do it, since only some packages require the context change
    :return:
    """
    try:
        (chcon_path, returncode) = shell_interaction.shell_command(["which", "chcon"])
        if returncode != 0:
            logger.warn("Unable to locate chcon, code: %d.", returncode)
            return
        chcon_path = chcon_path.strip()

        (yum_path, returncode) = shell_interaction.shell_command(["which", "yum"])
        if returncode != 0:
            logger.warn("Unable to locate yum, code: %d.", returncode)
            return
        yum_path = yum_path.strip()

        (_, returncode) = shell_interaction.shell_command([chcon_path, "--reference", yum_path, "./main_entrance.py"])
        if returncode != 0:
            logger.warn("Unable to gain necessary access for possible kernel updates, code: %d.", returncode)
    except:
        # already tried to set SELinux access but failed, continue to update packages
        pass

def _get_snapshot_info_with_fallback_ssm_client(instance_id, region, snapshot_id, baseline_override=None):
    """
    Method for getting the patch snapshot with the fallback ssm client (different cred model).
    :param instance_id is the instance_id script is being executed on.
    :region is the region the instance is in. 
    :snapshot_id is the snapshot id to use.
    :param: baseline_override - the optional baseline override dict which matches the current OS
    :returns GetDeployablePatchSnapshot result.
    """
    logger.info("Unable to retrieve snapshot with default ssm client, retry with fallback ssm client")
    fallback_ssm_client = client_selector.get_fallback_client(region, "ssm")
    try:
        patch_snapshot = _get_snapshot_with_client(fallback_ssm_client, instance_id, snapshot_id, baseline_override)
        logger.debug("Success to get deployable snapshot: %s using the fallback client", patch_snapshot)
        return patch_snapshot

    except ClientError as e:
        if e.response['Error']['Code'] == 'AccessDeniedException':
            raise PatchManagerError("GetDeployableSnapshotForInstance had access denied and no metadata credentials were available",
                                    ExitCodes.NO_INSTANCE_METADATA)
        else:
            raise PatchManagerError("Get Snapshot failed", ExitCodes.SNAPSHOT_API_ERROR, e)
    except Exception as e:
        raise PatchManagerError("Get Snapshot failed", ExitCodes.SNAPSHOT_ERROR, e)

def _get_snapshot_info(instance_id, snapshot_id, region, baseline_override=None):
    """
    Calls get_deployable_patch_snapshot_for_instance.
    :param: instance_id to get the snapshot for.
    :param: snapshot_id of the snapshot to retrieve or new generated id to use.
    :param: region - the region the instance is in.
    :param: baseline_override - the optional baseline override dict which matches the current OS
    :return: Returns the patch snapshot object from get_deployable_patch_snapshot_for_instance.
    """
    try:
        ssm_client = client_selector.get_default_client(instance_id, region, "ssm")
        patch_snapshot = _get_snapshot_with_client(ssm_client, instance_id, snapshot_id, baseline_override)

        logger.debug("GetSnapshot returned: %s.", patch_snapshot)
        return patch_snapshot
    except (ClientError, PatchManagerError) as e:
        logger.exception(e)
        aws_error = e.response['Error']['Code']
        if isinstance(e, ClientError) and aws_error == 'UnsupportedOperatingSystem':
            raise PatchManagerError("Unsupported Operating System", ExitCodes.SNAPSHOT_UNSUPPORTED_OS, e)
        elif not client_selector.is_managed_instance(instance_id):
            return _get_snapshot_info_with_fallback_ssm_client(instance_id, region, snapshot_id, baseline_override)
        else:
            raise PatchManagerError("Get Snapshot failed", ExitCodes.SNAPSHOT_API_ERROR, e)
    except Exception as e:
        raise PatchManagerError("Get Snapshot failed", ExitCodes.SNAPSHOT_ERROR, e)

def get_patch_baseline(baseline_tags, operating_system, instance_id, region):
    """
    Method for getting a patch baseline from the local account.
    :param baseline_tags - The tag attached to the baseline to retrieve.
    :param operating_system - The operating system from get-deployable-patch-snapshot-for-instance.
    :param instance_id - The instance payload is executing on.
    :param region - The region ec2 instance is in.  
    :return baseline or ""
    """
    if not baseline_tags:
        return None

    logger.info("Searching for baselines with tags %s", baseline_tags)
    # parser input parameters
    resource_groups_parser = ResourceGroupsParser(region, logger)
    key, values = resource_groups_parser.parse_baseline_tags(baseline_tags)

    # get_baseline_from_tags
    resource_client = ResourceGroupsClient(instance_id, region, logger)
    baseline_ids_from_tags = resource_client.get_resources(key, values, resource_groups_parser)

    logger.info("Baselines from tags are.... %s", " ".join(baseline_ids_from_tags))

    if not baseline_ids_from_tags:
        return None
    else:
        logger.info("Found %s baselines with tags.", str(len(baseline_ids_from_tags)))
    # get all baselines in account
    ssm_client = SSMClient(instance_id, region, logger)
    baseline_ids_by_os = ssm_client.describe_patch_baselines(operating_system, DescribePatchBaselinesParser(operating_system))

    if not baseline_ids_by_os:
        return None
    else:
        logger.info("Found %s baselines matching os.",str(len(baseline_ids_by_os)))

    baseline_id = get_intersect_of_tag_and_os_baselines(key, values, operating_system, baseline_ids_from_tags, baseline_ids_by_os)

    if not baseline_id:
        return None

    logger.info("Found baseline %s matching both tag key value and operating system."%(baseline_id))
    return ssm_client.get_patch_baseline(baseline_id)

def get_intersect_of_tag_and_os_baselines(key, values, operating_system, baseline_ids_from_tags, baseline_ids_by_os):
    """
    Method for returning a single baseline that intersects two lists of baseline_ids.
    :param key - is the key tag of the baseline_ids_from_tags that was used (as a str) (for logging purposes)
    :param values - is the list of strings of the baseline_ids_from_tags that were used (for logging purposes)
    :param - baseline_ids_from_tags is a list of baseline ids that were retrieved by tag key values.
    :param - baseline_ids_by_os is a list of baseline ids by os that were retrieve by tag key values.
    :returns a single baseline id or None.
    """
    possible_baselines = []
    for baseline_id in baseline_ids_from_tags:
        logger.info("Checking if baseline %s with tag matches baselines for this os %s", baseline_id, " ".join(baseline_ids_by_os))
        if baseline_id in baseline_ids_by_os:
            possible_baselines.append(baseline_id)

    if len(possible_baselines) > 1:
        patch_manager_error = "More than one baseline with tag key: %s values %s and operating system: %s."%(key,', '.join(values), operating_system)
        patch_manager_error = patch_manager_error + ". Unable to determine which one to use. \n"
        patch_manager_error = patch_manager_error + ". Baselines matching tag key, value and operating system are: %s"%(','.join(possible_baselines))
        raise PatchManagerError(patch_manager_error, ExitCodes.PATCH_ASSOCIATIONS_BASELINE_ERROR)
    elif len(possible_baselines) == 0:
        return None
    else:
        return possible_baselines[0]

def _describe_association_with_fallback_ssm_client(region, association_id, operating_system):
    """
    Method for describing an association with an alternative ssm client creds model.
    :param region is the region to look for.
    :param association_id of the association to retrieve.
    :param operating_system is the operating system to get baselines for. 
    :return the result of DescribeAssociation request.
    """
    logger.info("Unable to describe association with default ssm client, retry with fallback ssm client")
    fallback_ssm_client = client_selector.get_fallback_client(region)
    try:
        return fallback_ssm_client.describe_association(
            AssociationId=association_id
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'AccessDeniedException':
            raise PatchManagerError("DescribeAssociation had access denied and no metadata credentials were available",
                                    ExitCodes.NO_INSTANCE_METADATA)
        else:
            raise PatchManagerError("DescribeAssociation failed", ExitCodes.ASSOCIATION_API_ERROR, e)
    except Exception as e:
        raise PatchManagerError("DescribeAssociation failed", ExitCodes.ASSOCIATION_ERROR, e)

def describe_association(association_id, operating_system, instance_id, region):
    """
    Method for describing an association from the local account.
    :param association id - The association id of the association to describe.
    :param operating_system - The current operating system.
    :param instance_id - The instance payload is executing on.
    :param region - The region ec2 instance is in. 
    :return baseline or ""
    """
    try:
        ssm_client = client_selector.get_default_client(instance_id, region)
        return ssm_client.describe_association(
            AssociationId=association_id
        )
    except (ClientError, PatchManagerError) as e:
        logger.exception(e)
        if not client_selector.is_managed_instance(instance_id):
            return _describe_association_with_fallback_ssm_client(region, association_id, operating_system)
        else:
            raise PatchManagerError("DescribeAssociation failed", ExitCodes.ASSOCIATION_API_ERROR, e)
    except Exception as e:
        raise PatchManagerError("DescribeAssociation failed", ExitCodes.ASSOCIATION_ERROR, e)

def fetch_snapshot(operation_type, instance_id, region, reboot_option, document_step, snapshot_id = "", override_list=None, baseline_override = None):
    """
    Method for calling get_deployable_patch_snapshot_for_instance. 
    :param: operation_type: Scan or Install
    :param: instance_id - the instance id operation is being run on.
    :param: region - the region the instance is in.
    :param: reboot_option - document parameter indicating if system should be rebooted after operation or not.
    :param: document_step - Either PatchMacOS or PatchLinux
    :param: snapshot_id: to request the snapshot with
    :param: override_list - the override list provided by customer to use during an install operation.
    :param: baseline_override = the s3 location of the Baseline Override provided by the customer.

    :return: (operating_system, product) of this instance according to the service
    """
    logger.info("Running with snapshot id = %s and operation = %s" % (snapshot_id, operation_type))
    if snapshot_id == "":
            snapshot_id = str(uuid.uuid4())

    if baseline_override and override_list:
        raise PatchManagerError("Cannot provide both Baseline Override and Install Override List"
                                , ExitCodes.BASELINE_OVERRIDE_AND_INSTALL_OVERRIDE_PROVIDED)

    baseline_override_dict = load_baseline_override(baseline_override, document_step, region)
    snapshot_info = _get_snapshot_info(instance_id, snapshot_id, region, baseline_override_dict)
    product = snapshot_info['Product']
    snapshot = download_snapshot(snapshot_info['SnapshotDownloadUrl'])
    patch_group = snapshot.get("patchGroup") or ""
    baseline = snapshot["patchBaseline"]
    operating_system = baseline["operatingSystem"]

    logger.info("Instance Id: %s", instance_id)
    logger.info("Region: %s", region)
    logger.info("Product: %s", product)
    logger.info("Patch Group: %s", patch_group)
    logger.info("Operation type: %s", operation_type)
    logger.info("Snapshot Id: %s", snapshot_id)
    logger.info("Patch Baseline: %s", baseline)
    logger.info("Reboot Option: %s", reboot_option)

    save_metrics_id(snapshot_info.get("MetricsId"))

    return (snapshot_id, product, patch_group, baseline, operating_system)

def save_snapshot_associations(baseline, operating_system, instance_id, region, product, patch_group, operation_type, snapshot_id, reboot_option, association_id= None, override_list= None, association_severity= None):
    """
    Method for saving a snapshot to the directory location for payload execution.
    :param baseline is the Baseline key retrieved from the snapshot OR GetPatchBaseline call.
    :param operating_system is the os of the current instance.
    :param region is the region the instance is in .
    :param product is the product the snapshot is for.
    :param patch_group is any patch group tag the baseline has.
    :param operation_type is scan or install.
    :param snapshot_id is the snapshot_id of the snapshot that was created or retrieved.
    :param reboot_option is the option to reboot or not reboot the instance.
    :param override_list is the override list to use in an install operations.
    """
    # save the snapshot of baseline along with product, instance id, region
    # so APT / YUM can use
    try:
        with open("./snapshot.json", "w") as f:
            json.dump({
                "patchBaseline": baseline,
                "product": product,
                "patchGroup": patch_group,
                "instanceId": instance_id,
                "region": region,
                "operation": operation_type,
                "snapshotId": snapshot_id,
                "installOverrideList": override_list,
                "rebootOption": reboot_option,
                "associationId": association_id,
                "associationSeverity": association_severity
        }, f)
    except Exception as e:
        logger.exception("Unable to save processed snapshot.json.")
        raise PatchManagerError("Unable to save processed snapshot.json.", ExitCodes.SNAPSHOT_COULDNT_SAVE, e)
    return operating_system, product


def save_snapshot(baseline, operating_system, instance_id, region, product, patch_group, operation_type, snapshot_id,
                  reboot_option, override_list=None, baseline_override=None):
    """
    Method for saving a snapshot to the directory location for payload execution.
    :param baseline is the Baseline key retrieved from the snapshot OR GetPatchBaseline call.
    :param operating_system is the os of the current instance.
    :param region is the region the instance is in .
    :param product is the product the snapshot is for.
    :param patch_group is any patch group tag the baseline has.
    :param operation_type is scan or install.
    :param snapshot_id is the snapshot_id of the snapshot that was created or retrieved.
    :param reboot_option is the option to reboot or not reboot the instance.
    :param override_list is the override list to use in an install operations.
    """
    # save the snapshot of baseline along with product, instance id, region
    # so APT / YUM can use
    try:
        with open("./snapshot.json", "w") as f:
            json.dump({
                "patchBaseline": baseline,
                "product": product,
                "patchGroup": patch_group,
                "instanceId": instance_id,
                "region": region,
                "operation": operation_type,
                "snapshotId": snapshot_id,
                "installOverrideList": override_list,
                "baselineOverride": baseline_override,
                "rebootOption": reboot_option
            }, f)
    except Exception as e:
        logger.exception("Unable to save processed snapshot.json.")
        raise PatchManagerError("Unable to save processed snapshot.json.", ExitCodes.SNAPSHOT_COULDNT_SAVE, e)
    return operating_system, product

def execute_entrance_script(entrance_script, operating_system, operation_type, product):

    try:
        script_args = ["--file", "snapshot.json"]
        if operating_system != "SUSE":
            _setup_se_linux_context()

        return _launch_entrance(entrance_script, operation_type, product, script_args)
    except PatchManagerError as e:
        shell_interaction.abort(e)
    except Exception:
        logger.exception("Error executing the entrance script")
        shell_interaction.abort()

def convert_baseline_to_snapshot_form(get_patch_baseline):
    """
    Method for converting the result of a get_patch_baseline() request to the get_deployable_patch_snapshot() baseline form.
    :param baseline retrieved from get_patch_baseline
    """
    logger.info("Converting baseline to snapshot form...")
    return _replace_keys(get_patch_baseline, Get_Baseline_To_Snapshot_Keys.KEYS)


def save_metrics_id(metrics_id):
    if not metrics_id or len(metrics_id) < 40:
        logger.info("Unable to initialize exit code reporting: No metrics ID from server")
        return
    try:
        with open("./metrics_id", "w") as f:
            f.write(metrics_id)
    except Exception as err:
        logger.info("Unable to save metrics id file: " + err)


def _get_snapshot_with_client(ssm_client, instance_id, snapshot_id, baseline_override=None):
    if baseline_override is not None:
        return ssm_client.get_deployable_patch_snapshot_for_instance(
            InstanceId=instance_id,
            SnapshotId=snapshot_id,
            BaselineOverride=baseline_override
        )
    else:
        return ssm_client.get_deployable_patch_snapshot_for_instance(
            InstanceId=instance_id,
            SnapshotId=snapshot_id
        )

def _replace_keys(d, km):
    """
    Method for recursively replacing the keys in a nested dictionary based on the provide key_map.
    :param d is the dictionary to replace.
    :param km is the key map of keys found in the dictionary with values to replace those keys with.
    """
    if not isinstance(d, dict):
        return d

    result_dict=copy.copy(d)
    for k, v in d.items():
        if k in km:
            # if it is a createdTime or createdDate,
            # convert to seconds. botocore returns a datetime object.
            if (k == "CreatedDate" or k == "ModifiedDate") and \
                    isinstance(d[k], datetime.datetime):
                linux_epoch = datetime.datetime(1970, 1, 1)
                linux_epoch = linux_epoch.replace(tzinfo=d[k].tzinfo)
                result_dict[k] = (d[k] - linux_epoch).total_seconds()
            # replace the baseline key with the snapshot key.
            result_dict[km[k]] = result_dict.pop(k)
            if isinstance(v, dict):
                result_dict[km[k]] = _replace_keys(v, km)
            elif isinstance(v, list):
                result_dict[km[k]] = list (
                    map(lambda item: _replace_keys(item, km), v)
                )
    return result_dict

