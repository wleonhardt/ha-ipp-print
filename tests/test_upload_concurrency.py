"""Bound document preparation across HTTP uploads, services and printers."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

import custom_components.ipp_print as integration
from custom_components.ipp_print.const import DOMAIN
from custom_components.ipp_print.coordinator import JobCoordinator

from test_views import PDF, OK_RESULT, _form, _setup, _setup_two


@pytest.mark.parametrize("two_printers", [False, True])
async def test_concurrent_http_submission_rejected_without_resend(hass, hass_client, two_printers):
    await (_setup_two(hass) if two_printers else _setup(hass))
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def submit(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return OK_RESULT

    first_target = "sensor.test_printer_current_job" if two_printers else None
    next_target = "sensor.test_printer_current_job_2" if two_printers else None
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(side_effect=submit)), \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        client = await hass_client()
        first = asyncio.create_task(client.post(
            "/api/ipp_print/print", data=_form(PDF, entity_id=first_target)))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            second = await client.post(
                "/api/ipp_print/print", data=_form(PDF, entity_id=next_target))
            assert second.status == 409
            assert (await second.json())["job_may_exist"] is False
            assert calls == 1
            release.set()
            assert (await first).status == 200
            assert calls == 1  # Refused requests are not queued or replayed.
            retry = await client.post(
                "/api/ipp_print/print", data=_form(PDF, entity_id=next_target))
            assert retry.status == 200 and calls == 2
        finally:
            release.set()
            await first


@pytest.mark.parametrize("first_kind", ["http", "service"])
async def test_upload_and_service_share_document_slot(hass, hass_client, tmp_path, first_kind):
    await _setup(hass)
    path = tmp_path / "document.pdf"
    path.write_bytes(PDF)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def submit(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return OK_RESULT

    async def service():
        return await hass.services.async_call(
            DOMAIN, "print_file", {"path": str(path)}, blocking=True, return_response=True)

    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(side_effect=submit)), \
            patch.object(JobCoordinator, "_ensure_poll_loop"), \
            patch.object(integration, "_read_file_capped", wraps=integration._read_file_capped) as read:
        client = await hass_client()
        first = asyncio.create_task(client.post("/api/ipp_print/print", data=_form(PDF))
                                    if first_kind == "http" else service())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            if first_kind == "http":
                with pytest.raises(HomeAssistantError, match="Another document"):
                    await service()
                read.assert_not_called()
            else:
                second = await client.post("/api/ipp_print/print", data=_form(PDF))
                assert second.status == 409
                assert read.call_count == 1
            assert calls == 1
        finally:
            release.set()
            await first


def _blocked_upload(entered, release):
    from types import SimpleNamespace

    chunks = [PDF, b""]

    async def read_chunk(_size):
        entered.set()
        await release.wait()
        return chunks.pop(0)

    part = SimpleNamespace(name="file", filename="doc.pdf", read_chunk=AsyncMock(side_effect=read_chunk))
    reader = SimpleNamespace(next=AsyncMock(side_effect=[part, None]))
    return SimpleNamespace(multipart=AsyncMock(return_value=reader))


async def test_busy_refuses_before_reading_body_and_keeps_read_only_routes_available(hass, hass_client):
    from types import SimpleNamespace

    await _setup(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    view = integration.PrintView(hass)
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)), \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        first = asyncio.create_task(view.post(_blocked_upload(entered, release)))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            refused = SimpleNamespace(multipart=AsyncMock(side_effect=AssertionError("body read")))
            response = await view.post(refused)
            assert response.status == 409 and response.keep_alive is False
            refused.multipart.assert_not_awaited()
            client = await hass_client()
            assert (await client.get("/api/ipp_print/capabilities")).status == 200
            assert (await client.post("/api/ipp_print/cancel", json={"job_id": 999})).status == 404
        finally:
            release.set()
            assert (await first).status == 200


@pytest.mark.parametrize("failure", ["malformed", "oversized", "format", "validation", "ambiguous"])
async def test_failed_upload_releases_slot_without_automatic_resend(
    hass, hass_client, monkeypatch, validation_result, failure,
):
    await _setup(hass)
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        client = await hass_client()
        data = _form(PDF)
        expected = 400
        if failure == "malformed":
            data = b"not multipart"
        elif failure == "oversized":
            monkeypatch.setattr(integration, "MAX_UPLOAD_BYTES", len(PDF))
            data, expected = _form(PDF + b"x"), 413
        elif failure == "format":
            data, expected = _form(b"GIF89a"), 415
        elif failure == "validation":
            data.add_field("copies", "1")
            validation_result.side_effect = ValueError("settings rejected")
        else:
            pj.side_effect = TimeoutError()
            expected = 502
        failed = await client.post("/api/ipp_print/print", data=data)
        assert failed.status == expected
        assert pj.await_count == (1 if failure == "ambiguous" else 0)
        if failure == "ambiguous":
            assert (await failed.json())["job_may_exist"] is True
        # Read-only requests never replay a refused/uncertain submission.
        assert (await client.get("/api/ipp_print/capabilities")).status == 200
        assert pj.await_count == (1 if failure == "ambiguous" else 0)
        pj.side_effect = validation_result.side_effect = None
        retry = await client.post("/api/ipp_print/print", data=_form(PDF))
        assert retry.status == 200
        assert pj.await_count == (2 if failure == "ambiguous" else 1)


@pytest.mark.parametrize("kind", ["cancel", "disconnect"])
async def test_interrupted_body_releases_slot(hass, hass_client, kind):
    await _setup(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    request = _blocked_upload(entered, release)
    if kind == "disconnect":
        async def disconnected():
            raise ConnectionResetError("upload disconnected")
        request.multipart.side_effect = disconnected
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        first = asyncio.create_task(integration.PrintView(hass).post(request))
        if kind == "cancel":
            await asyncio.wait_for(entered.wait(), 2)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        else:
            assert (await first).status == 400
        pj.assert_not_awaited()
        client = await hass_client()
        assert (await client.post("/api/ipp_print/print", data=_form(PDF))).status == 200
        pj.assert_awaited_once()


async def test_real_stalled_upload_times_out_and_releases_slot(hass, hass_client, monkeypatch):
    import aiohttp

    await _setup(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    original = aiohttp.BodyPartReader.read_chunk

    async def observed(part, *args, **kwargs):
        entered.set()
        return await original(part, *args, **kwargs)

    async def stream():
        yield PDF
        await release.wait()

    monkeypatch.setattr(integration, "_UPLOAD_TIMEOUT_SECONDS", 0.25)
    monkeypatch.setattr(aiohttp.BodyPartReader, "read_chunk", observed)
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        client = await hass_client()
        first = asyncio.create_task(client.post("/api/ipp_print/print", data=_form(stream())))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            busy = await client.post("/api/ipp_print/print", data=_form(PDF))
            assert busy.status == 409
            response = await asyncio.wait_for(first, 2)
            assert response.status == 408 and (await response.json())["job_may_exist"] is False
            assert response.headers.get("Connection") == "close"
            pj.assert_not_awaited()
            retry = await client.post("/api/ipp_print/print", data=_form(PDF))
            assert retry.status == 200
            pj.assert_awaited_once()
        finally:
            release.set()
            if not first.done():
                first.cancel()
            await asyncio.gather(first, return_exceptions=True)


async def test_upload_deadline_does_not_time_out_printer_submission(hass, hass_client, monkeypatch):
    await _setup(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def submit(**kwargs):
        entered.set()
        await release.wait()
        return OK_RESULT

    monkeypatch.setattr(integration, "_UPLOAD_TIMEOUT_SECONDS", 0.01)
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(side_effect=submit)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        client = await hass_client()
        first = asyncio.create_task(client.post("/api/ipp_print/print", data=_form(PDF)))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(first), 0.04)
            release.set()
            assert (await first).status == 200
            pj.assert_awaited_once()
        finally:
            release.set()
            await first


@pytest.mark.parametrize("worker_fails", [False, True])
async def test_canceled_service_keeps_slot_until_executor_read_finishes(
    hass, hass_client, tmp_path, worker_fails,
):
    import threading
    from homeassistant.core import ServiceCall

    await _setup(hass)
    path = tmp_path / "document.pdf"
    path.write_bytes(PDF)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    entered, release = threading.Event(), threading.Event()
    read_calls = 0

    def read(_path):
        nonlocal read_calls
        read_calls += 1
        entered.set()
        assert release.wait(5)
        if worker_fails:
            raise OSError("read failed")
        return PDF

    # HA's test fixture runs Mock executor targets inline; use a real worker.
    with patch.object(integration, "_read_file_capped", new=read), \
            patch.object(integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        handler = integration._make_print_file_handler(hass)
        call = ServiceCall(hass, DOMAIN, "print_file", {"path": str(path)})
        first = asyncio.create_task(handler(call))
        try:
            async with asyncio.timeout(2):
                while not entered.is_set():
                    if first.done():
                        await first
                    await asyncio.sleep(0.01)
            first.cancel()
            await asyncio.sleep(0)
            first.cancel()  # A second cancellation still cannot stop a worker.
            client = await hass_client()
            busy = await client.post("/api/ipp_print/print", data=_form(PDF))
            assert busy.status == 409 and not first.done()
            with pytest.raises(HomeAssistantError, match="Another document"):
                await handler(call)
            assert read_calls == 1
            pj.assert_not_awaited()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await first
            retry = await client.post("/api/ipp_print/print", data=_form(PDF))
            assert retry.status == 200
            pj.assert_awaited_once()
        finally:
            release.set()
            await asyncio.gather(first, return_exceptions=True)


@pytest.mark.parametrize("error", [FileNotFoundError(), OSError("read failed"), ValueError("too big")])
async def test_service_read_failure_releases_slot(hass, hass_client, tmp_path, error):
    await _setup(hass)
    path = tmp_path / "document.pdf"
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    with patch.object(integration, "_read_file_capped", side_effect=error), \
            patch.object(integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(DOMAIN, "print_file", {"path": str(path)}, blocking=True)
        pj.assert_not_awaited()
        client = await hass_client()
        assert (await client.post("/api/ipp_print/print", data=_form(PDF))).status == 200
        pj.assert_awaited_once()


async def test_reload_cannot_reset_an_upload_slot(hass, hass_client):
    entry = await _setup(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    view = integration.PrintView(hass)
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        first = asyncio.create_task(view.post(_blocked_upload(entered, release)))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert await hass.config_entries.async_reload(entry.entry_id)
            client = await hass_client()
            assert (await client.post("/api/ipp_print/print", data=_form(PDF))).status == 409
            pj.assert_not_awaited()
            release.set()
            assert (await first).status == 200
            assert (await client.post("/api/ipp_print/print", data=_form(PDF))).status == 200
            assert pj.await_count == 2
        finally:
            release.set()
            await first


@pytest.mark.parametrize("kind", ["http", "service"])
async def test_canceled_submission_releases_slot_without_resend(hass, hass_client, tmp_path, kind):
    from homeassistant.core import ServiceCall

    await _setup(hass)
    path = tmp_path / "document.pdf"
    path.write_bytes(PDF)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    entered, release = asyncio.Event(), asyncio.Event()

    async def submit(**kwargs):
        entered.set()
        await release.wait()
        return OK_RESULT

    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock(side_effect=submit)) as pj, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        if kind == "service":
            call = ServiceCall(hass, DOMAIN, "print_file", {"path": str(path)})
            first = asyncio.create_task(integration._make_print_file_handler(hass)(call))
        else:
            body_entered, body_release = asyncio.Event(), asyncio.Event()
            body_release.set()
            first = asyncio.create_task(integration.PrintView(hass).post(
                _blocked_upload(body_entered, body_release)))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            client = await hass_client()
            assert (await client.get("/api/ipp_print/capabilities")).status == 200
            pj.assert_awaited_once()
            release.set()
            assert (await client.post("/api/ipp_print/print", data=_form(PDF))).status == 200
            assert pj.await_count == 2
        finally:
            release.set()
            await asyncio.gather(first, return_exceptions=True)
