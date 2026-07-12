class ServiceError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def as_payload(self):
        return {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
