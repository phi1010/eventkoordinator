import logging
import os
from pathlib import Path

import dotenv
from dynaconf import LazySettings

BASE_DIR = Path(__file__).resolve().parent.parent



def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def get_dynaconf_settings(include_autosettings: bool) -> LazySettings:
    logging.info("Loading Dynaconf settings")
    includes = [
        str(BASE_DIR / "settings.toml"),
    ]

    if env_bool("DJANGO_DEBUG", default=False):
        logging.warning("DJANGO_DEBUG is set to True, including settings.debug.toml")
        settings_debug_toml = BASE_DIR / "settings.debug.toml"
        if not settings_debug_toml.exists():
            logging.warning("settings.debug.toml does not exist, skipping")
        includes.append(str(settings_debug_toml))

    includes.append(str(BASE_DIR / ".settings.secrets.toml"))
    if include_autosettings:
        includes.append(str(BASE_DIR / "auto_settings.py"))

    lazy_settings = LazySettings(
        **dict(ENVVAR_PREFIX_FOR_DYNACONF="DJANGO", SETTINGS_FILE_FOR_DYNACONF=str(BASE_DIR / "default_settings.py"),
               INCLUDES_FOR_DYNACONF=includes, MERGE_ENABLED_FOR_DYNACONF=True, ))
    return lazy_settings
