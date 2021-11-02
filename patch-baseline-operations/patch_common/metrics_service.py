import boto3
import datetime
import threading
import traceback
import sys

from patch_common import client_selector
from patch_common.constant_repository import exit_codes_to_meaning, Metrics

metrics_service = {
    'pinpoint_client': None,
    'instance_id': None,
    'product': None,
    'operation': None,
    'pinpoint_app_id': None,
    'snapshot': None,
    'account_id': None
}

patch_runtime_metrics = {
    Metrics.KERNEL_LIVE_PATCH_ENABLED: "false",
    Metrics.KERNEL_LIVE_PATCH_COMPLIANT: "false",
    Metrics.COMPLIANCE_ITEM_CHAR_COUNT: 0,
    Metrics.SUMMARY_ITEM_CHAR_COUNT: 0,
    Metrics.UNHANDLED_EXCEPTIONS: "",
    Metrics.HANDLED_EXCEPTIONS: []
}


def get_metrics_id_from_file():
    metrics_id = None
    try:
        with open('./metrics_id', 'r') as metrics_file:
            metrics_id = metrics_file.read()
    except Exception as e:
        pass
    return metrics_id

def threaded_metrics_initialization(snapshot_object, metrics_id):
    try:
        region, instance_id, product, operation = \
            snapshot_object.region, snapshot_object.instance_id, snapshot_object.product, snapshot_object.operation
        global metrics_service
        cognito_client = boto3.client("cognito-identity", region_name=region)
        ephemeral_id, pinpoint_app_id = metrics_id.split("|")

        cognito_credentials = cognito_client.get_credentials_for_identity(IdentityId=ephemeral_id)
        metrics_service['pinpoint_client'] = boto3.client(
            'pinpoint',
            aws_access_key_id=cognito_credentials['Credentials']['AccessKeyId'],
            aws_secret_access_key=cognito_credentials['Credentials']['SecretKey'],
            aws_session_token=cognito_credentials['Credentials']['SessionToken'],
            region_name=region
        )
        sts_client = client_selector.get_default_client(instance_id, region, "sts")
        account_id = sts_client.get_caller_identity()["Account"]
        metrics_service['account_id'] = account_id
        metrics_service['instance_id'] = instance_id
        metrics_service['product'] = product
        metrics_service['operation'] = operation
        metrics_service['pinpoint_app_id'] = pinpoint_app_id
        metrics_service['snapshot'] = snapshot_object
    except Exception as e:
        pass

def try_initialize_metrics_service(snapshot_object):
    metrics_id = get_metrics_id_from_file()
    if metrics_id is None:
        return
    try:
        # start this as a daemon thread so it doesn't block program execution and also doesn't block program exit
        init_worker = threading.Thread(
            target=threaded_metrics_initialization,
            args=(snapshot_object, metrics_id)
        )
        init_worker.daemon = True
        init_worker.start()
        init_worker.join(20)
    except Exception as e:
        pass


def set_runtime_metric(metric, value="true"):
    if metric in patch_runtime_metrics:
        patch_runtime_metrics[metric] = value

def append_runtime_metric(metric, value=None):
    if value == None:
        return
    if metric in patch_runtime_metrics and isinstance(patch_runtime_metrics[metric], list):
        if isinstance(value, list):
            patch_runtime_metrics[metric].extend(value)
        else:
            patch_runtime_metrics[metric].append(value)

def append_runtime_metric_handled_error(value=None):
    return append_runtime_metric(Metrics.HANDLED_EXCEPTIONS, value)

def append_runtime_metric_file_info(message=""):
    try:
        frameinfo = sys._getframe(1)
        file_info = {"filename": frameinfo.f_code.co_filename, "lineno": frameinfo.f_lineno}
        if message != "":
            file_info.update({"message": message})
        append_runtime_metric(Metrics.HANDLED_EXCEPTIONS, file_info)
    except Exception as e:
        pass

def append_runtime_metric_traceback():
    try:
        append_runtime_metric(Metrics.HANDLED_EXCEPTIONS, traceback.extract_tb(sys.exc_info()[2]))
    except Exception as e:
        pass
