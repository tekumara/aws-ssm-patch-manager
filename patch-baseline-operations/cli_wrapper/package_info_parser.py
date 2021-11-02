# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import re
import subprocess
from subprocess import check_output
from cli_wrapper.cli_package_bean import CLIPackageBean
from xml.etree.ElementTree import Element

class PackageInfoParser():
  """
  Parser for the 'zypper info --type package <package_name>' command.
  """
  def parse(self, response):
    """
    Method for parsing a string representing a response from the 'zypper info --type package <package_name>' command. 
    :param - response is a string response from an info command. 
    :return an xml element containing everything needed to initialize
    a cli_package object.
    Example reponse param:
            Information for package yast2-tune:
            -----------------------------------
            Repository     : SLE-Module-Basesystem15-Updates           
            Name           : yast2-tune                                
            Version        : 4.0.1-3.3.1                               
            Arch           : x86_64                                    
            Vendor         : SUSE LLC <https://www.suse.com/>          
            Support Level  : Level 3                                   
            Installed Size : 142.1 KiB                                 
            Installed      : Yes                                       
            Status         : out-of-date (version 4.0.0-1.57 installed)
            Source package : yast2-tune-4.0.1-3.3.1.src                
            Summary        : YaST2 - Hardware Tuning                   
            Description    :                                           
                This package contains the YaST2 component for hardware configuration.
    
        self.xml_element = xml_element
    """
    attributes_to_grab = { 
      "name" : r'name\s*:', 
      "edition" : r'version\s*:',
      "installed" : r'installed\s*:',
      "arch" : r'arch\s*:',
      "status" : r'status\s*:'}

    try:
      # In case more than one package info was returned.
      packages = re.split(r'information for package.*:', response, flags=re.IGNORECASE)

      # because this is a split, 
      # the string before the first occurence of 'information for package' is junk.
      packages.pop(0) 

      cli_packages = []
      for package in packages:
        element = self.__get_xml_element_with_attributes(package, attributes_to_grab)

        # Never create a package that did not have a name
        if element.get('name'):  
          cli_packages.append(CLIPackageBean(xml_element = element))

      return cli_packages

    except Exception as e:
      raise Exception("Failed to parse response from 'zypper info --type package <package_name>' command. Response: %s"%(response), e)
    

  def __get_xml_element_with_attributes(self, response, attributes_to_grab):
    """
    Method for creating an instance with the attributes_to_grab assigned to it. 
    return: object instance with found attributes.
    """
    try:
      new_element = Element("")
      new_element.set("kind", "package")
      for line in response.splitlines():
        if line.strip():
          for attribute in attributes_to_grab:
            if re.match(attributes_to_grab[attribute], line.lower().strip()):
              new_element = self.__set_element(attribute, new_element, line)
              if(attribute == "edition"):
                new_element = self.__parse_version_from_edition(new_element)
      return new_element
    except Exception as e:
      raise Exception("Unable to get attributes from patch object.", e)

  def __set_element(self, key, element, line):
    """
    Method for setting an element key from an identified value in the info object.
    :param key - is the key to set in the element object.
    :param element - the element object to return.
    :param line - is the line that has the value of the key.
    """
    try:
      line_array = line.split(":",1)
      element.set(key, line_array[1].strip())
      
      return element

    except Exception as e:
      raise Exception("Error setting element %s for 'zypper info --type package' command."%(key), e)
  
  def __parse_version_from_edition(self, element):
    """
    Method for getting the version from edition. For example, the edition is "3.4.1-5.2.1" and the version is "3.4.1"
    """
    edition = element.get("edition")
    if edition:
      version = edition.split("-", 1)[0]
      if version:
        element.set("version" , version.strip())
    return element