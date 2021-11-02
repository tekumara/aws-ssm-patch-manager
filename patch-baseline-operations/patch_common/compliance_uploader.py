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
                  compliance):
    """
    Upload an inventory report for the instance containing the summary and compliance items. Handles inventory
    hash change logic
    :param ssm_client_selector: to hit inventory
    :param instance_id: for the items
    :param summary_item: to be uploaded with put_inventory
    :param compliance_item: to be uploaded with put_inventory, empty if hash has not changed
    """
    logger.info("Start to upload patch compliance.")
    logger.debug("Compliance: %s", str(compliance))

    compliance_contents = compliance["Items"]
    clobber = False
    retries = 0
    success = False
    while retries <= 1 and not success:
        retries = retries + 1

        if clobber or _has_compliance_hash_changed(compliance):
            logger.info("Attempting full upload")
            compliance["Items"] = compliance_contents
        else:
            logger.info("Report is unchanged, attempting partial upload")
            del (compliance["Items"])

        try:
            default_ssm_client = client_selector.get_default_client(instance_id, region)

            items = []
            if "Items" in compliance:
                items = compliance["Items"]

            default_ssm_client.put_compliance_items(
                ResourceId=compliance["ResourceId"],
                ResourceType=compliance["ResourceType"],
                ComplianceType=compliance["ComplianceType"],
                ExecutionSummary=compliance["ExecutionSummary"],
                Items=items,
                UploadType="PARTIAL",
                ItemContentHash=compliance["ItemContentHash"]
            )
            logger.info("Upload complete.")
            success = True
            _persist_inventory_hash(compliance)

        except (ClientError, PatchManagerError) as e:
            # Only worry about a specific service error code
            # TODO - check these Exception types with put compliance.
            if isinstance(e, ClientError) and e.response["Error"]["Code"] in ["InvalidItemContentException", "ItemContentMismatchException"]:
                logger.warn("Hash mismatch on upload, retry", exc_info=True)
                clobber = True
            elif not client_selector.is_managed_instance(instance_id):
                _upload_report_with_fallback_client(region, instance_id, compliance)
                return
            else:
                raise PatchManagerError("Unable to upload the inventory:", ExitCodes.PUT_INVENTORY_ERROR, e)
        except Exception as e:
            raise PatchManagerError("Encounter service side error when uploading the inventory", ExitCodes.PUT_INVENTORY_ERROR, e)
    if not success:
        raise PatchManagerError("Could not upload inventory report after retries.", ExitCodes.PUT_INVENTORY_ERROR)

def _upload_report_with_fallback_client(region,
                                   instance_id,
                                   compliance):
    """
    Upload an inventory report using fallback ssm client
    :param instance_id: for the items
    :param summary_item: to be uploaded with put_inventory
    :param compliance_item: to be uploaded with put_inventory, empty if hash has not changed
    """
    fallback_ssm_client = client_selector.get_fallback_client(region)
    try:
        items = []
        if "Items" in compliance:
            items = compliance["Items"]

        fallback_ssm_client.put_compliance_items(
            ResourceId=compliance["ResourceId"],
            ResourceType=compliance["ResourceType"],
            ComplianceType=compliance["ComplianceType"],
            ExecutionSummary=compliance["ExecutionSummary"],
            Items=items,
            ItemContentHash=compliance["ItemContentHash"]
        )
        logger.info("Upload complete.")
        _persist_inventory_hash(compliance)
    except Exception as e:
        # TODO - check these errors.
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
        os.makedirs(os.path.join(DEFAULT_HASH_LOCATION, item['ItemContentHash']))
    except:
        logger.warn("Could not persist inventory hash", exc_info=True)


def _has_compliance_hash_changed(compliance):
    """
    checks the previous hash uploaded, if any
    :param compliance: to get ContentHash from
    :return:
    """
    new_hash = compliance['ItemContentHash']
    hash_path = os.path.join(DEFAULT_HASH_LOCATION, new_hash)
    return not os.path.exists(hash_path)
