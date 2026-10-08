// jsdom tests for the Lovelace card. Run: npm run test:card
import { test, afterEach } from 'node:test';
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

const windows = new Set();
afterEach(() => {
  for (const win of windows) win.close();
  windows.clear();
});

function boot() {
  const dom = new JSDOM('<home-assistant></home-assistant>', {
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  windows.add(dom.window);
  dom.window.eval(CARD_SRC);
  return dom.window;
}

// Default registry: one ipp_print sensor, so cards without `entity:` resolve.
const ONE_PRINTER = { [SENSOR]: { entity_id: SENSOR, platform: 'ipp_print' } };

function makeHass(win, { fetchImpl, states = {}, entities = ONE_PRINTER } = {}) {
  const calls = { subscribe: [], fetch: [] };
  const hass = {
    states,
    entities,
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
  assert.equal(C.getStubConfig().title, 'Print');
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
  // The followed sensor is also the printer target.
  assert.equal(calls.fetch[0].init.body.get('entity_id'), 'sensor.office_job');
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

  // A newer job supersedes the sensor; do not keep claiming ours is printing.
  cb({ c: { 'sensor.office_job': { '+': { s: 'pending', a: { job_id: 99 } } } } });
  assert.equal(status.textContent, 'Job submitted (printer is tracking another job)');

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
  el._activeSensorId = SENSOR;
  await el._cancelJob();
  assert.equal(calls.fetch[0].url, '/api/ipp_print/cancel');
  const body = JSON.parse(calls.fetch[0].init.body);
  assert.equal(body.job_id, 5);
  assert.equal(body.entity_id, SENSOR);
  assert.equal(el.shadowRoot.querySelector('.status').textContent, 'Cancelling…');
});

test('discovers the only ipp_print sensor from the entity registry', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ ok: true, job_id: 1 }),
    entities: {
      'sensor.hp_current_job': { entity_id: 'sensor.hp_current_job', platform: 'ipp_print' },
      'light.desk': { entity_id: 'light.desk', platform: 'hue' },
    },
  });
  el.hass = hass;
  await el._upload(file(win, 'a.pdf', 'application/pdf'));
  await tick();
  assert.equal(calls.fetch[0].init.body.get('entity_id'), 'sensor.hp_current_job');
  assert.equal(JSON.stringify(calls.subscribe[0].msg.entity_ids), '["sensor.hp_current_job"]');
});

test('legacy sensor.printer_current_job still works without a registry hit', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ ok: true, job_id: 1 }),
    entities: {},
    states: { [SENSOR]: { state: 'idle', attributes: {} } },
  });
  el.hass = hass;
  await el._upload(file(win, 'a.pdf', 'application/pdf'));
  assert.equal(calls.fetch[0].init.body.get('entity_id'), SENSOR);
});

test('refuses to upload when several printers exist and no entity is set', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win, {
    fetchImpl: async () => jsonResponse({ ok: true }),
    entities: {
      'sensor.a_current_job': { entity_id: 'sensor.a_current_job', platform: 'ipp_print' },
      'sensor.b_current_job': { entity_id: 'sensor.b_current_job', platform: 'ipp_print' },
    },
  });
  el.hass = hass;
  await el._upload(file(win, 'a.pdf', 'application/pdf'));
  assert.equal(calls.fetch.length, 0);
  assert.match(el.shadowRoot.querySelector('.status').textContent, /set entity:/);
  assert.ok(!el._busy);
});

test('disconnect closes a subscription that resolves late', async () => {
  const win = boot();
  const el = mount(win, { entity: SENSOR });
  let resolveSubscribe;
  let unsubscribed = 0;
  el.hass = { states: {}, connection: {
    subscribeMessage: () => new Promise((resolve) => { resolveSubscribe = resolve; }),
  } };
  el._activeJobId = 7;
  const tracking = el._trackPrintProgress(SENSOR);
  el.remove();
  resolveSubscribe(() => { unsubscribed++; });
  await tracking;
  assert.equal(unsubscribed, 1);
  assert.equal(el._unsubProgress, undefined);
});

test('terminal update before subscription resolution closes the late handle', async () => {
  const win = boot();
  const el = mount(win);
  let unsubscribed = 0;
  el.hass = { states: {}, connection: {
    subscribeMessage: async (cb) => {
      cb({ a: { [SENSOR]: { s: 'completed', a: { job_id: 7 } } } });
      return () => { unsubscribed++; };
    },
  } };
  el._activeJobId = 7;
  await el._trackPrintProgress(SENSOR);
  assert.equal(unsubscribed, 1);
  assert.match(el._statusEl.textContent, /Print complete/);
  assert.equal(el._activeJobId, null);
});

test('initial terminal snapshot needs no subscription', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win, {
    states: { [SENSOR]: { state: 'completed', attributes: { job_id: 7 } } },
  });
  el.hass = hass;
  el._activeJobId = 7;
  await el._trackPrintProgress(SENSOR);
  assert.equal(calls.subscribe.length, 0);
  assert.match(el._statusEl.textContent, /Print complete/);
});

