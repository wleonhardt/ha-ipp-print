"""Shared constants."""
from __future__ import annotations

DOMAIN = "ipp_print"

# Config-entry data keys.
CONF_HOST = "host"
CONF_PORT = "port"
CONF_PATH = "path"
CONF_USE_TLS = "use_tls"
CONF_USER = "user"
CONF_PASSWORD = "password"
CONF_VERIFY_TLS = "verify_tls"
CONF_RELAXED_CIPHERS = "relaxed_ciphers"

DEFAULT_PORT = 443
DEFAULT_PATH = "/ipp/print"
DEFAULT_USER = "anonymous"

# Card asset shipped inside the integration. Served at a content-hash URL
# from async_setup_entry so browser caches invalidate automatically.
CARD_FILENAME = "card.js"
CARD_URL_PREFIX = "/ipp_print/card-"  # followed by hash + .js

# Upload limits.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB
PDF_MAGIC = b"%PDF-"

# Document formats we can identify from content. `%PDF-` may appear anywhere
# in the first 1024 bytes (spec); the image magics are strict prefixes.
IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
FORMAT_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

# Service: ipp_print.print_file
SERVICE_PRINT_FILE = "print_file"
ATTR_PATH = "path"
ATTR_DOCUMENT_FORMAT = "document_format"
ATTR_JOB_NAME = "job_name"
ATTR_COPIES = "copies"
ATTR_SIDES = "sides"


def sniff_format(buf: bytes | bytearray) -> str | None:
    """Return the MIME type for a document we know how to identify."""
    head = bytes(buf[:1024])
    for magic, fmt in IMAGE_MAGIC:
        if head.startswith(magic):
            return fmt
    if PDF_MAGIC in head:
        return "application/pdf"
    return None


_JFIF_APP0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"


def ensure_jpeg_app_segment(document: bytes | bytearray) -> bytes | bytearray:
    """Give a JPEG with no APPn segment a minimal JFIF header.

    CUPS image filters only recognise a JPEG whose first segment is APPn
    (JFIF or Exif) and fail the job otherwise, which prints nothing or a
    blank page. Files with stripped metadata have none. The image data is
    not touched.
    """
    if len(document) < 4 or document[:3] != b"\xff\xd8\xff" or 0xE0 <= document[3] <= 0xEF:
        return document
    return document[:2] + _JFIF_APP0 + document[2:]
