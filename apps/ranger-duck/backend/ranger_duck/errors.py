class DemoError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "retryable": self.retryable}}


def upstream_error() -> DemoError:
    return DemoError("upstream_error", "The video service could not complete this request.", retryable=True)


def timeout_error() -> DemoError:
    return DemoError("upstream_timeout", "The video search or playback timed out. Please retry.", 504, True)
