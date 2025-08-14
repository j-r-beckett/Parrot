from weather_client import WeatherClient
from decorators import add_docstring


def forecast_tool(weather_client: WeatherClient):
    description = "Returns a weather forecast for the user's area"

    @add_docstring(description)
    def forecast() -> str:
        return "It's 80F and there's a high chance of acid rain!"

    return forecast
