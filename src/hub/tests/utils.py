"""Test utilities and shared mocks."""


class MockLogger:
    """Mock logger that implements the Litestar Logger protocol."""
    
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def warn(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass
    def critical(self, *args, **kwargs): pass
    def fatal(self, *args, **kwargs): pass
    def setLevel(self, *args, **kwargs): pass