// jsdom tests for the Lovelace card. Run: npm run test:card
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { JSDOM } from 'jsdom';

const here = path.dirname(fileURLToPath(import.meta.url));
const CARD_SRC = readFileSync(
  path.join(here, '..', '..', 'custom_components', 'ipp_print', 'static', 'card.js'),
  'utf8',
);
const TAG = 'ipp-print-upload-card';
const SENSOR = 'sensor.printer_current_job';

function boot() {
  const dom = new JSDOM('<home-assistant></home-assistant>', {
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  dom.window.eval(CARD_SRC);
  return dom.window;
}

function makeHass(win, { fetchImpl, states = {} } = {}) {
  const calls = { subscribe: [], fetch: [] };
  const hass = {
    states,
    fetchWithAuth: async (url, init) => {
      calls.fetch.push({ url, init });
      return fetchImpl(url, init);
    },
    connection: {
      subscribeMessage: async (cb, msg) => {
        calls.subscribe.push({ cb, msg });
        return () => { calls.unsubscribed = true; };
      },
    },
  };
  return { hass, calls };
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function mount(win, config = {}) {
  const el = win.document.createElement(TAG);
  el.setConfig(config);
  win.document.body.appendChild(el);
  return el;
}

const tick = () => new Promise((r) => setTimeout(r, 0));
// jsdom's FormData insists on a real File.
const file = (win, name, type) => new win.File(['x'], name, { type });

test('registers the element, card-picker entry, and stub config', () => {
  const win = boot();
  const C = win.customElements.get(TAG);
  assert.ok(C, 'custom element defined');
  assert.equal(C.getStubConfig().title, 'Print PDF');
  const entry = win.customCards.find((c) => c.type === TAG);
  assert.ok(entry);
  assert.equal(entry.preview, true);
});

test('renders title and updates it on later setConfig', () => {
  const win = boot();
  const el = mount(win, { title: 'Hello' });
  const title = el.shadowRoot.querySelector('.title');
  assert.equal(title.textContent, 'Hello');
  el.setConfig({ title: 'Changed' });
  assert.equal(title.textContent, 'Changed');
  // Re-render must not duplicate the shadow tree.
  assert.equal(el.shadowRoot.querySelectorAll('ha-card').length, 1);
});

test('rejects files that are neither PDF nor image', async () => {
  const win = boot();
  const el = mount(win);
  await el._upload(file(win, 'notes.txt', 'text/plain'));
  assert.match(el.shadowRoot.querySelector('.status').textContent, /Pick a PDF, JPEG, or PNG/);
});

test('upload posts to the endpoint and follows the job via subscribe_entities', async () => {
  const win = boot();
  const el = mount(win, { entity: 'sensor.office_job' });
  const { hass, calls } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ ok: true, filename: 'doc.pdf', job_id: 42, state: 'pending' }),
  });
  el.hass = hass;

  await el._upload(file(win, 'doc.pdf', 'application/pdf'));
  await tick();

  assert.equal(calls.fetch[0].url, '/api/ipp_print/print');
  assert.equal(calls.fetch[0].init.method, 'POST');
  assert.equal(el._activeJobId, 42);
  const status = el.shadowRoot.querySelector('.status');
  assert.match(status.textContent, /Submitted ✓ doc\.pdf/);

  // Non-admin-safe subscription, scoped to the configured entity.
  assert.equal(calls.subscribe.length, 1);
  const { cb, msg } = calls.subscribe[0];
  assert.equal(msg.type, 'subscribe_entities');
  assert.equal(JSON.stringify(msg.entity_ids), '["sensor.office_job"]');

  // Full add → processing with page progress; cancel link visible.
  cb({ a: { 'sensor.office_job': { s: 'processing', a: { job_id: 42, pages_done: 1, pages_total: 3 } } } });
  assert.equal(status.textContent, 'Printing page 1/3…');
  assert.ok(el.shadowRoot.querySelector('.cancel').classList.contains('show'));

  // Attribute-only diff (state unchanged) still updates progress.
  cb({ c: { 'sensor.office_job': { '+': { a: { pages_done: 2 } } } } });
  assert.equal(status.textContent, 'Printing page 2/3…');

  // Diffs for another job are ignored.
  cb({ c: { 'sensor.office_job': { '+': { s: 'pending', a: { job_id: 99 } } } } });
  assert.equal(status.textContent, 'Printing page 2/3…');

  // Terminal state with an attribute removal → completion text, unsubscribed.
  cb({ c: { 'sensor.office_job': { '+': { s: 'completed', a: { job_id: 42, pages_done: 3 } }, '-': { a: ['pages_total'] } } } });
  assert.equal(status.textContent, 'Print complete ✓ (3 pages)');
  assert.ok(status.classList.contains('ok'));
  assert.equal(calls.unsubscribed, true);
  assert.ok(!el.shadowRoot.querySelector('.cancel').classList.contains('show'));
});

test('aborted job shows the printer reason', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ ok: true, filename: 'x.pdf', job_id: 7 }),
  });
  el.hass = hass;
  await el._upload(file(win, 'x.pdf', 'application/pdf'));
  await tick();
  calls.subscribe[0].cb({ a: { [SENSOR]: { s: 'aborted', a: { job_id: 7, state_reasons: 'printer-unreachable' } } } });
  const status = el.shadowRoot.querySelector('.status');
  assert.equal(status.textContent, 'Print failed: printer-unreachable');
  assert.ok(status.classList.contains('err'));
});

test('server error message is surfaced', async () => {
  const win = boot();
  const el = mount(win);
  const { hass } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ message: 'printer does not accept image/png' }, 415),
  });
  el.hass = hass;
  await el._upload(file(win, 'a.png', 'image/png'));
  assert.equal(
    el.shadowRoot.querySelector('.status').textContent,
    'Submit failed: printer does not accept image/png',
  );
  assert.equal(el._busy, false);
});

test('falls back to the app root hass when lovelace never pushed one', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ ok: true, filename: 'a.pdf', job_id: 1 }),
  });
  win.document.querySelector('home-assistant').hass = hass;  // healed-card case
  await el._upload(file(win, 'a.pdf', 'application/pdf'));
  assert.equal(calls.fetch.length, 1);
});

test('cancel posts the active job id', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ ok: true, job_id: 5 }),
  });
  el.hass = hass;
  el._activeJobId = 5;
  await el._cancelJob();
  assert.equal(calls.fetch[0].url, '/api/ipp_print/cancel');
  assert.equal(JSON.parse(calls.fetch[0].init.body).job_id, 5);
  assert.equal(el.shadowRoot.querySelector('.status').textContent, 'Cancelling…');
});
