"""IPP compatibility cases, synthetic wire data rather than device claims."""
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ipp_print import printer as p
from custom_components.ipp_print.ipp_codec import Resolution, UnknownValue, decode_response

from test_printer import _job_group, _resp

GET_ATTRS = p.PrinterClient.get_printer_attrs
VALIDATE = p.PrinterClient.validate_job


def member(name, tag, raw):
    return p._attr(0x4A, b"", name.encode()) + p._attr(tag, b"", raw)


def test_nested_collections_preserve_groups_and_types():
    dimensions = (member("x-dimension", 0x21, p._int_value(21590))
                  + member("y-dimension", 0x21, p._int_value(27940)))
    media = (member("media-size", 0x34, b"") + dimensions
             + p._attr(0x37, b"", b"") + member("media-source", 0x44, b"tray-1"))
    raw = _resp(0, b"\x04" + p._attr(0x34, b"media-col-ready", b"")
                + media + p._attr(0x37, b"", b"")
                + p._attr(0x32, b"printer-resolution-supported", p._int_value(600) * 2 + b"\x03")
                + p._attr(0x30, b"vendor-value", b"\xff\x00")
                + b"\x05" + p._attr(0x44, b"media-source", b"tray-9"))
    response = decode_response(raw)
    ready = response.attributes((4,))["media-col-ready"][0]
    assert ready["media-size"][0]["x-dimension"] == [21590]
    assert ready["media-source"] == ["tray-1"]
    assert response.attributes((5,))["media-source"] == ["tray-9"]
    assert response.attributes((4,))["printer-resolution-supported"] == [Resolution(600, 600, 3)]
    assert response.attributes((4,))["vendor-value"] == [UnknownValue(0x30, b"\xff\x00")]
    assert p.parse_printer_attrs_response(raw).media_collections["media-col-ready"] == [ready]


@pytest.mark.parametrize("payload", [
    p._attr(0x34, b"x", b"bad"),
    p._attr(0x34, b"x", b"") + member("nested", 0x34, b"") * 9,
    p._attr(0x34, b"x", b"") + p._attr(0x21, b"", p._int_value(1)),
    p._attr(0x32, b"x", b"bad"),
])
def test_malformed_collections_and_resolutions_fail_bounded(payload):
    with pytest.raises(ValueError):
        decode_response(_resp(0, b"\x04" + payload))


@pytest.mark.parametrize("status", [1, 2])
def test_success_warnings_keep_job_and_unsupported_names(status):
    result = p.parse_print_job_response(_resp(
        status, _job_group(7, 3) + b"\x05" + p._attr(0x44, b"sides", b"two-sided-long-edge")))
    assert result.job_id == 7 and result.warning
    assert result.unsupported_attributes == ("sides",)


async def test_format_query_uses_mime_and_preserves_ready_vs_default():
    raw = _resp(0, b"\x04"
                + p._attr(0x49, b"document-format-supported", b"application/pdf")
                + p._attr(0x44, b"media-default", b"iso_a4_210x297mm")
                + p._attr(0x44, b"media-ready", b"na_letter_8.5x11in"))
    client = p.PrinterClient(host="example")
    with patch.object(client, "_post_ipp", AsyncMock(return_value=raw)) as post:
        info = await GET_ATTRS(client, "application/pdf")
        assert info.media_default == "iso_a4_210x297mm"
        assert set(info.media_ready) == {"na_letter_8.5x11in"}
        assert info.document_format == "application/pdf"
        for call in post.call_args_list:
            attrs = decode_response(call.args[0]).attributes()
            assert attrs["document-format"] == ["application/pdf"]
            assert len(attrs["requested-attributes"]) <= 8
        assert await GET_ATTRS(client, "application/pdf") is info
        assert post.await_count == 3


