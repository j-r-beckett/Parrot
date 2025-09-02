"""Standardized exception handling wrapper for assistant tools."""

import functools
import traceback
from typing import Any, Awaitable, Callable, TypeVar, cast
from pydantic_ai.tools import RunContext


F = TypeVar('F', bound=Callable[..., Awaitable[Any]])


def safe_tool(func: F) -> F:
    """
    Decorator that wraps async tool functions to catch all exceptions and return 
    error messages instead of letting them propagate and kill the request thread.
    
    Logs full exception details but only returns the exception message to the LLM.
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Let pydantic-ai exceptions pass through unchanged
            if e.__class__.__module__.startswith('pydantic_ai'):
                raise
            
            # Log full traceback for debugging
            args[0].deps.logger.error(
                f"Tool '{func.__name__}' failed: {traceback.format_exc()}"
            )
            
            # Return just the exception message to the LLM
            return f"Error: {str(e)}"
    
    return cast(F, wrapper)