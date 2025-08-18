from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix="CLANKER",
    settings_files=['settings.json'],
    load_dotenv=True,
)