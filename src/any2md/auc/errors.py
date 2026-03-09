from any2md.errors import Any2MDError


class AucError(Any2MDError):
    """Base exception for AUC-related errors."""


class AucNotConfiguredError(AucError):
    """Raised when AUC credentials are not configured."""


class AucApiError(AucError):
    """Raised when AUC API returns an error."""


class AucTimeoutError(AucError):
    """Raised when AUC task exceeds maximum wait time."""

    def __init__(self, task_id: str, max_wait_seconds: int) -> None:
        self.task_id = task_id
        self.max_wait_seconds = max_wait_seconds
        super().__init__(
            f"AUC task {task_id} exceeded maximum wait time of {max_wait_seconds}s"
        )


class AucTaskNotFoundError(AucError):
    """Raised when a cached AUC task cannot be found."""