test('active and paused jobs remain subscribed beyond the initial safety window', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win);
  el.hass = hass;
  el._activeJobId = 7;
  const timers = new Map();
  let nextTimer = 100000;
  const realClearTimeout = win.clearTimeout.bind(win);
  win.setTimeout = (cb, ms) => { const id = ++nextTimer; timers.set(id, { cb, ms }); return id; };
  win.clearTimeout = (id) => {
    if (!timers.delete(id)) realClearTimeout(id);
  };
  await el._trackPrintProgress(SENSOR);
  assert.equal(timers.size, 1);
  calls.subscribe[0].cb({ a: { [SENSOR]: {
    s: 'processing-stopped', a: { job_id: 7, state_reasons: 'media-empty' },
  } } });
  assert.equal(el._statusEl.textContent, 'Printing paused: media-empty');
  assert.ok(el._cancelEl.classList.contains('show'));
  assert.equal(calls.unsubscribed, undefined);
  assert.equal(timers.size, 0, 'first-snapshot timeout cleared for an active job');
});

test('previous subscription cannot overwrite the next job', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win);
  el.hass = hass;
  el._activeJobId = 7;
  await el._trackPrintProgress(SENSOR);
  const old = calls.subscribe[0].cb;
  el._activeJobId = 8;
  await el._trackPrintProgress(SENSOR);
  calls.subscribe[1].cb({ a: { [SENSOR]: { s: 'processing', a: { job_id: 8 } } } });
  old({ a: { [SENSOR]: { s: 'completed', a: { job_id: 7 } } } });
  assert.equal(el._statusEl.textContent, 'Printing…');
  assert.equal(el._activeJobId, 8);
});

test('late cancel response does not overwrite completion', async () => {
  const win = boot();
  const el = mount(win);
  let resolveCancel;
  const { hass, calls } = makeHass(win, {
    fetchImpl: () => new Promise((resolve) => { resolveCancel = resolve; }),
  });
  el.hass = hass;
  el._activeJobId = 7;
  el._activeSensorId = SENSOR;
  await el._trackPrintProgress(SENSOR);
  const cancel = el._cancelJob();
  calls.subscribe[0].cb({ a: { [SENSOR]: { s: 'completed', a: { job_id: 7 } } } });
  resolveCancel(jsonResponse({ ok: true }));
  await cancel;
  assert.match(el._statusEl.textContent, /Print complete/);
});

test('healed card uses the latest app-root hass', () => {
  const win = boot();
  const el = mount(win);
  const old = { states: {} };
  const live = { states: { [SENSOR]: {} } };
  el.hass = old;
  win.document.querySelector('home-assistant').hass = live;
  assert.equal(el._getHass(), live);
});

test('rejects oversized files before posting', async () => {
  const win = boot();
  const el = mount(win);
  await el._upload({ size: 50 * 1024 * 1024 + 1, name: 'large.pdf' });
  assert.match(el._statusEl.textContent, /50 MiB/);
});

test('removed sensor ends tracking and hides cancel', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win);
  el.hass = hass;
  el._activeJobId = 7;
  await el._trackPrintProgress(SENSOR);
  calls.subscribe[0].cb({ r: [SENSOR] });
  assert.equal(calls.unsubscribed, true);
  assert.match(el._statusEl.textContent, /sensor unavailable/);
  assert.ok(!el._cancelEl.classList.contains('show'));
});


test('a pending cancel for an older job cannot block cancellation of the next job', async () => {
  const win = boot();
  const el = mount(win);
  const resolvers = [];
  const { hass, calls } = makeHass(win, {
    fetchImpl: () => new Promise((resolve) => { resolvers.push(resolve); }),
  });
  el.hass = hass;
  el._activeJobId = 7;
  el._progressGeneration = 1;
  const oldCancel = el._cancelJob();
  el._activeJobId = 8;
  el._progressGeneration = 2;
  const newCancel = el._cancelJob();
  assert.equal(calls.fetch.length, 2);
  resolvers[0](jsonResponse({ ok: true }));
  await oldCancel;
  assert.equal(el._cancelPending.jobId, 8);
  resolvers[1](jsonResponse({ ok: true }));
  await newCancel;
  assert.equal(el._cancelPending, null);
});

