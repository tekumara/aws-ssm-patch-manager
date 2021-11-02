# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element


class XMLParser():
  """
  Parser for parsing pure xml output. 
  """
  def __init__(self, inst_type, element_to_retrieve):
    """
    Initialization method for providing the type of object to be returned.
    :param inst_type is the .__class__ attribute on the object being returned from the parse() method.
    :param element_to_retrieve is the string name of the xml element to look for from the output.
    """
    self.element_to_retrieve = element_to_retrieve
    self.instance_type = inst_type
    
  def parse(self, response):
    """
    Method for parsing Zypp xml output.
    :param - response is the CLI output from a command as xml string or xml.etree.ElementTree.Element.
    :return - list of object instances of type self.instance_type
    """
    root = self.__convert_to_xml(response)
    if root is None:
      raise TypeError("Invalid xml element type %s "%(type(response))) 

    try:
      elements = root.iter(self.element_to_retrieve)
      list_of_instances = []

      for element in elements:
        list_of_instances.append(self.instance_type(element))
      return list_of_instances
    except Exception as e:
      raise Exception("XML element from list failed to parse: %s"%(elements), e)

  def __convert_to_xml(self, response):
    """
    Method for validating that the response type is correct and assigning it to class instance.
    :param - response object to parse as a string or ElementTree.
    :return - response object as an xml.etree.ElementTree or None if it is the wrong type (not a string of ElementTree)
    """
    if isinstance(response, str):
      return ET.fromstring(response)
    elif isinstance(response, Element):
      return response
    else:
      return None
    