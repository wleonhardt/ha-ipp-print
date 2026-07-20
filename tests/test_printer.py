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