async def test_read_only_version_negotiation_remembers_11():
    client = p.PrinterClient(host="example")
    with patch.object(client, "_post_ipp", AsyncMock(side_effect=[
        _resp(0x0503), _resp(0), _resp(0),
    ])) as post:
        await GET_ATTRS(client)
        await GET_ATTRS(client)
    assert [call.args[0][:2] for call in post.call_args_list] == [b"\x02\x00", b"\x01\x01", b"\x01\x01"]


async def test_transport_failure_does_not_probe_another_version():
    client = p.PrinterClient(host="example")
    with patch.object(client, "_post_ipp", AsyncMock(side_effect=TimeoutError)) as post:
        with pytest.raises(TimeoutError):
            await GET_ATTRS(client)
        post.assert_awaited_once()


async def test_validation_sends_no_document_and_unsupported_fallback_is_remembered():
    client = p.PrinterClient(host="example")
    with patch.object(client, "_post_ipp", AsyncMock(return_value=_resp(0x0501))) as post:
        assert await VALIDATE(client, document_format="application/pdf", copies=2)
        assert await VALIDATE(client, document_format="application/pdf", copies=2)
        post.assert_awaited_once()
        request = post.call_args.args[0]
        assert int.from_bytes(request[2:4], "big") == p.OP_VALIDATE_JOB
        assert request.endswith(b"\x03")
        assert decode_response(request).attributes()["copies"] == [2]


@pytest.mark.parametrize("status", [1, 2, 0x040B])
async def test_validation_rejects_substitution_before_upload(status):
    client = p.PrinterClient(host="example")
    with patch.object(client, "_post_ipp", AsyncMock(return_value=_resp(status))):
        with pytest.raises(p.IppError, match="validation"):
            await VALIDATE(client, document_format="application/pdf", sides="one-sided")


def test_tray_and_paper_encode_in_one_typed_collection():
    request = p.build_print_job(printer_uri="ipp://printer/ipp/print", user="anonymous",
                               job_name="test", document_format="application/pdf", document=b"",
                               media="iso_a4_210x297mm", media_source="tray-1")
    attrs = decode_response(request).attributes((2,))
    assert attrs["media-col"] == [{"media-source": ["tray-1"],
                                   "media-size": [{"x-dimension": [21000], "y-dimension": [29700]}]}]
    assert "media" not in attrs


async def test_routine_queries_never_request_expansive_media_database():
    client = p.PrinterClient(host="example")
    with patch.object(client, "_post_ipp", AsyncMock(return_value=_resp(0))) as post:
        await GET_ATTRS(client, "application/postscript")
    requested = [name for call in post.call_args_list
                 for name in decode_response(call.args[0]).attributes()["requested-attributes"]]
    assert "media-col-database" not in requested
    assert "media-source-supported" in requested


async def test_preflight_may_negotiate_version_without_submitting_document():
    client = p.PrinterClient(host="example")
    with patch.object(client, "_post_ipp", AsyncMock(side_effect=[_resp(0x0503), _resp(0)])) as post:
        assert await VALIDATE(client, document_format="application/pdf", copies=1) is None
    assert len(post.call_args_list) == 2
    for call in post.call_args_list:
        assert int.from_bytes(call.args[0][2:4], "big") == p.OP_VALIDATE_JOB
        assert call.args[0].endswith(b"\x03")


async def test_service_format_caches_are_bounded_and_evictions_drain():
    from custom_components.ipp_print import _format_cache
    live = {"client": p.PrinterClient(host="example")}
    first = await _format_cache(live, "application/pdf")
    for number in range(8):
        await _format_cache(live, f"application/vendor-{number}")
    assert first.closed
    assert len(live["format_caches"]) == 8
    for cache in live["format_caches"].values():
        await cache.async_close()


@pytest.mark.parametrize("media,expected", [
    ("na_letter_8.5x11in", (21590, 27940)),
    ("iso_a4_210x297mm", (21000, 29700)),
    ("vendor_opaque", None), ("vendor_zero_0x3in", None),
])
def test_media_keyword_dimensions_are_exact(media, expected):
    assert p.media_dimensions(media) == expected
