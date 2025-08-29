from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModelSettings
from config import settings
from .dependencies import AssistantDependencies


def create_assistant(dependencies_type: type[AssistantDependencies] = AssistantDependencies) -> Agent[AssistantDependencies, str]:
    """Create assistant agent with tools."""
    agent = Agent(
        "anthropic:claude-sonnet-4-20250514",
        deps_type=dependencies_type,
        system_prompt=settings.prompts.assistant,
        model_settings=AnthropicModelSettings(
            max_tokens=settings.llm.max_tokens,
            thinking={"type": "enabled", "budget_tokens": settings.llm.max_tokens // 2}
        )
    )
    
    # Register tools
    register_assistant_tools(agent)
    return agent


def register_assistant_tools(agent: Agent[AssistantDependencies, str]) -> None:
    """Register all assistant tools on the agent."""
    
    # Import and register tools from separate files
    from assistant.tools.weather import register_weather_tool
    from assistant.tools.datetime import register_datetime_tool  
    from assistant.tools.navigation import register_navigation_tool
    
    register_weather_tool(agent)
    register_datetime_tool(agent)
    register_navigation_tool(agent)