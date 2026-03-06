
import json
import logging
import logging.config
import pprint
from urllib.error import URLError
from urllib.request import urlopen
from dynaconf import LazySettings

from project.dynaconfsettings import get_dynaconf_settings

logging.info(f"Loading {__name__}")

dynasettings = get_dynaconf_settings(include_autosettings=False)


_discovery_payload: dict[str, str] = {}
if dynasettings.OIDC_DISCOVERY_URL:
    logging.info("Attempting OIDC discovery for %s", dynasettings.OIDC_DISCOVERY_URL)
    try:
        with urlopen(dynasettings.OIDC_DISCOVERY_URL, timeout=dynasettings.OIDC_DISCOVERY_TIMEOUT_SECONDS or 10) as response:
            _discovery_payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logging.getLogger(__name__).warning(
            "OIDC discovery failed for %s: %s",
            dynasettings.OIDC_DISCOVERY_URL,
            exc,
        )

    OIDC_OP_AUTHORIZATION_ENDPOINT = _discovery_payload.get("authorization_endpoint", "")
    OIDC_OP_TOKEN_ENDPOINT = _discovery_payload.get("token_endpoint", "")
    OIDC_OP_USER_ENDPOINT = _discovery_payload.get("userinfo_endpoint", "")
    OIDC_OP_JWKS_ENDPOINT = _discovery_payload.get("jwks_uri", "")
    OIDC_OP_LOGOUT_ENDPOINT = _discovery_payload.get("end_session_endpoint", "")
else:
    logging.info("No OIDC discovery URL configured, skipping discovery")

#logging.config.dictConfig(dynasettings.LOGGING_CONFIG)