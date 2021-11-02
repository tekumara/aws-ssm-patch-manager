# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import logging
from cli_wrapper.cli_patch_issue import CLIPatchIssue

logger = logging.getLogger()

class CLIPatchIssueParser():
    """
    Class for representing parsing the result of 'zypper lp -a --cve'
    """
    def parse(self, response):
        """
        Constructor for CLICVEPatch object.
        :param - response is a string from zypper command.
        :return - Map: Patch Name -> CLIPatchIssue
        Example:

        Refreshing service 'SUSE_Linux_Enterprise_Server_x86_64'.
        Refreshing service 'Server_Applications_Module_x86_64'.
        Refreshing service 'Web_and_Scripting_Module_x86_64'.
        Loading repository data...
        Reading installed packages...

        The following matches in issue numbers have been found:

        Issue    | No.              | Patch                                                 | Category    | Severity  | Interactive    | Status     | Summary
        ---------+------------------+-------------------------------------------------------+-------------+-----------+----------------+------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        bugzilla | 1014478          | SUSE-SLE-Module-Basesystem-15-SP2-2020-1000           | recommended | moderate  | ---            | not needed | Recommended update for azure-cli tools, python-adal, python-applicationinsights, python-azure modules, python-msrest, python-msrestazure, python-pydocumentdb, python-uamqp, python-vsts-cd-manager
        bugzilla | 1054413          | SUSE-SLE-Module-Basesystem-15-SP2-2020-1000           | recommended | moderate  | ---            | not needed | Recommended update for azure-cli tools, python-adal, python-applicationinsights, python-azure modules, python-msrest, python-msrestazure, python-pydocumentdb, python-uamqp, python-vsts-cd-manager
        bugzilla | 1140565          | SUSE-SLE-Module-Basesystem-15-SP2-2020-1000           | recommended | moderate  | ---            | not needed | Recommended update for azure-cli tools, python-adal, python-applicationinsights, python-azure modules, python-msrest, python-msrestazure, python-pydocumentdb, python-uamqp, python-vsts-cd-manager
        bugzilla | 982804           | SUSE-SLE-Module-Basesystem-15-SP2-2020-1000           | recommended | moderate  | ---            | not needed | Recommended update for azure-cli tools, python-adal, python-applicationinsights, python-azure modules, python-msrest, python-msrestazure, python-pydocumentdb, python-uamqp, python-vsts-cd-manager
        bugzilla | 999200           | SUSE-SLE-Module-Basesystem-15-SP2-2020-1000           | recommended | moderate  | ---            | not needed | Recommended update for azure-cli tools, python-adal, python-applicationinsights, python-azure modules, python-msrest, python-msrestazure, python-pydocumentdb, python-uamqp, python-vsts-cd-manager
        bugzilla | 1166066          | SUSE-SLE-Module-Basesystem-15-SP2-2020-1297           | security    | moderate  | ---            | not needed | Security update for libvpx
        cve      | CVE-2020-0034    | SUSE-SLE-Module-Basesystem-15-SP2-2020-1297           | security    | moderate  | ---            | not needed | Security update for libvpx
        bugzilla | 1082318          | SUSE-SLE-Module-Basesystem-15-SP2-2020-1396           | security    | moderate  | ---            | applied    | Security update for zstd
        """
        name_to_issue_map = {}
        try:
            response_lines = response.split("\n")
            for entry in response_lines:
                issue_fields = entry.split('|')
                if len(issue_fields) >= 3:  # Line may wrap around, all we need is first 3 entries
                    issue_type = issue_fields[0].strip().lower()
                    issue_id = issue_fields[1].strip()
                    patch_name = issue_fields[2].strip()
                    if issue_type == "cve" or issue_type == "bugzilla":
                        self._add_issue_id_to_map(name_to_issue_map, patch_name, issue_type, issue_id)
        except Exception as e:
            logger.exception("Unable to parse CVE Metadata for Patches", e)

        return name_to_issue_map

    def _add_issue_id_to_map(self, name_to_issue_map, patch_name, issue_type, issue_id):
        if patch_name not in name_to_issue_map:
            name_to_issue_map[patch_name] = CLIPatchIssue(patch_name)

        name_to_issue_map[patch_name].add_issue_id_to_patch(issue_type, issue_id)


