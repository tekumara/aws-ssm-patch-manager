class PatchManagerError(Exception):
    def __str__(self):
        if self.cause:
            return super(PatchManagerError, self).__str__() + "\n Caused By: " + self.cause.__str__()
        return super(PatchManagerError, self).__str__()

    def __init__(self, message, error_code, cause=None):
        super(PatchManagerError, self).__init__(message, error_code)
        self.message = message
        self.error_code = error_code
        self.cause = cause

