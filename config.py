from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix="CLANKER",
    settings_files=['settings.json', 'prompts.json'],
    load_dotenv=True,
    merge_enabled=True,
)