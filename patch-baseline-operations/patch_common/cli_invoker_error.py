class CLIInvokerError(object):
    """
    Class for representing a CLI call error.
    """
    def __init__(self, error_message, error_code):
        """
        Initialization method for class.
        :param error_message is the message to display on the error. Required.
        :param error_code is the error code the error represents. Required.
        """

        if error_message == None:
            raise NotImplementedError("All CLIInvokerError must provide an error_message to log and explain the error.")
        
        if error_code == None:
            raise NotImplementedError("All CLIInvokerError must provide an error_code they represent.")

        self.error_message = error_message
        self.error_code = error_code

    @property
    def error_message(self):
        """
        Method for getting the message to log for this error.
        """
        return self.__error_message

    @error_message.setter
    def error_message(self, error_message):
        """
        Method for setting the message to be logged, describe and explain this error.
        :param error_message is the message to be logged, desribe and explain this error.
        """
        self.__error_message = error_message

    @property
    def error_code(self):
        """
        Method for getting the error code that represents this error.
        """
        return self.__error_code

    @error_code.setter
    def error_code(self, error_code):
        """
        Method for setting the error code that represents this error.
        :param error code as a string.
        """
        self.__error_code = error_code
