"""Tests for the safe_tool decorator."""

import pytest
from unittest.mock import Mock
from pydantic_ai.tools import RunContext
from assistant.tool_wrapper import safe_tool


class TestSafeTool:
    @pytest.mark.asyncio
    async def test_safe_tool_returns_result_on_success(self):
        """Test that safe_tool returns the original result when no exception occurs."""

        @safe_tool
        async def successful_tool(ctx, param: str) -> str:
            return f"Success: {param}"

        ctx = Mock()
        result = await successful_tool(ctx, "test")
        assert result == "Success: test"

    @pytest.mark.asyncio
    async def test_safe_tool_catches_exception_and_returns_error_message(self):
        """Test that safe_tool catches exceptions and returns error message."""

        @safe_tool
        async def failing_tool(ctx, param: str) -> str:
            raise ValueError("Something went wrong")

        ctx = Mock()
        result = await failing_tool(ctx, "test")
        assert result == "Error: Something went wrong"

    @pytest.mark.asyncio
    async def test_safe_tool_logs_exception_details_with_runcontext(self):
        """Test that safe_tool logs full exception details when RunContext with logger is available."""

        # Create mock logger
        mock_logger = Mock()

        # Create mock RunContext with deps.logger
        mock_deps = Mock()
        mock_deps.logger = mock_logger
        mock_ctx = Mock(spec=RunContext)
        mock_ctx.deps = mock_deps

        @safe_tool
        async def failing_tool(ctx, param: str) -> str:
            raise ValueError("Test exception")

        result = await failing_tool(mock_ctx, "test")

        # Verify error message returned
        assert result == "Error: Test exception"

        # Verify logger was called with full traceback
        mock_logger.error.assert_called_once()
        log_call_args = mock_logger.error.call_args[0][0]
        assert "Tool 'failing_tool' failed:" in log_call_args
        assert "ValueError: Test exception" in log_call_args
        assert "Traceback" in log_call_args

    @pytest.mark.asyncio
    async def test_safe_tool_preserves_function_metadata(self):
        """Test that the decorator preserves the original function's metadata."""

        @safe_tool
        async def documented_tool(ctx, param: str) -> str:
            """This is a test tool with documentation."""
            return param

        assert documented_tool.__name__ == "documented_tool"
        assert documented_tool.__doc__ == "This is a test tool with documentation."

    @pytest.mark.asyncio
    async def test_safe_tool_passes_through_pydantic_ai_exceptions(self):
        """Test that pydantic-ai exceptions are passed through without handling."""

        # Create a mock pydantic-ai exception
        class MockPydanticAIException(Exception):
            pass

        # Mock the module to appear as pydantic_ai
        MockPydanticAIException.__module__ = "pydantic_ai.exceptions"

        @safe_tool
        async def pydantic_ai_exception_tool(ctx, param: str) -> str:
            raise MockPydanticAIException("This should pass through")

        ctx = Mock()

        # Should raise the exception, not catch it
        with pytest.raises(MockPydanticAIException, match="This should pass through"):
            await pydantic_ai_exception_tool(ctx, "test")
