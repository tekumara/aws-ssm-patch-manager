from botocore.exceptions import ClientError
import logging
import os

from patch_common import client_selector
from patch_common.constant_repository import ExitCodes
from patch_common.exceptions import PatchManagerError

logger = logging.getLogger()
DEFAULT_HASH_LOCATION = "/var/log/amazon/ssm/pb-hashes"


def upload_report(region,
                  instance_id,
                  summary_item,
                  compliance_item):
    """
    Upload an inventory report for the instance containing the summary and compliance items. Handles inventory
    hash change logic
    :param client_selector: to hit inventory
    :param instance_id: for the items
    :param summary_item: to be uploaded with put_inventory
    :param compliance_item: to be uploaded with put_inventory, empty if hash has not changed
    """
    logger.info("Start to upload patch compliance.")
    logger.info("Summary: %s", str(summary_item))
    logger.debug("Compliance: %s", str(compliance_item))

    compliance_contents = compliance_item["Content"]
    clobber = False
    retries = 0
    success = False
    while retries <= 1 and not success:
        retries = retries + 1

        if clobber or _has_compliance_hash_changed(compliance_item):
            logger.info("Attempting full upload")
            compliance_item["Content"] = compliance_contents
        else:
            logger.info("Report is unchanged, attempting partial upload")
            del (compliance_item["Content"])

        try:
            default_ssm_client = client_selector.get_default_client(instance_id, region)
            default_ssm_client.put_inventory(
                InstanceId=instance_id,
                Items=[summary_item, compliance_item]
            )
            logger.info("Upload complete.")
            success = True
            _persist_inventory_hash(compliance_item)

        except (ClientError, PatchManagerError) as e:
            # Only worry about a specific service error code
            if isinstance(e, ClientError) and e.response["Error"]["Code"] in ["InvalidItemContentException", "ItemContentMismatchException"]:
                logger.warn("Hash mismatch on upload, retry", exc_info=True)
                clobber = True
            elif isinstance(e, ClientError) and e.response["Error"]["Code"] == "ItemSizeLimitExceededException":
                logger.warn("Exceeded Inventory Size Limit, retry without uploading CVE data")
                compliance_contents = _remove_cves_from_report(compliance_contents)
            elif not client_selector.is_managed_instance(instance_id):
                _upload_report_with_fallback_client(region, instance_id, summary_item, compliance_item)
                return
            else:
                raise PatchManagerError("Unable to upload the inventory:", ExitCodes.PUT_INVENTORY_ERROR, e)
        except Exception as e:
            raise PatchManagerError("Encounter service side error when uploading the inventory", ExitCodes.PUT_INVENTORY_ERROR, e)
    if not success:
        raise PatchManagerError("Could not upload inventory report after retries.", ExitCodes.PUT_INVENTORY_ERROR)

def _upload_report_with_fallback_client(region,
                                   instance_id,
                                   summary_item,
                                   compliance_item):
    """
    Upload an inventory report using fallback ssm client
    :param instance_id: for the items
    :param summary_item: to be uploaded with put_inventory
    :param compliance_item: to be uploaded with put_inventory, empty if hash has not changed
    """
    fallback_ssm_client = client_selector.get_fallback_client(region)
    try:
        fallback_ssm_client.put_inventory(
            InstanceId=instance_id,
            Items=[summary_item, compliance_item]
        )
        logger.info("Upload complete.")
        _persist_inventory_hash(compliance_item)
    except Exception as e:
        raise PatchManagerError("Unable to upload the inventory using fallback creds:", ExitCodes.PUT_INVENTORY_ERROR, e)


def _persist_inventory_hash(item):
    """
    Persists the inventory hash for future comparison, cleans previous hashes
    :param item: to get ContentHash from
    """
    try:
        if os.path.exists(DEFAULT_HASH_LOCATION):
            hashes = os.listdir(DEFAULT_HASH_LOCATION)
            if len(hashes) > 1:
                logger.warn("Found multiple old hashes in directory %s", hashes)
            for directory in hashes:
                os.rmdir(os.path.join(DEFAULT_HASH_LOCATION, directory))
        os.makedirs(os.path.join(DEFAULT_HASH_LOCATION, item['ContentHash']))
    except:
        logger.warn("Could not persist inventory hash", exc_info=True)


def _has_compliance_hash_changed(compliance):
    """
    checks the previous hash uploaded, if any
    :param compliance: to get ContentHash from
    :return:
    """
    new_hash = compliance['ContentHash']
    hash_path = os.path.join(DEFAULT_HASH_LOCATION, new_hash)
    return not os.path.exists(hash_path)


def _remove_cves_from_report(compliance_contents):
    for pkg in compliance_contents:
        if "CVEIds" in pkg:
            del pkg["CVEIds"]

    return compliance_contents
