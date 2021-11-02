# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import bz2
from datetime import datetime
import glob
import gzip
import shutil
import xml.etree.ElementTree as ET
import logging
import os
from patch_common.cli_invoker import CLIInvoker, CLIInvokerException
from patch_dnf.dnf_package import DnfPackage

logger = logging.getLogger()

UPDATE_INFO_DATE_FORMATS = [ "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H"]


def generate_packages_with_metadata():
    """
    Method for generating a list of packages with corresponding metadata
    """
    update_info_files = _generate_update_info_files()
    for update_info in update_info_files:
        update_notices = _generate_update_notices(update_info)
        for update_notice in update_notices:
            try:
                classification = update_notice.get('type', default="").capitalize()
                issued = update_notice.find('issued')
                issued_date = _convert_date_to_epoch_time(issued.get('date')) if issued is not None else "0"
                severity = getattr(update_notice.find('severity'), 'text', "")
                references = update_notice.findall('references/reference')
                update_notice_ids = _get_advisory_ids(references)
                module = update_notice.find('pkglist/collection/module')
                module_name = None
                module_stream = None
                if module is not None:
                    module_name = module.get('name')
                    module_stream = module.get('stream')
                packages = update_notice.findall('pkglist/collection/package')
                for package in packages:
                    # Filename: python2-wheel-0.30.0-15.module+el8.0.0+4028+a686efca.noarch.rpm
                    name = package.get('name')  # python2-wheel
                    arch = package.get('arch')  # noarch
                    epoch = package.get('epoch')  # 1
                    version = package.get('version')  # 0.30.0
                    release = package.get('release')  # 15.module+el8.0.0+4028+a686efca
                    taxonomy = "{}-{}:{}-{}.{}".format(name, epoch, version, release, arch)
                    available_edition = "{}-{}".format(version, release)
                    yield DnfPackage(
                        taxonomy=taxonomy,
                        name=name,
                        arch=arch,
                        epoch=epoch,
                        available_edition=available_edition,
                        release=release,
                        classification=classification,
                        severity=severity,
                        release_time=issued_date,
                        advisory_ids=update_notice_ids[0],
                        bugzilla_ids=update_notice_ids[1],
                        cve_ids=update_notice_ids[2],
                        module_name=module_name,
                        module_stream=module_stream
                    )
            except:
                logger.warn("Unable to parse Update Notice from provide update_info.xml. For more details, please refer to https://docs.aws.amazon.com/systems-manager/latest/userguide/patch-manager-how-it-works-alt-source-repository.html")


def _generate_update_notices(xml_file):
    """
    Generator function to return update element from a given xml file
    :param xml_file: name of xml file to parse
    :return: Update xml element
    """
    # get an iterable
    context = ET.iterparse(xml_file, events=("start", "end"))
    context = iter(context)
    event, root = next(context)
    for event, elem in context:
        if event == "end" and elem.tag == "update":
            yield elem
            root.clear()


def _generate_update_info_files():
    """
    Generator function to retrieve all update_notice files for given repositories
    Copies zipped files and moves them to temp directory for patching operation
    :return: xml file for each repository
    """
    dnf_cache_folder = "/var/cache/dnf/"
    matching_files = glob.glob(dnf_cache_folder + "*/repodata/*updateinfo*")

    temp_dir = os.getcwd() + "/update_info"
    if not os.path.exists(temp_dir):
        os.mkdir(temp_dir)

    for idx, file_name in enumerate(matching_files):
        file_name, openfile = _get_file_open_mode(file_name)
        if openfile is None:
            continue

        with openfile(file_name, 'rb') as f_in:
            xml_file = "%s/update_info_%s.xml" % (temp_dir, idx)
            with open(xml_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        yield xml_file
        os.remove(xml_file)

    os.rmdir(temp_dir)


def _convert_date_to_epoch_time(issued_date):
    """
    Function to convert string date to epoch time
    :param issued_date: datetime string from xml metadata
    :return: String with date converted to epoch time
    """

    for date_format in UPDATE_INFO_DATE_FORMATS:
        try:
            parsed_issued_date = datetime.strptime(issued_date, date_format)
            issued_date_epoch_time = (parsed_issued_date - datetime(1970, 1, 1)).total_seconds()
            return str(int(issued_date_epoch_time))
        except ValueError:
            pass

    logger.warn("Repository contains unsupported date format %s. Defaulting to 01/01/1970", issued_date)
    return "0"


def _get_advisory_ids(references):
    """
    Function to parse Reference xml object and return all update notice ids
    :param references: References xml object
    :return: tuple with (Advisory Ids, Bugzilla Ids, CVE Ids)
    """
    advisory_ids = set()
    bugzilla_ids = set()
    cve_ids = set()
    for reference in references:
        adv_type = reference.get('type')
        adv_id = reference.get('id')
        if adv_type == 'self':
            advisory_ids.add(adv_id)
        elif adv_type == 'bugzilla':
            bugzilla_ids.add(adv_id)
        elif adv_type == 'cve':
            cve_ids.add(adv_id)
    return advisory_ids, bugzilla_ids, cve_ids


def _get_file_open_mode(file_name):
    """
    Function to get what type of library to use for file type
    :param file_name
    :return: file opening method
    """
    openfile = None
    if file_name.endswith('.bz2'):
        openfile = bz2.BZ2File
    elif file_name.endswith('.gz'):
        openfile = gzip.open
    elif file_name.endswith('.xz'):
        try:
            CLIInvoker(comd=['unxz', file_name]).execute()
        except CLIInvokerException as e:
            logger.warn("Unable to decompress updateinfo.xml file: %s", file_name)
        openfile = open
        file_name = file_name.replace('.xz', '')
    elif file_name.endswith('.xml'):
        openfile = open
    else:
        logger.warn("Unsupported updateinfo file format: %s", file_name)

    return file_name, openfile
