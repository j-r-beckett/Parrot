from dynaconf import Dynaconf
import os

settings = Dynaconf(
    envvar_prefix="CLANKER",
    settings_files=[
        os.path.join(os.path.dirname(__file__), "settings.json"),
        os.path.join(os.path.dirname(__file__), "prompts.json"),
    ],
    load_dotenv=True,
    merge_enabled=True,
)

