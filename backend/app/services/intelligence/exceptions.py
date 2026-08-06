class IntelligenceError(Exception):
    """Base exception for all document intelligence framework errors."""
    pass


class CircularDependencyError(IntelligenceError):
    """Raised when there is a cyclic dependency loop in module declarations."""
    pass


class ModuleExecutionError(IntelligenceError):
    """Raised when a fatal error occurs during module execution."""
    pass
