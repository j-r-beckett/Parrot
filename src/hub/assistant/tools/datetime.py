from datetime import datetime
from timezonefinder import TimezoneFinder
import pytz
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from assistant.dependencies import AssistantDependencies

# Initialize TimezoneFinder at module level since it's expensive to create
tf = TimezoneFinder()


def register_datetime_tool(agent: Agent[AssistantDependencies, str]) -> None:
    """Register datetime tool on the agent."""

    @agent.tool
    async def get_current_datetime(
        ctx: RunContext[AssistantDependencies], location: str
    ) -> str:
        """Get the current date and time for a location.

        Args:
            location: The location to get the time for (e.g., "New York City", "Tokyo", "London")

        Returns:
            The current date and time in YYYY-MM-DD HH:MM:SS format
        """
        # Geocode the location to get coordinates
        lat, lon = await ctx.deps.geocode(location)

        # Get timezone for the coordinates
        timezone_str = tf.timezone_at(lat=lat, lng=lon)

        if not timezone_str:
            # Fallback to UTC if timezone not found
            timezone_str = "UTC"

        # Get current time in that timezone
        tz = pytz.timezone(timezone_str)
        local_time = datetime.now(tz)

        # Return formatted datetime without timezone info
        return local_time.strftime("%Y-%m-%d %H:%M:%S")
