from dynaconf import Dynaconf
import os

settings = Dynaconf(
    envvar_prefix=False,
    settings_files=[
        os.path.join(os.path.dirname(__file__), "settings.json"),
    ],
    load_dotenv=True,
    merge_enabled=True,
)
