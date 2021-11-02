
from patch_common import baseline
from patch_common.constant_repository import Snapshot_keys

class Snapshot:

    def __init__(self, snapshot):

        self.instance_id = snapshot[Snapshot_keys.INSTANCE_ID]
        self.operation = snapshot[Snapshot_keys.OPERATION]
        self.patch_baseline = baseline.Baseline(snapshot[Snapshot_keys.PATCH_BASELINE])
        self.patch_baseline_dict = snapshot[Snapshot_keys.PATCH_BASELINE]
        self.patch_group = snapshot[Snapshot_keys.PATCH_GROUP]
        self.product = snapshot[Snapshot_keys.PRODUCT]
        self.region = snapshot[Snapshot_keys.REGION]
        self.snapshot_id = snapshot[Snapshot_keys.SNAPSHOT_ID]
        self.install_override_list = snapshot.get(Snapshot_keys.INSTALL_OVERRIDE_LIST)
        self.baseline_override = snapshot.get(Snapshot_keys.BASELINE_OVERRIDE)
        self.reboot_option = snapshot.get(Snapshot_keys.REBOOT_OPTION)