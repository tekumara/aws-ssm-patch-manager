import gzip
import json
import logging
import os
import contextlib

from patch_common.constant_repository import ExitCodes
from patch_common.exceptions import PatchManagerError
from patch_common.shell_interaction import download_from_url

logger = logging.getLogger()

def download_snapshot(url, filename="patch_snapshot_download_data"):
    _clean_previous_download_data(filename)
    try:
        download_from_url(url, filename)
        snapshot = _try_unpack(filename)
        if(snapshot is not None):
            return snapshot
        else:
            error_message = "Invalid Snapshot fetched from s3"
            logger.exception(error_message)
            raise PatchManagerError(error_message, ExitCodes.SNAPSHOT_INVALID)
    except Exception as e:
        error_message = "Could not download a valid snapshot"
        logger.exception(error_message)
        raise PatchManagerError(error_message, ExitCodes.SNAPSHOT_ERROR, e)

def _clean_previous_download_data(filename):
    try:
        os.remove(filename)
    except OSError:
        # no leftover file found
        pass

def _try_unpack(filename):
    snapshot = _unpack_as_text_file(filename)
    if(snapshot is None):
        logger.info("Unable to parse snapshot as text. Trying decompression.")
        snapshot = _unpack_as_gzipped_file(filename)
    return snapshot

def _unpack_as_text_file(filename):
    with open(filename, 'r') as f:
        return _unpack_as_text(f)

def _unpack_as_gzipped_file(filename):
    try:
        with contextlib.closing(gzip.open(filename, 'rb')) as f:
            return _unpack_as_text(f)
    except IOError as e:
        logger.info("Unable to decompress file as gzip")

def _unpack_as_text(file):
    try:
        contents = file.read()
        if not type(contents) == str:
            contents = contents.decode("utf-8")
        contents = contents.strip()
        snapshot = json.loads(contents)
        if(_is_valid_snapshot(snapshot)):
            return snapshot
    except (KeyError, ValueError) as e:
        pass
    return None

def _is_valid_snapshot(snapshot):
    return snapshot["patchBaseline"] is not None
