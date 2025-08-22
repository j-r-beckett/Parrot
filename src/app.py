from litestar import Litestar
from src.config import settings
from src.lifespan import lifespan
from src.api.routes.health import health
from src.api.routes.sms import test_sms
from src.api.routes.assistant import (
    test_weather_hourly,
    test_weather_12hour,
    test_agent,
    test_geocoding,
    test_nav,
)


app = Litestar(
    route_handlers=[
        health,
        test_sms,
        test_weather_hourly,
        test_weather_12hour,
        test_agent,
        test_geocoding,
        test_nav,
    ],
    lifespan=[lifespan],
    debug=settings.debug,
)