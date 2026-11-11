"""Wrap a baseline/progressive JPEG in a one-page PDF without decoding it.

Some print servers (CUPS with a Canon inkjet in issue #8) print a native
`image/jpeg` job as a blank page while a PDF prints correctly. PDF can carry
a JPEG stream untouched (`/DCTDecode`), so the pixels are never re-encoded
and no imaging library is needed: only the JPEG headers are read, for the
dimensions, the colour model and the EXIF orientation.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# Marker bytes after 0xFF that start a frame we can embed (Huffman DCT:
# baseline, extended sequential, progressive). Arithmetic-coded, lossless and
# hierarchical frames are not valid /DCTDecode input for most viewers.
_SOF_OK = frozenset({0xC0, 0xC1, 0xC2})
_SOF_UNSUPPORTED = frozenset({0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})
_STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})

_POINTS_PER_HUNDREDTH_MM = 72 / 2540
# 10 mm clear border: stays inside the printable area of ordinary printers.
_MARGIN_PT = 10 * 72 / 25.4
_MIN_PAGE_PT = 72.0
_MAX_PAGE_PT = 14400.0  # the PDF 1.x page size limit (200 in)
_FALLBACK_PAGE_PT = (612.0, 792.0)

# EXIF orientation -> (p, q, r, s, t, w) with display X = p*u + q*v + r and
# Y = s*u + t*v + w, where (u, v) is the stored image's unit square with v up
# and (X, Y) the upright picture's unit square.
_ORIENTATION = {
    1: (1, 0, 0, 0, 1, 0),
    2: (-1, 0, 1, 0, 1, 0),
    3: (-1, 0, 1, 0, -1, 1),
    4: (1, 0, 0, 0, -1, 1),
    5: (0, -1, 1, -1, 0, 1),
    6: (0, 1, 0, -1, 0, 1),
    7: (0, 1, 0, 1, 0, 0),
    8: (0, -1, 1, 1, 0, 0),
}


@dataclass(frozen=True, slots=True)
class JpegInfo:
    width: int
    height: int
    components: int
    orientation: int  # EXIF 1-8; 1 when absent or invalid
    adobe: bool  # Adobe APP14 present (CMYK/YCCK data is stored inverted)


def parse_jpeg(data: bytes | bytearray) -> JpegInfo | None:
    """Read the headers of a JPEG; None when it cannot be embedded as-is."""
    size = len(data)
    if size < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None
    pos = 2
    orientation = 1
    adobe = False
    frame: tuple[int, int, int] | None = None
    while pos < size:
        if data[pos] != 0xFF:
            return None
        while pos < size and data[pos] == 0xFF:  # fill bytes
            pos += 1
        if pos >= size:
            return None
        marker = data[pos]
        pos += 1
        if marker == 0x00:
            return None
        if marker in _STANDALONE:
            continue
        if marker == 0xD9:  # EOI before a scan
            return None
        if pos + 2 > size:
            return None
        length = (data[pos] << 8) | data[pos + 1]
        if length < 2 or pos + length > size:
            return None
        segment = data[pos + 2:pos + length]
        if marker in _SOF_UNSUPPORTED:
            return None
        if marker in _SOF_OK:
            if len(segment) < 6 or segment[0] != 8:
                return None
            height = (segment[1] << 8) | segment[2]
            width = (segment[3] << 8) | segment[4]
            components = segment[5]
            if not width or not height or components not in (1, 3, 4):
                return None
            frame = (width, height, components)
        elif marker == 0xE1 and bytes(segment[:6]) == b"Exif\x00\x00":
            orientation = _exif_orientation(bytes(segment[6:])) or orientation
        elif marker == 0xEE and bytes(segment[:5]) == b"Adobe":
            adobe = True
        elif marker == 0xDA:  # start of scan: header is complete
            break
        pos += length
    if frame is None:
        return None
    return JpegInfo(frame[0], frame[1], frame[2], orientation, adobe)


def _exif_orientation(tiff: bytes) -> int | None:
    if len(tiff) < 8:
        return None
    if tiff[:2] == b"II":
        order = "<"
    elif tiff[:2] == b"MM":
        order = ">"
    else:
        return None
    try:
        if struct.unpack_from(order + "H", tiff, 2)[0] != 42:
            return None
        ifd = struct.unpack_from(order + "I", tiff, 4)[0]
        count = struct.unpack_from(order + "H", tiff, ifd)[0]
        for index in range(min(count, 256)):
            entry = ifd + 2 + 12 * index
            tag, kind, items = struct.unpack_from(order + "HHI", tiff, entry)
            if tag == 0x0112 and kind == 3 and items == 1:
                value = struct.unpack_from(order + "H", tiff, entry + 8)[0]
                return value if value in _ORIENTATION else None
    except struct.error:
        return None
    return None


def _num(value: float) -> bytes:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return (text if text not in ("", "-0") else "0").encode()


def _page_size(media_hundredths_mm: tuple[int, int] | None,
               display: tuple[int, int]) -> tuple[float, float]:
    page = _FALLBACK_PAGE_PT
    if media_hundredths_mm:
        candidate = tuple(value * _POINTS_PER_HUNDREDTH_MM for value in media_hundredths_mm)
        if all(_MIN_PAGE_PT <= value <= _MAX_PAGE_PT for value in candidate):
            page = candidate
    # Landscape pictures get a landscape page so they are not shrunk onto the
    # short side of a portrait one.
    if (display[0] > display[1]) != (page[0] > page[1]):
        page = (page[1], page[0])
    return page


def jpeg_to_pdf(data: bytes | bytearray,
                media_hundredths_mm: tuple[int, int] | None = None) -> bytes | None:
    """One-page PDF around `data`, or None if the JPEG cannot be embedded.

    The page is the printer's paper size (or US Letter when unknown), turned to
    landscape for a landscape picture, with the picture centred and fitted
    inside a 10 mm border at its EXIF orientation.
    """
    info = parse_jpeg(data)
    if info is None:
        return None
    swap = info.orientation >= 5
    shown_w, shown_h = (info.height, info.width) if swap else (info.width, info.height)
    page_w, page_h = _page_size(media_hundredths_mm, (shown_w, shown_h))
    margin = min(_MARGIN_PT, page_w / 4, page_h / 4)
    scale = min((page_w - 2 * margin) / shown_w, (page_h - 2 * margin) / shown_h)
    box_w, box_h = shown_w * scale, shown_h * scale
    x, y = (page_w - box_w) / 2, (page_h - box_h) / 2
    p, q, r, s, t, w = _ORIENTATION[info.orientation]
    matrix = (box_w * p, box_h * s, box_w * q, box_h * t, x + box_w * r, y + box_h * w)

    content = b"q " + b" ".join(_num(v) for v in matrix) + b" cm /Im0 Do Q\n"
    color = {1: b"/DeviceGray", 3: b"/DeviceRGB", 4: b"/DeviceCMYK"}[info.components]
    decode = b" /Decode [1 0 1 0 1 0 1 0]" if info.components == 4 and info.adobe else b""
    image_head = (
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s"
        b" /BitsPerComponent 8 /Filter /DCTDecode%s /Length %d >>\nstream\n"
        % (info.width, info.height, color, decode, len(data))
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " + _num(page_w) + b" " + _num(page_h)
        + b"] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        image_head + bytes(data) + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)
