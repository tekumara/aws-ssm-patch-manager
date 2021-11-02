import logging

from patch_common.constant_repository import InstallOverrideList_keys
from patch_common.downloader import download_file, load_yaml_file, is_access_denied

logger = logging.getLogger()

class Patch:
    def __init__(self, patch):
        self.id = patch.get(InstallOverrideList_keys.ID)
        self.title = patch.get(InstallOverrideList_keys.TITLE)
        if self.id is None:
            raise Exception("Must provide an id for each patch")

    def _get_all_filters(self):
        if self.title is not None:
            return [ self.id, self.title ]
        else:
            return self.id

class InstallOverrideList:
    def __init__(self, override_list):
        if type(override_list) is dict:
            logging.info("The content of install override list is: %s", override_list)

            self.patches = override_list.get(InstallOverrideList_keys.PATCHES)
            self.all_filters = []
            self.id_filters = []

            if self.patches and len(self.patches) > 0:
                for p in self.patches:
                    patch = Patch(p)
                    self.all_filters.append(patch._get_all_filters())
                    self.id_filters.append(patch.id)
            else:
                logging.warn("There are no patches specified in the provided override list file.")
        else:
            raise Exception("The content of the provided InstallOverrideList is invalid.")

    @staticmethod
    def load(snapshot_object):
        override_list_path = snapshot_object.install_override_list
        region = snapshot_object.region

        # Only download the override list when it's provided for install operation
        if override_list_path is not None and len(override_list_path) > 0 and snapshot_object.operation.lower() == "install":
            file_name = "install_override_list.yaml"

            logger.info("Downloading InstallOverrideList from: %s.", override_list_path)
            if download_file(override_list_path, file_name, region):
                content = load_yaml_file(file_name)

                if is_access_denied(content):
                    logger.error("Found access denied error: %s when downloading InstallOverrideList", content)
                    raise Exception("Access denied to provided InstallOverrideList: " + override_list_path)
                else:
                    return InstallOverrideList(content)
