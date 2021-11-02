import logging
import os
import json

from patch_common.constant_repository import ExitCodes
from patch_common.downloader import download_file, load_json_file, is_access_denied
from patch_common.exceptions import PatchManagerError
from patch_common.operating_system_parser import get_operating_system

logger = logging.getLogger()


def load_baseline_override(baseline_override_path, document_step, region):
    """
    Function to download and grab the relevant Baseline Override for a particular instance based on Operating System
    Throws an error if a baseline override is provided but there is either
      - 0 Baseline Overrides which match the current OS
      - More than 1 Baseline Override which match the current OS

    :param region: region credentials are vended from
    :param document_step: - Either PatchMacOS or PatchLinux
    :param baseline_override_path: url or s3 file path to Baseline Override object
    :return: baseline override dict if baseline override provided, else None
    """
    if not baseline_override_path:
        return None

    logger.info("Downloading Baseline Override from %s", baseline_override_path)
    baseline_overrides = _download_baseline_override_content(baseline_override_path, region)
    operating_system = get_operating_system(document_step)
    baseline_override_dict = _get_baseline_dict_for_operating_system_product(baseline_overrides, operating_system)

    if baseline_override_dict:
        logger.debug("Using Baseline Override: %s", baseline_override_dict)
        return baseline_override_dict


def output_baseline_override_results(summary, compliance):
    # Delete Irrelevant data from compliance summary + items
    summary_content = summary["Content"][0]
    summary_content.pop("BaselineId")

    packages = compliance["Content"]
    non_compliant_packages = [p for p in packages if p["Status"] == "NON_COMPLIANT"]
    for pkg in non_compliant_packages:
        pkg.pop("DocumentName")
        pkg.pop("DocumentVersion")
        pkg.pop("PatchBaselineId")
        pkg.pop("PatchGroup")

    logger.info("[BASELINE OVERRIDE]: Summary: %s", json.dumps(summary_content, indent=4, sort_keys=True))
    if len(non_compliant_packages) > 0:
        logger.info("[BASELINE OVERRIDE]: Non Compliant Packages: %s",
                    json.dumps(non_compliant_packages, indent=4, sort_keys=True))
    else:
        logger.info("[BASELINE OVERRIDE]: All Packages are Compliant.")


def _get_baseline_dict_for_operating_system_product(baseline_overrides, operating_system):
    """
    Filter list of raw baseline overrides and match the one with the correct Operating System
    :param baseline_overrides: list of raw baseline override dicts
    :param operating_system: current executing operating system
    :return: baseline override which matches the current OS
    """
    baseline_override_dict = None
    for baseline in baseline_overrides:
        if "OperatingSystem" in baseline and operating_system == baseline["OperatingSystem"]:
            if not baseline_override_dict:
                baseline_override_dict = _convert_baseline_override_to_request_format(baseline)
            else:
                logger.error("Multiple Valid Baseline Overrides found for Operating System %s", operating_system)
                raise PatchManagerError(
                    "Multiple Baseline Overrides provided for given OS: {}".format(operating_system),
                    ExitCodes.BASELINE_OVERRIDE_MULTIPLE_OVERRIDES_PROVIDED_FOR_OS
                )

    if baseline_override_dict:
        return baseline_override_dict
    else:
        logger.error("No Valid Baseline Override found for Operating System %s", operating_system)
        raise PatchManagerError(
            "Unable to find Baseline Override for Operating System: {} , in BaselineOverride.".format(operating_system),
            ExitCodes.BASELINE_OVERRIDE_MISSING_OS
        )


def _download_baseline_override_content(baseline_override_path, region):
    """
    Download baseline override and extract content
    :param baseline_override_path: url or s3 file path to baseline override
    :return: baseline override json contents
    """
    file_name = "baseline_override.json"
    if download_file(baseline_override_path, file_name, region):
        content = load_json_file(file_name)
        # content is loaded, delete file
        os.remove(file_name)
        if is_access_denied(content):
            logger.error("Found access denied error: %s when downloading BaselineOverride", content)
            raise PatchManagerError("Access denied to provided BaselineOverride: " + baseline_override_path,
                                    ExitCodes.BASELINE_OVERRIDE_ACCESS_DENIED)
        elif isinstance(content, dict):
            logger.error("Invalid Baseline Override JSON Array")
            raise PatchManagerError("Provided Baseline Override was not a JSON Array", ExitCodes.BASELINE_OVERRIDE_INVALID)
        else:
            return content
    else:
        raise PatchManagerError("Unable to download BaselineOverride: " + baseline_override_path,
                                ExitCodes.BASELINE_OVERRIDE_DOWNLOAD_ERROR)



def _convert_baseline_override_to_request_format(raw_baseline_override):
    """
    Convert provided raw baseline override Json to expected Baseline Override format for GetDeployablePatchSnapshotForInstance
    Removes any unnecessary fields from the object
    :param raw_baseline_override: raw dict from customer provided Json
    :return: Baseline Override dict in expected format
    """
    return {
        "OperatingSystem": raw_baseline_override.get("OperatingSystem"),
        "GlobalFilters": raw_baseline_override.get("GlobalFilters"),
        "ApprovalRules": raw_baseline_override.get("ApprovalRules"),
        "ApprovedPatches": raw_baseline_override.get("ApprovedPatches"),
        "ApprovedPatchesComplianceLevel": raw_baseline_override.get("ApprovedPatchesComplianceLevel"),
        "ApprovedPatchesEnableNonSecurity": raw_baseline_override.get("ApprovedPatchesEnableNonSecurity"),
        "RejectedPatches": raw_baseline_override.get("RejectedPatches"),
        "RejectedPatchesAction": raw_baseline_override.get("RejectedPatchesAction"),
        "Sources": raw_baseline_override.get("Sources")
    }