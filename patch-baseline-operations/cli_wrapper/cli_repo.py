# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
from xml.etree.ElementTree import Element

class CLIRepo():
    """
    Class for representing Zypp Repository.
    """
    def __init__(self, xml_element):
        """
        Constructor for Zypp Repos.
        :param - xml_element is an xml.etree.ELementTree.Element object.
        Example: <repo alias="Web_and_Scripting_Module_x86_64:SLE-Module-Web-Scripting15-SP2-Updates" 
                name="SLE-Module-Web-Scripting15-SP2-Updates" 
                type="rpm-md" priority="99" 
                enabled="1" 
                autorefresh="1" 
                gpgcheck="1" 
                repo_gpgcheck="1" 
                pkg_gpgcheck="0">
                <url>plugin:/susecloud?credentials=Web_and_Scripting_Module_x86_64&amp;path=/repo/SUSE/Updates/SLE-Module-Web-Scripting/15-SP2/x86_64/update/</url>
                </repo>
        """
        if not isinstance(xml_element, Element):
            raise TypeError("CLIRepo parameter xml_element must be type xml.etree.ElementTree.Element")

        self.__enabled = xml_element.get('enabled') == "1"
        self.__name = name = xml_element.get('name')

    @property
    def enabled(self):
        """
        Method for returning a boolean representing whether the repo is enabled.
        """
        return self.__enabled

    @property
    def name(self):
        """
        Method for returning the repo's name.
        """
        return self.__name

    