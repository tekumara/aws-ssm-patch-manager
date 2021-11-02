# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import os
import sys
from patch_common.xml_parser import XMLParser
from patch_common.cli_invoker import CLIInvoker
from patch_common.cli_invoker_error import CLIInvokerError
from cli_wrapper.cli_patch_issue_parser import CLIPatchIssueParser
from cli_wrapper.cli_patch_bean import CLIPatchBean
from cli_wrapper.cli_lock import CLILock
from cli_wrapper.cli_solvable import CLISolvable
from cli_wrapper.cli_repo import CLIRepo
from cli_wrapper.package_info_parser import PackageInfoParser
from cli_wrapper.patch_info_parser import PatchInfoParser

class ZypperCLI:
  """
  This class is a direct 1:to:1 relationship with the zypper cli. The commands are the same as the zypper cli. 
  For example, calling zypper_lu_type_patch() is the equivalent of 'zypper lu --type patch'
  """

  def __init__(self):
    # Set the LC_ALL env variable to the C locale to prevent issues parsing with the CLISolvable class due to language setting changes
    os.environ['LC_ALL'] = 'C'

  def commit(self):
    """
    Method for committing a list of packages to be upgraded. Fails on conflicts. 
    This command takes a list_of_packages that can be just the name, the name.arch or the name.arch[OP][Edition]. For example, 'nano.x86_64>=2.3.3-3.3'
    e.g. commit().execute(['curl', 'libcurl'])
    :return - CLIInvoker - ("result string", return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper','--non-interactive','update'])

  def zypper_list_repos(self):
    return CLIInvoker(\
                        comd=['zypper', '--xmlout', 'lr'],\
                        psr=XMLParser(CLIRepo, 'repo'))

  def zypper_info_package(self):
    """
    Method for getting information about a package object.
    This command takes a list of package_names to get info for. 
    e.g. zypper_info_package().execute(['curl', 'libcurl'])
    The executable of this command is zypper. The reason we open the Zypper shell to execute the command versus using bash is execution speed.
    Bash takes ~ 5 seconds per package name and the zypper shell takes ~ 5 seconds for 1200-1500 package names. There can be over 1000 package names
    on vanilla instances. 
    :return - CLIInvoker - ("response string", return_code)
    """
    return CLIInvoker(\
                        comd = ['shell','info','-t','package'], \
                        psr = PackageInfoParser(), \
                        executable = "zypper", \
                        print_output = False)
  
  def zypper_info_type_patch(self):
    """
    Method for calling 'zypper info --type patch <patch_name> <patch_name> ...' on a list of patches.
    This command takes a list of patch names to get info for.
    e.g. zypper_info_type_patch().execute(['PATCH1','PATCH2'])
    The executable of this command is zypper. The reason we open the Zypper shell to execute the command versus using bash is execution speed.
    Bash takes ~ 5 seconds per patch name and the zypper shell takes ~ 5 seconds for 1200-1500 patch names. There can be over 1000 patch names
    on vanilla instances. 
    :return - CLIInvoker - (List<CLIPatchBean>, return_code)
    """
    return CLIInvoker(\
                        comd = ['shell','info','-t','patch'],
                        psr = PatchInfoParser(),
                        executable = "zypper",
                        print_output = False)

  def zypper_list_patch_issues(self):
    """
    Method for calling 'zypper --xmlout lp -a --cve --bugzilla'
    Retrieves a list of CVEs which are resolved by a corresponding Patch
    :return - CLIInvoker - (response_text, return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper', 'lp', '-a', '--cve', '--bugzilla'],
                        psr = CLIPatchIssueParser(),
                        print_output = False)

  def zypper_removelock(self):
    """
    Method for removing package locks. 
    This command takes a list of package names to unlock.
    e.g. zypper_removelock().execute(['curl'])
    :return - CLIInvoker - (response_text, return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper', 'removelock'])

  def zypper_locks(self):
    """
    Method for getting the list of locked objects
    :return - CLIInvoker - (List<CLILock>, return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper','--xmlout','locks'],
                        psr = XMLParser(CLILock, 'lock'))

  def zypper_refresh(self):
    """
    Method for refreshing the zypper repositories. 
    :return - CLIInvoker - (response_text, return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper','refresh'])

  def zypper_addlock(self):
    """
    Method for adding locks to packages to prevent installs or upgrades.
    This command takes a list of package names to lock.
    e.g. zypper_addlock().execute(['curl', 'libcurl'])
    :return - CLIInvoker - (response_text, return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper', 'addlock'])

  def rpm_q_qf_version(self):
    """
    Gets the current installed verison of a package in format.
    This command takes a list of package names to get the edition information for.
    e.g. rpm_q_qf_version().execute(['curl','libcurl'])
    :return - CLIInvoker - (response_text, return_code)
    """
    return CLIInvoker(\
                        comd = ['rpm','-q','--qf', "%{VERSION}-%{RELEASE}\n"],
                        print_output = False)
  
  def rpm_q_qf_installedtime(self):
    """
    Gets the date a package was installed in format 'Mon Dec 10 16:13:09 2018'
    This command takes a list of package names to get the installedtime information for.
    e.g. rpm_q_qf_version().execute(['curl','libcurl'])
    :return - CLIInvoker  - (response_text, return_code)
    """
    return CLIInvoker(\
                        comd = ['rpm', '-q','--qf', "%{INSTALLTIME}\n" ],
                        print_output = False)

  def zypper_se_type_package_installed_only(self):
    """
    Method for calling 'zypper se --type package --installed-only'
    :return - CLIInvoker - (List<CLISolvables> , return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper', '--xmlout', 'se','-s','--type','package','--installed-only'],
                        psr = XMLParser(CLISolvable, 'solvable'),
                        errors = [
                                    CLIInvokerError(error_code = 104, error_message = "Subprocess returned error code 104. \
                                    No packages were found. Ignoring error and continuing. ")
                                 ]
                        )
  
  def zypper_se_type_package_uninstalled_only(self):
    """
    Method for calling 'zypper se --type package --uninstalled-only'
    :return - CLIInvoker - (List<CLISolvables>, return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper', '--xmlout', 'se','-s','--type','package','--uninstalled-only'],
                        psr = XMLParser(CLISolvable, 'solvable'),
                        errors = [
                                    CLIInvokerError(error_code = 104, error_message = "Subprocess returned error code 104. \
                                    No packages were found. Ignoring error and continuing. ")
                                 ]
                      )

  def zypper_search_type_package(self):
    """
    Get's all available solvables of type package. This includes the same package but multiple times as separate solvables
    for different versions.
    :return - CLIInvoker - List<CLISolvable> of kind=package. There may be duplicates in names with different versions.
    """
    return CLIInvoker(\
                        comd = ['zypper', '--xmlout', 'search', '-s', '--type', 'package'],
                        psr = XMLParser(CLISolvable, 'solvable'),
                        errors = [
                                    CLIInvokerError(error_code = 104, error_message = "Subprocess returned error code 104. \
                                    No packages were found. Ignoring error and continuing. ")
                                 ]
                        )

  def rpm_q_qf_release(self):
    """
    Gets the current installed release of a package in format.
    This command takes a list of package names to get the installedtime information for.
    e.g. rpm_q_qf_release().execute(['curl','libcurl'])
    :return - CLIInvoker - (return_string, return_code)
    """
    return CLIInvoker(\
                        comd = ['rpm','-q','--qf', "%{RELEASE}\n"],
                        print_output = False)

  def zypper_se_type_patch(self):
    """
    Method for returning all of the patches on a machine. 
    :return - CLIInvoker - (List<CLISolvable>, return_code)
    """
    return CLIInvoker(\
                        comd = ['zypper','--xmlout','se','-s','--type', 'patch'],
                        psr = XMLParser(CLISolvable, 'solvable'),
                        errors = [
                                    CLIInvokerError(error_code = 104, error_message = "Subprocess returned error code 104. \
                                    No patches were found. Ignoring error and continuing. ")
                                 ]
                        )