test('file selection stages locally and Print submits once with file changes locked', async () => {
  const win = boot();
  const el = mount(win);
  let respond;
  const { hass, calls } = makeHass(win, { fetchImpl: () => new Promise(resolve => { respond = resolve; }) });
  el.hass = hass;
  const document = file(win, 'report.pdf', 'application/pdf');
  el._pick();
  const input = win.document.querySelector('input[type=file]');
  assert.ok(input?.isConnected);
  Object.defineProperty(input, 'files', { value: [document] });
  input.dispatchEvent(new win.Event('change'));
  assert.equal(calls.fetch.length, 0);
  assert.equal(el._stagedFile, document);
  assert.equal(el._fileNameEl.textContent, 'report.pdf');
  assert.equal(el._primaryEl.textContent, 'Print');
  el._primaryEl.click();
  el._primaryEl.click();
  el.shadowRoot.querySelector('.clear').click();
  el._stageFile(file(win, 'other.pdf', 'application/pdf'));
  assert.equal(el._stagedFile, document);
  assert.equal(calls.fetch.length, 1);
  assert.equal(calls.fetch[0].init.body.get('file').name, 'report.pdf');
  respond(jsonResponse({ job_id: 42, filename: 'report.pdf' }));
  await tick();
  assert.equal(el._stagedFile, null, 'release local file after acceptance');
  assert.equal(el._primaryEl.disabled, true, 'active print blocks another submission');
  el._pick();
  assert.equal(win.document.querySelector('input[type=file]'), null);
  calls.subscribe[0].cb({ a: { [SENSOR]: { s: 'completed', a: { job_id: 42 } } } });
  assert.equal(el._primaryEl.disabled, false);
  assert.equal(el._primaryEl.textContent, 'Choose file');
});

test('canceling replacement preserves selection; Clear discards without uploading', () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win);
  el.hass = hass;
  const document = file(win, 'original.pdf', 'application/pdf');
  el._stageFile(document);
  el.shadowRoot.querySelector('.replace').click();
  win.document.querySelector('input[type=file]').dispatchEvent(new win.Event('cancel'));
  assert.equal(el._stagedFile, document);
  assert.equal(win.document.querySelector('input[type=file]'), null);
  assert.equal(el._primaryEl.textContent, 'Print');
  el.shadowRoot.querySelector('.clear').click();
  assert.equal(el._stagedFile, null);
  assert.equal(el._primaryEl.textContent, 'Choose file');
  assert.equal(calls.fetch.length, 0);
});

test('invalid replacement retains a valid staged document', () => {
  const win = boot();
  const el = mount(win);
  const document = file(win, 'valid.pdf', 'application/pdf');
  el._stageFile(document);
  el._stageFile(file(win, 'bad.txt', 'text/plain'));
  assert.equal(el._stagedFile, document);
  assert.match(el._statusEl.textContent, /Pick a PDF/);
  assert.equal(el._fileNameEl.textContent, 'valid.pdf');
});

test('known validation rejection retains staged file; uncertain submission clears it', async () => {
  for (const [response, retained] of [
    [jsonResponse({ message: 'printer does not accept image/png' }, 415), true],
    [jsonResponse({ message: 'gateway timeout' }, 504), false],
    [jsonResponse({ ok: true }), false],
    [new Error('connection lost'), false],
  ]) {
    const win = boot();
    const el = mount(win);
    const { hass, calls } = makeHass(win, { fetchImpl: async () => {
      if (response instanceof Error) throw response;
      return response;
    } });
    el.hass = hass;
    const document = file(win, 'test.png', 'image/png');
    el._stageFile(document);
    await el._upload(document);
    assert.equal(el._stagedFile, retained ? document : null);
    assert.equal(calls.fetch.length, 1);
    assert.equal(el._primaryEl.disabled, false);
    if (!retained) assert.match(el._statusEl.textContent, /Check the printer queue/);
  }
});

test('card surface and child keyboard events do not open a file picker', () => {
  const win = boot();
  const el = mount(win);
  const card = el.shadowRoot.querySelector('ha-card');
  assert.equal(card.getAttribute('role'), null);
  card.click();
  card.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  el._primaryEl.dispatchEvent(new win.KeyboardEvent('keydown', { key: ' ', bubbles: true }));
  assert.equal(win.document.querySelector('input[type=file]'), null);
  assert.equal(el._cancelEl.tagName, 'BUTTON');
});

test('disconnect cleans an open picker and a lost job tracker unlocks selection', async () => {
  const win = boot();
  const el = mount(win);
  el._pick();
  el.remove();
  assert.equal(win.document.querySelector('input[type=file]'), null);
  win.document.body.appendChild(el);
  const { hass, calls } = makeHass(win);
  el.hass = hass;
  el._activeJobId = 8;
  await el._trackPrintProgress(SENSOR);
  calls.subscribe[0].cb({ r: [SENSOR] });
  assert.equal(el._activeJobId, null);
  assert.equal(el._primaryEl.disabled, false);
  assert.match(el._statusEl.textContent, /sensor unavailable/);
});

test('native lifecycle hooks close an established subscription and reconnect once', async () => {
  const win = boot();
  const el = mount(win);
  const { hass, calls } = makeHass(win);
  el.hass = hass;
  el._activeJobId = 9;
  el._activeSensorId = SENSOR;
  await el._trackPrintProgress(SENSOR);
  assert.equal(calls.subscribe.length, 1);
  el.remove();
  assert.equal(calls.unsubscribed, true);
  win.document.body.appendChild(el);
  await tick();
  assert.equal(calls.subscribe.length, 2);
});
