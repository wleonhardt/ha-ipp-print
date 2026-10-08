"""Exercise real aiohttp transport against a local IPP stand-in."""
from unittest.mock import AsyncMock, patch

from aiohttp import web
import pytest

from custom_components.ipp_print import printer as p


async def test_print_payload_content_length_and_connection_reuse(aiohttp_server, socket_enabled):
    received = []
    connections = []
    response = (
        b"\x02\x00\x00\x00\x00\x00\x00\x01\x02"
        + p._attr(p.TAG_INTEGER, b"job-id", p._int_value(7))
        + p._attr(p.TAG_ENUM, b"job-state", p._int_value(3))
        + b"\x03"
    )

    async def ipp(request):
        received.append((dict(request.headers), await request.read()))
        connections.append(request.transport)
        return web.Response(body=response, content_type="application/ipp")

    app = web.Application()
    app.router.add_post("/ipp/print", ipp)
    server = await aiohttp_server(app)
    client = p.PrinterClient(host=server.host, port=server.port, use_tls=False)
    document = bytearray(b"%PDF-" + b"x" * (3 * p.DOCUMENT_CHUNK_BYTES + 17))
    try:
        for _ in range(2):
            result = await client.print_job(
                job_name="x.pdf", document_format="application/pdf", document=document,
                copies=1, sides="one-sided",
            )
            assert result.job_id == 7
        expected = p.build_print_job(
            printer_uri=client.printer_uri, user="anonymous", job_name="x.pdf",
            document_format="application/pdf", document=document, copies=1, sides="one-sided",
        )
        for headers, body in received:
            assert body == expected
            assert headers["Content-Length"] == str(len(expected))
            assert "Transfer-Encoding" not in headers
        assert connections[0] is connections[1]
    finally:
        await client.async_close()


async def test_payload_retains_document_and_writes_bounded_views():
    document = bytearray(b"x" * (2 * p.DOCUMENT_CHUNK_BYTES + 7))
    payload = p._IppDocumentPayload(b"header", document)
    writer = AsyncMock()
    await payload.write(writer)
    chunks = [call.args[0] for call in writer.write.await_args_list]
    assert payload.size == len(document) + 6
    assert chunks[0] == b"header"
    assert all(isinstance(chunk, memoryview) and chunk.obj is document for chunk in chunks[1:])
    assert all(len(chunk) <= p.DOCUMENT_CHUNK_BYTES for chunk in chunks[1:])
    assert b"".join(chunks) == b"header" + document


async def test_redirect_does_not_replay_job(aiohttp_server, socket_enabled):
    destination = AsyncMock()

    async def redirect(request):
        await request.read()
        raise web.HTTPTemporaryRedirect("/other")

    async def other(request):
        await destination()
        return web.Response(body=b"ignored")

    app = web.Application()
    app.router.add_post("/ipp/print", redirect)
    app.router.add_post("/other", other)
    server = await aiohttp_server(app)
    client = p.PrinterClient(host=server.host, port=server.port, use_tls=False)
    try:
        with pytest.raises(p.IppHttpError, match="HTTP 307"):
            await client._post_ipp(b"print request")
        destination.assert_not_called()
    finally:
        await client.async_close()


async def test_response_read_is_capped(aiohttp_server, socket_enabled, monkeypatch):
    async def oversized(request):
        await request.read()
        return web.Response(body=b"x" * 1024)

    monkeypatch.setattr(p, "MAX_RESPONSE_BYTES", 100)
    app = web.Application()
    app.router.add_post("/ipp/print", oversized)
    server = await aiohttp_server(app)
    client = p.PrinterClient(host=server.host, port=server.port, use_tls=False)
    try:
        with pytest.raises(p.IppError, match="exceeds"):
            await client._post_ipp(b"query")
    finally:
        await client.async_close()


async def test_close_during_session_initialization_does_not_leak():
    import asyncio
    import threading

    started = threading.Event()
    proceed = threading.Event()
    real_context = p._ssl_context

    def slow_context(**kwargs):
        started.set()
        assert proceed.wait(5)
        return real_context(**kwargs)

    client = p.PrinterClient(host="printer")
    with patch.object(p, "_ssl_context", side_effect=slow_context):
        initializing = asyncio.create_task(client._get_session())
        await asyncio.to_thread(started.wait, 5)
        closing = asyncio.create_task(client.async_close())
        proceed.set()
        session = await initializing
        await closing
    assert session.closed
    with pytest.raises(p.IppError, match="unloaded"):
        await client._get_session()
