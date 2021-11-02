# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.


class CLIPatchIssue(object):
    """
    Class to represent Patch Issue information for a given Patch object
    """
    def __init__(self, name, cve_ids=None, bugzilla_ids=None):
        """
        :param name: Name of Patch
        :param cve_ids: Set of CVE Ids applicable to the Patch
        :param bugzilla_ids: Set of Bugzilla Ids applicable to the Patch
        """
        self.name = name
        if cve_ids is None:
            self.cve_ids = set()
        if bugzilla_ids is None:
            self.bugzilla_ids = set()

    def add_issue_id_to_patch(self, issue_type, issue_id):
        """
        Method to add an issue id to the correct issue type set
        :param type: either "cve" or "bugzilla"
        :param issue_id:
        :return:
        """
        issue_type = issue_type.strip().lower()
        if issue_type == "cve":
            self.cve_ids.add(issue_id)
        elif issue_type == "bugzilla":
            self.bugzilla_ids.add(issue_id)
