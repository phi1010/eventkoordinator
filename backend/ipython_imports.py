import os
import sys  # noqa: F403, E402, F401
from pathlib import Path  # noqa: F403, E402, F401
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
django.setup()

from django.conf import settings  # noqa: E402, F401
from apiv1.models import *  # noqa: F403, E402
from openid_user_management.models import *  # noqa: F403, E402

__all__ = [key for key in globals().keys() if not key.startswith("_")]
