from datetime import datetime
from timezonefinder import TimezoneFinder
import pytz
from nominatim_client import NominatimClient


def datetime_tool(nominatim_client: NominatimClient):
    """Create a datetime tool function for the assistant."""
    
    tf = TimezoneFinder()
    
    async def get_current_datetime(location: str) -> str:
        """Get the current date and time for a location.
        
        Args:
            location: The location to get the time for (e.g., "New York City", "Tokyo", "London")
            
        Returns:
            The current date and time in YYYY-MM-DD HH:MM:SS format
        """
        # Geocode the location to get coordinates
        lat, lon = await nominatim_client.geocode(location)
        
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
    
    return get_current_datetime