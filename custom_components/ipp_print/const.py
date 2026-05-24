"""Shared constants."""
from __future__ import annotations

DOMAIN = "ipp_print"

# Config-entry data keys.
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USE_TLS = "use_tls"
CONF_USER = "user"
CONF_PASSWORD = "password"
CONF_VERIFY_TLS = "verify_tls"
CONF_RELAXED_CIPHERS = "relaxed_ciphers"

DEFAULT_PORT = 443
DEFAULT_USER = "anonymous"

# Card asset shipped inside the integration. Served at a content-hash URL
# from async_setup_entry so browser caches invalidate automatically.
CARD_FILENAME = "card.js"
CARD_URL_PREFIX = "/ipp_print/card-"  # followed by hash + .js

# Upload limits.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB
PDF_MAGIC = b"%PDF-"
