# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
from cli_wrapper.cli_package_bean import CLIPackageBean

class CLIPatchBean(object):
  """
  Class for representing a patch object returned from the CLI.
  """
  def __init__(self, name, classification, severity, conflicts=[]):
    """
    Constructor for patch object.
    :param - name is the name of the patch bean. 
    :param - classification is the classification of the patch.
    :param - severity is the severity of the patch. 
    :param conflicts is the list of packages that are needed to satisfy the patch.
    """
    self.classification = classification
    self.severity = severity
    self.name = name
    self.conflicts = conflicts

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
  def classification(self):
    """
    Method for returning the classification
    """
    return self.__classification

  @classification.setter
  def classification(self, classification):
    """
    Method for setting the classification
    """
    self.__classification = classification

  @property
  def severity(self):
    """
    Method for returning the severity.
    """
    return self.__severity

  @severity.setter
  def severity(self, severity):
    """
    Method for setting the severity
    """
    self.__severity = severity

  @property
  def conflicts(self):
    """
      Method for getting the packages that are required for this patch to be considered 'installed'.
      :return a list of CLIPatchConflicts
    """ 
    return self.__conflicts

  @conflicts.setter
  def conflicts(self, cnflcts):
    """
      Method for getting the packages that are required for this patch to be considered 'installed'.
      :param cnflcts is the list of CLIPatchConflicts to set it to.
      :return a list of CLIPatchConflicts
    """ 
    self.__conflicts = cnflcts

