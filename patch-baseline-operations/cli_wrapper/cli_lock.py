# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
from xml.etree.ElementTree import Element
import xml.etree.ElementTree as ET
from cli_wrapper.kind_enum import Package
from cli_wrapper.kind_enum import Patch
from cli_wrapper.kind_enum import Repository

class CLILock(object):
  """
  Class for representing a CLI Lock
  """
  def __init__(self, xml_element):
    """
    Constructor for lock object.
    :param - xml_element is an xml.etree.ELementTree.Element object.
    Example: 
        <lock number="2"><name>SUSE-SLE-Module-Basesystem-15-2018-1663</name><type>patch</type></lock>
    """
    if not isinstance(xml_element, Element):
      raise TypeError("CLILock parameter xml_element must be type xml.etree.ElementTree.Element")

    self.name = xml_element.find('name').text
    self.lock_type= xml_element.find('type').text

  @property
  def name(self):
    """
    Method for returning the name of the package.
    """
    return self.__name

  @name.setter
  def name(self, name):
    """
    Method for setting the name of the package.
    """
    self.__name = name
  
  @property
  def lock_type(self):
    """
    Method for getting the lock type.
    """
    if self.__lock_type == "package":
      return Package
    elif self.__lock_type == "patch":
      return Patch
    elif self.__lock_type == "repository":
      return Repository
    else:
      raise Exception("Unknown patch lock type %s"%(self.__lock_type))

  @lock_type.setter
  def lock_type(self, tpe):
    """
    Method for setting the type.
    :param tpe - is the type of the of element in the lock (ie, package, patch, pattern, etc...)
    """
    self.__lock_type = tpe





