"""
Django settings entrypoint for Dynaconf.

Dynaconf load order (low -> high priority):
1) backend/default_settings.py
2) backend/settings.toml
3) backend/settings.debug.toml
4) backend/.settings.secrets.toml (merged)
5) environment variables
"""

import logging
import logging.config
import sys

import dotenv

from project.dynaconfsettings import get_dynaconf_settings
import django.conf.global_settings

dotenv.load_dotenv()

LOGGING = django.conf.global_settings.LOGGING

logging.info(f"Loading {__name__}")

dynaconf_settings = get_dynaconf_settings(include_autosettings=True)
dynaconf_settings.populate_obj(sys.modules[__name__], ignore=locals())

LOGGING = dynaconf_settings.get("LOGGING", LOGGING)
if dynaconf_settings.get("SECRET_KEY") is None:
    raise Exception("SECRET_KEY is not set. This is not recommended for production.")