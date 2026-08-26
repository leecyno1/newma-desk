class WorkflowAuthorizationError(Exception):
    """Raised when a principal cannot perform a workflow action."""


class WorkflowValidationError(Exception):
    """Raised when a workflow definition or command is invalid."""
