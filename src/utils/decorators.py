def add_docstring(doc):
    def decorator(func):
        func.__doc__ = doc
        return func

    return decorator
