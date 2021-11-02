# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import os
import logging
import subprocess
from patch_common.cli_invoker_error import CLIInvokerError
from pwd import getpwnam 

class CLIInvoker:
  """
  Class for representing a CLI command.
  HOW TO USE THIS CLASS:
    - To execute commands using the CLI Invoker, use the default executable of 'bash' by leaving the 'executable' param empty.
    - Else specify an executable in the 'executable' parameter. For example, '"/usr/bin/zypper"' as the executable_path and then 'shell' as the first
    command argument will execute commands in the zypper shell.
    - If a parser is provided, the output of parser.parse(cli_response) will be returned with the exit code of the subprocess as a tuple.
    - Else simply the response text. 
    -For example:(<response_text>, 0)
     The command "echo 'Hello world!' if no parser is provided will return the tuple:
     ('Hello world!', 0)
  """
  CONST_SYSTEM_MANAGEMENT_IS_LOCKED_ERROR = "System management is locked"

  def __init__(self, comd, psr = None, executable= None, print_output=True, errors = [], working_dir=None):
    """
    Method for instantiating a CLI command instance.
    :param - comd is a string array representing the cli command to execute.
    :param - psr is a class with a "parse" method on it that provides parsing capabilities of the response.
    :param - executable is an executable to use besides bash.
    :param - print_output is a boolean indicating whether to log the command as some of them can be large and take up log space. 
    :param - errors is a list of CLIInvokerErrors indicating which errors to log but ignore. 
    """
    self.command = comd
    self.logger = logging.getLogger()
    self.parser_instance = psr
    self.executable_path=executable
    self.print_output = print_output
    self.working_directory = working_dir
    self.__set_errors(errors)

  def execute(self, items_to_append = None):
    """
    Method for executing the provided CLI command.
    :param items_to_append is an array of command to append to current command.
    :param executable_path defaults to bash if none is specified. If one is specified it will use that executable instead.
    :param environment to execute in. 
    :return - output of a tuple containing:
      1) If a parser was provided, the output of parser.parse(cli_response) else the subprocess output text.
      2) the return code from the subprocess.
    """
    try:
      effective_command = self.command
      result = None
      
      if items_to_append:
        effective_command = effective_command + items_to_append
      
      final_command = [command.encode("utf-8") for command in effective_command]

      self.__print_info("Running command %s"%(final_command))
      if self.working_directory:
        self.working_directory = os.path.dirname(self.working_directory)
        self.__print_info("Running with current working directory (cwd) %s"%(self.working_directory))
        

      process = subprocess.Popen(\
        final_command, \
        stdout=subprocess.PIPE, \
        stderr=subprocess.STDOUT, \
        cwd=self.working_directory, \
        executable=self.executable_path)

      result = process.communicate()
      process.poll() # populates return code.

      self.__print_info("Parsing response...")

      result = self.process_result(result, process.returncode, final_command)
      
      if self.CONST_SYSTEM_MANAGEMENT_IS_LOCKED_ERROR in result[0]:
        raise CLIInvokerException(result[0])

      if self.parser_instance:
        return (self.parser_instance.parse(result[0]), process.returncode)
      else:
        return (result[0], process.returncode)

    except Exception as e:
      # If this is an expected error, we are going to log it and continue.
      if result and process.returncode in self.errors:
        self.logger.info("Encountered a known exception: %s . \n ignoring and continuing."%(self.errors[result[1]]))
      else:        
	      raise CLIInvokerException("Failed CLI Invocation: %s"%(self.command), e)

  def process_result(self, result, returncode, final_command):
    """
    Method for determining whether or not to throw an exception on the result. 
    :param result is the result from a process.communicate() call.
    :param returncode is the subprocess.returncode.
    :param final_command is the CLIInvoker command with any parameters that were appended to it. 
    :return result or throws a CLIInvokerException.
    """
    if not result:
      raise CLIInvokerException("Subprocess returned a null result for command %s"%(final_command))

    result_string = result[0]
    if not isinstance(result_string, str):
       result_string = result_string.decode("utf-8")

    if returncode != 0 and returncode not in self.errors:
      raise CLIInvokerException("Subprocess returned error code %s for command %s. \n Output: %s"%(returncode, final_command, result[0]))
    elif returncode != 0 and returncode in self.errors:
      self.logger.info("Encountered a known exception in the CLI Invoker: %s . \n ignoring and continuing."%(self.errors[returncode]))

    return (result_string, result[1])

  def __print_info(self, text_to_print):
    """
    Method to print info to output / logs.
    :param text_to_print is the text to add to logs / output.
    """
    if self.print_output:
      self.logger.info(text_to_print)

  def __set_errors(self, errors):
    """
    Method for setting the provided list of errors into a hash of form {"error code" : CLIInvokerError}.
    Throws error if error is not of correct type.
    :param errors - list of type CLIInvokerError
    """
    self.errors = {}
    if errors:
      for error in errors:
        if not isinstance(error, CLIInvokerError):
          raise CLIInvokerException("All provided errors must be of type CLIInvokerError. Problem Command: %s"%(self.command))
          
        self.errors[error.error_code] = error


class CLIInvokerException(Exception):
   """Raised when there is an unknown error in the CLIInvoker."""
   pass