# metrics are like the console metrics service
# event types are like button clicks in a website, attributes might be url. Metric might just be "click"
# 40 custom endpoint attributes hard limit: user attributes, attributes or metrics
# endpoint attribute value limits: 50
# https://docs.aws.amazon.com/pinpoint/latest/developerguide/quotas.html
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/pinpoint.html#Pinpoint.Client.put_events
def post_metric(metric_value, package_inventory, start_time):
    try:
        if metrics_service['pinpoint_client'] is None or metrics_service['snapshot'] is None:
            return
        exit_code_name = exit_codes_to_meaning[metric_value]
        uses_cpa = "false"
        if metrics_service['snapshot'].install_override_list:
            uses_cpa = "true"

        uses_baseline_override = "false"
        if metrics_service['snapshot'].baseline_override:
            uses_baseline_override = "true"

        aws_baseline_used = "false"
        if metrics_service['snapshot'].patch_baseline.name.startswith("AWS"):
            aws_baseline_used = "true"

        bones_baseline_used = "true"
        if metrics_service['snapshot'].patch_baseline.name.lower().startswith("bones"):
            bones_baseline_used = "true"

        patch_group_used = "false"
        if metrics_service['snapshot'].patch_group:
            patch_group_used = "true"

        package_count_metric_name = "ScanMissingPackageCount"
        package_count_metric = len(package_inventory.missing_pkgs) if package_inventory else 0
        if metrics_service['operation'].lower() == "install":
            package_count_metric_name = "InstalledPackageCount"
            package_count_metric = len(package_inventory.current_installed_pkgs) if package_inventory else 0

        # (datetime.datetime.utcnow() - start_time).total_seconds() python2.7compatible.
        delta = datetime.datetime.utcnow() - start_time
        operation_duration_seconds=(delta.microseconds + (delta.seconds + delta.days * 24 * 3600) * 10**6) / 10**6
        timestamp = datetime.datetime.now().isoformat()
        attributes_dict = {
            "Exit_code": str(metric_value),
            "Product": metrics_service['product'],
            "Snapshot": metrics_service['snapshot'].snapshot_id,
            "InstallOverrideList": uses_cpa,
            "BaselineOverride": uses_baseline_override,
            "RebootOption": metrics_service['snapshot'].reboot_option or "RebootIfNeeded",
            "Region": metrics_service['snapshot'].region,
            "LivePatchEnabled": patch_runtime_metrics[Metrics.KERNEL_LIVE_PATCH_ENABLED],
            "LivePatchCompliant": patch_runtime_metrics[Metrics.KERNEL_LIVE_PATCH_COMPLIANT],
            "UsesAWSProvidedBaseline": aws_baseline_used,
            "UsesBONESProvidedBaseline": bones_baseline_used,
            "HasPatchGroupTag": patch_group_used,
            "UserAccountId": metrics_service['account_id']
        }
        attributes_dict.update(build_attributes("UnhandledExceptions", patch_runtime_metrics[Metrics.UNHANDLED_EXCEPTIONS]))
        attributes_dict.update(build_attributes("HandledExceptions", patch_runtime_metrics[Metrics.HANDLED_EXCEPTIONS]))
        res = metrics_service['pinpoint_client'].put_events(
            ApplicationId=metrics_service['pinpoint_app_id'],
            EventsRequest={
                "BatchItem": {
                    "0": {
                        "Endpoint": {
                            "Address": metrics_service['instance_id'],
                            "ChannelType": "CUSTOM",
                            "Attributes": {
                                "InstanceId": [metrics_service['instance_id']]
                            }
                        },
                        "Events": {
                            "evt1": {
                                "AppPackageName": "PatchBaselineOperations",
                                "AppTitle": metrics_service['product'],
                                "Metrics": {
                                    exit_code_name: 1,
                                    metrics_service['operation'] + '_duration': operation_duration_seconds,
                                    package_count_metric_name:package_count_metric,
                                    "ComplianceItemCharCount": patch_runtime_metrics[Metrics.COMPLIANCE_ITEM_CHAR_COUNT],
                                    "SummaryItemCharCount": patch_runtime_metrics[Metrics.SUMMARY_ITEM_CHAR_COUNT]
                                },
                                "EventType": metrics_service['operation'],
                                "Timestamp": timestamp,
                                "Attributes": attributes_dict
                            }
                        }
                    }
                }
            }
        )
    except Exception as e:
        pass

# metrics attributes value is of type string and has max length of 200
def validate_attribute_value(attribute_value):
    return str(attribute_value)[0:200]

# expand attributes array into attributes dictionary
# max_count specifies the maximum number of attributes allowed
# utility function converting an an array of values into a dictionary
# Pinpoint Limits Spec: https://docs.aws.amazon.com/pinpoint/latest/developerguide/quotas.html#quotas-events
def build_attributes(attribute_name, attribute_values, max_count=10):
    attributes_dict = {}
    if isinstance(attribute_values, list):
        for i in range(min(len(attribute_values), max_count)):
            attributes_dict[str(attribute_name) + str(i+1)] = validate_attribute_value(attribute_values[i])
    elif attribute_values != "":
        attributes_dict[str(attribute_name)] = validate_attribute_value(attribute_values)
    return attributes_dict




def deallocate_metrics_service():
    """
    This method exists because under some kernel and pythonn version combinations the sys.exit call at the end of the
    main_entrance method was generating a segfault. Was observable  on about 60% of runs with ami-0739f8cdb239fe9ae
    in IAD on 03/18/2020
    Ref: https://t.corp.amazon.com/D21572401
    :return:
    """
    global metrics_service
    metrics_service = {
        'pinpoint_client': None,
        'instance_id': None,
        'product': None,
        'operation': None,
        'pinpoint_app_id': None,
        'snapshot': None
    }
