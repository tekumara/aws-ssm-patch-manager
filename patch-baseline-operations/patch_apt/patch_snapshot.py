# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
from patch_common import baseline

SOURCES = 'sources'


class PatchSnapshot:
    """
    Class for the patch snapshot.
    """
    def __init__(self, patch_snapshot):
        """
        Constructor for the class.
        :param patch_snapshot: to obtain keys from.
        """

        self.instance_id = patch_snapshot.instance_id
        self.operation = patch_snapshot.operation
        self.patch_baseline = patch_snapshot.patch_baseline
        self.patch_group = patch_snapshot.patch_group
        self.product = patch_snapshot.product
        self.region = patch_snapshot.region
        self.snapshot_id = patch_snapshot.snapshot_id
        self.install_override_list = patch_snapshot.install_override_list
        self.reboot_option = patch_snapshot.reboot_option

        # Baseline Fields TODO: use Baseline Class defined in Common package
        self.patch_baseline_id = self.patch_baseline.baseline_id
        self.rejected_patches = self.patch_baseline.exclude
        self.rejected_patches_action = self.patch_baseline.rejected_patches_action
        self.approved_patches = self.patch_baseline.include
        self.approved_patches_compliance_level = self.patch_baseline.includeComplianceLevel
        self.approved_patches_enable_non_security = self.patch_baseline.approved_patches_enable_non_security

    @property
    def has_rejected_patches(self):
        return bool(self.rejected_patches)


    @property
    def block_rejected_patches(self):
        return self.rejected_patches_action is not None and self.rejected_patches_action.lower() == "block"


    def get_custom_repository_configuration(self):
        """
        Gets the custom repository configuration.
        :return: string of the configuration.
        """
        configuration = None
        for source in self.patch_baseline.sources:
            source_name = source['name']
            source_products = source['products']
            source_configuration = source['configuration']

            if (self.product in source_products) or ("*" in source_products):
                logging.info("Found source name: %s", source_name)
                if configuration is None:
                    configuration = source_configuration
                else:
                    configuration = "\n".join([configuration, source_configuration])

        # If the product was missing from the sources
        # then the customer potentially configured their sources incorrectly.
        # Fail the command.
        if self.patch_baseline.sources and configuration is None:
            error_message = "No sources contained the product: %s. " \
                            "Add the product to a source to use the custom repository configuration" % self.product
            logging.error(error_message)
            logging.error("Failing the command.")
            raise Exception(error_message)

        return configuration

    @property
    def global_filter(self):
        return self._create_aggregate_filter(self.patch_baseline.global_filters.filters)

    @property
    def approval_rules(self):
        approval_rules = []

        for approval_rule in self.patch_baseline.approval_rules.rules:
            enable_non_security_updates = approval_rule.enable_non_security or False
            compliance_level = approval_rule.compliance
            aggregate_filter = self._create_aggregate_filter(approval_rule.filter_group.filters)

            approval_rules.append(ApprovalRule(enable_non_security_updates, compliance_level, aggregate_filter))

        return approval_rules

    @staticmethod
    def _create_aggregate_filter(filters):
        """
        Convert a list of filters:
        "filters": [ { "key": "TheKey",  "values": [ "TheValues" ... ] }  .... ]
        into an aggregate filter and lowercase the values:
        "aggregate_filter": { "TheKey" : [ "thevalues" ... ] ... }
        :param filters: to convert to aggregate filters.
        :return: the aggregate filter.
        """
        aggregate_filter = {}

        for single_filter in filters:
            aggregate_filter[single_filter.key] = [x.lower() for x in
                                                      single_filter.values]  # Service can't be trusted with case
        return aggregate_filter


class ApprovalRule:
    def __init__(self, enable_non_security_updates, compliance_level, aggregate_filter):
        self.enable_non_security_updates = enable_non_security_updates
        self.compliance_level = compliance_level
        self.aggregate_filter = aggregate_filter

