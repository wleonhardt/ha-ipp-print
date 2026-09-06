"""IPP wire-format builder/parser tests — pure functions, no network."""
import pytest

from custom_components.ipp_print import printer as p

JOB_GROUP = 0x02  # job-attributes group delimiter


def _resp(status: int, groups: bytes = b"") -> bytes:
    """Craft a minimal IPP response: version 2.0, status, request-id 1."""
    return (
        b"\x02\x00"
        + status.to_bytes(2, "big")
        + (1).to_bytes(4, "big")
        + groups
        + bytes([p.TAG_END_ATTRS])
    )


def _job_group(job_id: int = 7, state: int = 5, extra: bytes = b"") -> bytes:
    return (
        bytes([JOB_GROUP])
        + p._attr(p.TAG_INTEGER, b"job-id", p._int_value(job_id))
        + p._attr(p.TAG_ENUM, b"job-state", p._int_value(state))
        + extra
    )


def test_build_print_job_layout():
    doc = b"%PDF-1.7 fake"
    req = p.build_print_job(
        printer_uri="ipps://host/ipp/print",
        user="anonymous",
        job_name="doc.pdf",
        document_format="application/pdf",
        document=doc,
    )
    assert req[:2] == b"\x02\x00"
    assert int.from_bytes(req[2:4], "big") == p.OP_PRINT_JOB
    assert req.endswith(bytes([p.TAG_END_ATTRS]) + doc)
    assert b"job-name" in req and b"application/pdf" in req


def test_build_print_job_accepts_bytearray():
    req = p.build_print_job(
        printer_uri="ipp://h/ipp/print",
        user="u",
        job_name="a",
        document_format="application/pdf",
        document=bytearray(b"%PDF-x"),
    )
    assert isinstance(req, bytes) and req.endswith(b"%PDF-x")


def test_job_name_truncated_at_codepoint_boundary():
    req = p.build_print_job(
        printer_uri="ipp://h/ipp/print",
        user="u",
        job_name="é" * 200,  # 400 UTF-8 bytes; naive [:255] splits a codepoint
        document_format="application/pdf",
        document=b"",
    )
    idx = req.index(b"job-name") + len(b"job-name")
    vlen = int.from_bytes(req[idx : idx + 2], "big")
    value = req[idx + 2 : idx + 2 + vlen]
    assert vlen <= 255
    value.decode("utf-8")  # must not raise


def test_parse_print_job_response():
    data = _resp(0x0000, _job_group(job_id=42, state=3))
    result = p.parse_print_job_response(data)
    assert result.ipp_status == 0
    assert result.job_id == 42
    assert result.job_state == 3
    assert result.job_state_name == "pending"


def test_parse_job_attrs_full():
    extra = (
        p._attr(0x44, b"job-state-reasons", b"job-printing")
        + p._attr(p.TAG_INTEGER, b"job-impressions-completed", p._int_value(2))
        + p._attr(p.TAG_INTEGER, b"job-impressions", p._int_value(5))
        + p._attr(p.TAG_NAME_WITHOUT_LANG, b"job-name", b"doc.pdf")
    )
    attrs = p.parse_job_attrs_response(_resp(0x0000, _job_group(7, 5, extra)))
    assert attrs is not None
    assert attrs.job_state_name == "processing"
    assert attrs.job_state_reasons == "job-printing"
    assert attrs.impressions_completed == 2
    assert attrs.impressions_total == 5
    assert attrs.job_name == "doc.pdf"


def test_parse_job_attrs_1setof_carries_name():
    # Second value of a 1setOf has a zero-length name and belongs to the
    # previous attribute.
    extra = (
        p._attr(0x44, b"job-state-reasons", b"none")
        + p._attr(0x44, b"", b"job-incoming")
    )
    attrs = p.parse_job_attrs_response(_resp(0x0000, _job_group(7, 3, extra)))
    assert attrs is not None
    assert attrs.job_state_reasons == "none"  # first value wins


def test_parse_job_attrs_not_found_raises_job_gone():
    with pytest.raises(p.JobGoneError):
        p.parse_job_attrs_response(_resp(p.STATUS_NOT_FOUND))


def test_parse_job_attrs_missing_state_is_none_not_terminal():
    groups = bytes([JOB_GROUP]) + p._attr(
        p.TAG_INTEGER, b"job-id", p._int_value(7)
    )
    assert p.parse_job_attrs_response(_resp(0x0000, groups)) is None


def test_parse_response_too_short_raises():
    with pytest.raises(ValueError):
        p.parse_response(b"\x02\x00")


