from litestar import Litestar
from config import settings
from lifespan import lifespan
from routes.health import health
from routes.sms import test_sms
from routes.webhook import handle_smsgap_received, handle_smsgap_delivered
from routes.assistant import (
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
        handle_smsgap_received,
        handle_smsgap_delivered,
        test_weather_hourly,
        test_weather_12hour,
        test_agent,
        test_geocoding,
        test_nav,
    ],
    lifespan=[lifespan],
    debug=settings.debug,
)
