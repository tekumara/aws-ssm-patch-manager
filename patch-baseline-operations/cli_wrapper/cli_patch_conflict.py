# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.

from patch_zypp_cli import zypp_shared_operation_methods as shared

class CLIPatchConflict(object):

  """
  Class for representing a patch conflict from the 'zypper info --type patch <patch_name>' command
  """
  def __init__(self, name, arch, edition, release_time, classification, severity):
    """
    Constructor for patch conflict.
    :param name is the name of the conflict.
    :param arch is the architecture of the conflict.
    :param edition is the edition of the conflict.
    :param classification is the classification of the patch this conflict was found on. 
    :param severity is the severity of the patch this conflict was found on. 
    :param patch_release_time is the time the patch notification came out. 
    """
    self.name = name
    self.arch = arch
    self.edition = edition
    self.patch_release_time = release_time if release_time else '0'
    self.classification = classification if classification else ''
    self.severity = severity if severity else ''
    self.bugzilla_ids = set()
    self.cve_ids = set()

    if self.edition:
      self.available_version = shared.parse_version_from_edition(self.edition)
      self.release = shared.parse_release_from_edition(self.edition)
  
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
  def patch_release_time(self):
    """
    Method for returning the patch_release_time.
    """
    return self.__patch_release_time

  @patch_release_time.setter
  def patch_release_time(self, patch_release_time):
    """
    Method for setting the patch_release_time
    :param patch_release_time as a string.
    """
    self.__patch_release_time = patch_release_time

  @property
  def release(self):
    """
    Method for getting the release.
    Release is the second half of a package edition. 
    If a package is edition: 4.3.1-2.0.1, the edition is 4.3.1-2.0.1, the version is 4.3.1 and the release is 2.0.1
    """
    return self.__release

  @release.setter
  def release(self, release_value):
    """
    Method setting the release
    :param release_value is the package release to set.
    Release is the second half of a package edition. 
    If a package is edition: 4.3.1-2.0.1, the edition is 4.3.1-2.0.1, the version is 4.3.1 and the release is 2.0.1
    """
    self.__release = release_value

  @property
  def available_version(self):
    """
    Method for returning the version of the package.
    """
    return self.__available_version

  @available_version.setter
  def available_version(self, vrs):
    """
    Method for setting the release of the package.
    """
    self.__available_version = vrs

  @property
  def edition(self):
    """
    Method for gettign the edition of the object.
    """
    return self.__edition

  @edition.setter
  def edition(self, ed):
    """
    Method fo rsetting the edition of the conflict.
    """
    self.__edition = ed

  @property
  def arch(self):
    """
    Method for returning the architecture (x86_64)
    """
    return self.__arch

  @arch.setter
  def arch(self, arch):
    """
    Method for setting the architecture (x86_64)
    :param arch is the architecture to set.
    """
    self.__arch = arch

  @property
  def name(self):
    """
    Method for getting the name of the package.
    """
    return self.__name

  @name.setter
  def name(self, name):
    """
    Method for setting the name of the package.
    :param name is the name to set the name to.
    """
    self.__name = name

  @property
  def bugzilla_ids(self):
    """
    Method for getting a set of bugzilla ids of the package
    """
    return self.__bugzilla_ids

  @bugzilla_ids.setter
  def bugzilla_ids(self, bugzilla_ids):
    """
    Method for setting the bugzilla ids of the package
    :param bugzilla_ids: the set of bugzilla ids of the package
    """
    self.__bugzilla_ids = bugzilla_ids

  @property
  def cve_ids(self):
    """
    Method for getting a set of cve ids of the package
    """
    return self.__cve_ids

  @cve_ids.setter
  def cve_ids(self, cve_ids):
    """
    Method for setting the cve ids of the package
    :param cve_ids: the set of cve ids of the package
    """
    self.__cve_ids = cve_ids