def test_parse_truncated_attributes_terminates():
    # Garbage/truncated payload must neither hang nor crash.
    data = _resp(0x0000)[:-1] + b"\x42\x00\xff"
    status, attrs = p.parse_response(data)
    assert status == 0


def test_ipp_http_error_messages():
    assert "authentication" in str(p.IppHttpError(401))
    assert "HTTP 503" in str(p.IppHttpError(503))


PRINTER_GROUP = 0x04  # printer-attributes group delimiter


def test_build_print_job_job_template_group():
    req = p.build_print_job(
        printer_uri="ipp://h/ipp/print", user="u", job_name="a",
        document_format="application/pdf", document=b"%PDF-x",
        copies=3, sides="two-sided-long-edge",
    )
    # job-attributes group sits between the operation group and end tag.
    jg = req.index(bytes([p.TAG_JOB_ATTRS]) + p._attr(p.TAG_INTEGER, b"copies", p._int_value(3)))
    assert jg > 0
    assert b"sides" in req and b"two-sided-long-edge" in req
    assert req.index(b"copies") < req.index(bytes([p.TAG_END_ATTRS]) + b"%PDF-x")


def test_build_print_job_omits_group_without_options():
    req = p.build_print_job(
        printer_uri="ipp://h/ipp/print", user="u", job_name="a",
        document_format="application/pdf", document=b"", copies=1,
    )
    # Operation group runs straight into end-of-attributes: no job group.
    assert req.endswith(b"application/pdf" + bytes([p.TAG_END_ATTRS]))
    assert b"copies" not in req


def test_build_get_printer_attrs_requested_1setof():
    req = p.build_get_printer_attrs(printer_uri="ipp://h/ipp/print", user="u")
    assert int.from_bytes(req[2:4], "big") == p.OP_GET_PRINTER_ATTRS
    assert req.count(b"requested-attributes") == 1
    for kw in p.PRINTER_ATTRS_REQUESTED:
        assert kw in req


def test_parse_printer_attrs():
    grp = (
        bytes([PRINTER_GROUP])
        + p._attr(p.TAG_NAME_WITHOUT_LANG, b"printer-name", b"office")
        + p._attr(0x41, b"printer-info", b"Office MFP")
        + p._attr(0x41, b"printer-make-and-model", b"Acme LaserJet 1000")
        + p._attr(p.TAG_URI, b"printer-uuid", b"urn:uuid:abc")
        + p._attr(p.TAG_MIME_MEDIA_TYPE, b"document-format-supported", b"application/pdf")
        + p._attr(p.TAG_MIME_MEDIA_TYPE, b"", b"image/jpeg")
        + p._attr(p.TAG_KEYWORD, b"sides-supported", b"one-sided")
        + p._attr(p.TAG_KEYWORD, b"", b"two-sided-long-edge")
        + p._attr(p.TAG_RANGE_OF_INTEGER, b"copies-supported", p._int_value(1) + p._int_value(99))
        + p._attr(p.TAG_BOOLEAN, b"color-supported", b"\x01")
    )
    info = p.parse_printer_attrs_response(_resp(0x0000, grp))
    assert info.name == "office"
    assert info.info == "Office MFP"
    assert info.make_and_model == "Acme LaserJet 1000"
    assert info.uuid == "urn:uuid:abc"
    assert info.formats == ["application/pdf", "image/jpeg"]
    assert info.sides == ["one-sided", "two-sided-long-edge"]
    assert info.copies_max == 99
    assert info.supports_format("image/jpeg")
    assert not info.supports_format("image/png")


def test_parse_printer_attrs_error_status_raises():
    with pytest.raises(p.IppError):
        p.parse_printer_attrs_response(_resp(0x0400))


def test_supports_format_octet_stream_means_anything():
    info = p.PrinterInfo(
        name=None, info=None, location=None, make_and_model=None, uuid=None,
        formats=["application/octet-stream"], sides=[], copies_max=None,
    )
    assert info.supports_format("image/png")


def test_client_url_uses_path_and_port():
    c = p.PrinterClient(host="h", port=631, use_tls=False, path="printers/office")
    assert c.printer_uri == "ipp://h:631/printers/office"
    assert c._url == "http://h:631/printers/office"
    assert c.web_url == "http://h:631/"
    c2 = p.PrinterClient(host="h", port=443, use_tls=True)
    assert c2.printer_uri == "ipps://h/ipp/print"
    assert c2.web_url == "https://h/"
