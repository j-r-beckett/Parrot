import clients.weather as weather_client
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from assistant.dependencies import AssistantDependencies


def register_weather_tool(agent: Agent[AssistantDependencies, str]) -> None:
    """Register weather tool on the agent."""
    
    @agent.tool
    async def forecast(ctx: RunContext[AssistantDependencies], location: str) -> str:
        """Returns a weather forecast formatted as JSON."""
        lat, lon = await ctx.deps.geocode(location)
        forecast = await weather_client.twelve_hour_forecast(
            ctx.deps.weather_client, ctx.deps.logger, lat, lon
        )
        return forecast.model_dump_json()
