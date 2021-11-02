# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import sys
sys.path.append("..") 
import re
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element
import subprocess
from cli_wrapper.cli_patch_conflict import CLIPatchConflict
from cli_wrapper.cli_patch_bean import CLIPatchBean

class PatchInfoParser():
  """
  Parser for the 'zypper info --type patch <patch_name>' command.
  """
  def parse(self, response):
    """
    Method for parsing the output of a 'zypper info --type patch <patch_name>' command.
    :param - response is the CLI output from the command as a string.
    :return - a list of CLIPatchBean objects with their packages (if any).         
    """
    try:
      attributes_to_grab = { 
        "name" : r'name\s*:', 
        "version": r'version\s*:',
        "status" : r'status\s*:', 
        "category" : r'category\s*:', 
        "severity" : r'severity\s*:', 
        "created" : r'created\s* on\s*:'}

      # In case more than one patches info was returned.
      patches = re.split(r'information for patch.*:', response, flags=re.IGNORECASE)
      # because this is a split, 
      # the string before the first occurence of 'information for patch' is junk.
      patches.pop(0) 

      patch_beans = []
      for patch in patches:
        instance = self.__get_object_instance_with_attributes(patch, attributes_to_grab)
        # Never create a patch that does not have a name.
        if hasattr(instance,"name"):
          patch_beans.append(self.__create_patch_bean(instance))
      return patch_beans
    except Exception as e:
      raise Exception("Failed to parse response from zypper info --type patch <patch_name> command. Response: %s"%(response), e)
  
  def __get_object_instance_with_attributes(self, response, attributes_to_grab):
    """
    Method for creating an instance with the attributes_to_grab assigned to it. 
    return: object instance with found attributes.
    """
    try:
      instance = lambda: None
      for line in response.splitlines():
        # If line is not blank.
        if line.strip():
          for attribute in attributes_to_grab:
            if re.match(attributes_to_grab[attribute] , line.lower().strip()):
              setattr(instance, attribute, line.split(":",1)[1].strip())
            elif re.match( r'conflicts\s*', line.lower().strip(), flags=re.IGNORECASE):
              setattr(instance, "conflicts", self.__get_conflicts(response[response.index(line):], instance))
      return instance
    except Exception as e:
      raise Exception("Unable to get attributes from patch object.", e)

  def __create_patch_bean(self, instance):
    """
    Method for converting a generic instance with known attributes to a CLIPatchBean object.
    :param instance - the instance holding the found attributes.
    :return CLIPatchBean object
    """
    return CLIPatchBean( 
      name=instance.name, 
      classification=instance.category if hasattr(instance, 'category') else "", 
      severity=instance.severity if hasattr(instance, 'severity') else "", 
      conflicts=instance.conflicts if hasattr(instance, 'conflicts') else None
    )
    
  def __get_conflicts(self, response, instance):
    """
    Method for returning a list of conflicts from the response. 
    :param response is a string response from the 'zypper info --type patch <patch_name>' command.
    :param instance is a python instance with all known attributes of the patch on it. 
    :return a list of conflicts. 
    """
    lines = response.splitlines()
    conflicts = []
    if lines:
      for index, line in enumerate(lines):
        # if it is a conflict
        if re.match( r'(.+)(\s*)<(\s*)(.+)', line.strip()):
          conflicts.append(self.__create_cli_patch_conflict(line.strip(), instance))

    return conflicts

  def __create_cli_patch_conflict(self, conflict_name, instance):
    """
    Method for parsing a conflict name into a CLIPatchConflict object.
    :param - conflict_name is a package string like evince-plugin-xpsdocument.x86_64 < 3.20.1-6.16.1
    :param - instance is a python instance with all known attributes of the patch on it. 
    :return a CLIPatchConflict object.
    """
    # This splits the conflict name in to parts of a tuple.
    # For example, this name evince-plugin-xpsdocument.x86_64 < 3.20.1-6.16.1
    # becomes:
    # pair[0] = evince-plugin-xpsdocument.x86_64
    # pair[1] = 3.20.1-6.16.1
    pair = conflict_name.strip().split()

    # This creates a tuple object that looks like this:
    #   name_arch[0] = python-pycrypto
    #   name_arch[1] = i586
    # However, sometimes there is only a name specified and no architecture. 
    # In this case we default to 'noarch'
    name_arch = pair[0].rsplit(".", 1)

    if len(name_arch) == 1:
      name_arch.append('noarch')

    created_on = instance.created if hasattr(instance, 'created') else ""
    classif = instance.category if hasattr(instance, 'category') else ""
    sev = instance.severity if hasattr(instance, 'severity') else ""
    
    return CLIPatchConflict(name=name_arch[0].strip(), arch=name_arch[1].strip(), edition=pair[2], release_time=created_on, classification=classif, severity=sev)

    