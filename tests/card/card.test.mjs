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
test('healing rebuilds the HA-owned card so state updates cannot restore the error', async () => {
  const win = boot();
  const doc = win.document;
  const host = doc.querySelector('home-assistant');
  host.hass = { states: {} };
  const wrapper = doc.createElement('hui-card');
  wrapper.config = wrapper._elementConfig = { type: 'custom:' + TAG, title: 'Recovered' };
  const error = doc.createElement('hui-error-card');
  error._config = { type: 'error', message: "Custom element doesn't exist: " + TAG + '.' };
  wrapper._element = error;
  wrapper.appendChild(error);
  let loads = 0;
  wrapper.load = () => {
    loads++;
    const replacement = doc.createElement(TAG);
    replacement.setConfig(wrapper.config);
    replacement.hass = host.hass;
    wrapper._element.replaceWith(replacement);
    wrapper._element = replacement;
  };
  host.appendChild(wrapper);
  await new Promise(resolve => setTimeout(resolve, 80));
  assert.equal(loads, 1);
  assert.equal(wrapper._element.localName, TAG);
  assert.equal(wrapper.querySelector(TAG), wrapper._element);
  assert.equal(wrapper._element.shadowRoot.querySelector('.title').textContent, 'Recovered');
  // HA updates and shows its stored element, not whichever node is in the DOM.
  const nextHass = { states: {} };
  wrapper._element.hass = nextHass;
  if (!wrapper._element.parentElement) wrapper.appendChild(wrapper._element);
  assert.equal(wrapper.children.length, 1);
  assert.equal(wrapper.querySelector('hui-error-card'), null);
});
const SENSOR = 'sensor.printer_current_job';

const windows = new Set();
afterEach(() => {
  for (const win of windows) win.close();
  windows.clear();
});

function boot(translations = {}, setup) {
  const dom = new JSDOM('<home-assistant></home-assistant>', {
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  windows.add(dom.window);
  // jsdom has no native dialog lifecycle; model its asynchronous close event.
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function () {
    if (!this.open) return;
    this.open = false;
    dom.window.setTimeout(() => this.dispatchEvent(new dom.window.Event('close')), 0);
  };
  setup?.(dom.window);
  dom.window.eval(CARD_SRC + '\nObject.assign(CARD_TRANSLATIONS, ' + JSON.stringify(translations) + ');');
  return dom.window;
}

// Default registry: one ipp_print sensor, so cards without `entity:` resolve.
const ONE_PRINTER = { [SENSOR]: { entity_id: SENSOR, platform: 'ipp_print' } };

function makeHass(win, { fetchImpl, capabilitiesImpl, states = {}, entities = ONE_PRINTER } = {}) {
  const calls = { subscribe: [], fetch: [], capabilities: [] };
  const hass = {
    states,
    entities,
    fetchWithAuth: async (url, init) => {
      if (url.startsWith('/api/ipp_print/capabilities?')) {
        calls.capabilities.push({ url, init });
        return capabilitiesImpl ? capabilitiesImpl(url, init) : jsonResponse({}, 404);
      }
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

function push(el, hass, state, attributes = {}, id = SENSOR) {
  hass.states = { ...hass.states };
  if (state === null) delete hass.states[id];
  else hass.states[id] = { entity_id: id, state, attributes };
  el.hass = { ...hass };
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

test('upload and remote jobs follow HA state without extra subscriptions', async () => {
  const win = boot(), el = mount(win, { entity: 'sensor.office_job' });
  const { hass, calls } = makeHass(win, { fetchImpl: async () => jsonResponse({ job_id: 42, filename: 'doc.pdf' }) });
  el.hass = hass;
  await el._upload(file(win, 'doc.pdf', 'application/pdf'));
  assert.equal(calls.fetch[0].url, '/api/ipp_print/print');
  assert.equal(calls.fetch[0].init.body.get('entity_id'), 'sensor.office_job');
  assert.equal(el._activeJobId, 42);
  assert.equal(calls.subscribe.length, 0);
  push(el, hass, 'processing', { job_id: 42, pages_done: 0, pages_total: 3 }, 'sensor.office_job');
  assert.equal(el._statusEl.textContent, 'Printing… 0 pages printed');
  push(el, hass, 'processing', { job_id: 42, pages_done: 2, pages_total: 3 }, 'sensor.office_job');
  assert.equal(el._statusEl.textContent, 'Printing… 2 pages printed');
  push(el, hass, 'pending', { job_id: 99 }, 'sensor.office_job');
  assert.equal(el._activeJobId, 99);
  assert.equal(el._statusEl.textContent, 'Queued for printer…');
  push(el, hass, 'completed', { job_id: 99, pages_done: 3 }, 'sensor.office_job');
  assert.equal(el._statusEl.textContent, 'Print complete ✓ (3 pages)');
  assert.equal(el._activeJobId, null);
  assert.equal(el._fileNameEl.textContent, 'PDF or image');
});

test('aborted job shows the device reason without submitting locally', async () => {
  const win = boot(), el = mount(win);
  const { hass, calls } = makeHass(win);
  push(el, hass, 'aborted', { job_id: 7, state_reasons: 'job-canceled-at-device' });
  assert.equal(el._statusEl.textContent, 'Print failed: job-canceled-at-device');
  assert.equal(calls.fetch.length, 0);
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
  assert.equal(el._activeSensorId, 'sensor.hp_current_job');
  assert.equal(calls.subscribe.length, 0);
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

test('reload adopts a running external job and never opens an extra subscription', async () => {
  const win = boot(), el = mount(win);
  const { hass, calls } = makeHass(win);
  push(el, hass, 'processing', { job_id: 7, filename: 'external.pdf', pages_done: 1 });
  assert.equal(el._activeJobId, 7);
  assert.equal(el._fileNameEl.textContent, 'external.pdf');
  const reloaded = mount(win); reloaded.hass = hass;
  assert.equal(reloaded._activeJobId, 7);
  assert.equal(reloaded._statusEl.textContent, el._statusEl.textContent);
  assert.equal(calls.subscribe.length, 0);
  assert.equal(calls.fetch.length, 0);
});

test('a terminal pushed snapshot wins over a delayed accepted submission', async () => {
  const win = boot(), el = mount(win);
  let resolve;
  const { hass } = makeHass(win, { fetchImpl: () => new Promise(r => { resolve = r; }) });
  el.hass = hass;
  const upload = el._upload(file(win, 'done.pdf', 'application/pdf')); await tick();
  push(el, hass, 'completed', { job_id: 7, pages_done: 1 });
  resolve(jsonResponse({ job_id: 7, filename: 'done.pdf' })); await upload;
  assert.equal(el._activeJobId, null);
  assert.equal(el._fileNameEl.textContent, 'PDF or image');
  assert.match(el._statusEl.textContent, /Print complete/);
});

test('completion without an observed count does not invent printed pages', async () => {
  const win = boot(), el = mount(win);
  const { hass, calls } = makeHass(win);
  push(el, hass, 'completed', { job_id: 7, pages_total: 12 });
  assert.equal(el._statusEl.textContent, 'Print complete ✓');
  assert.equal(calls.subscribe.length, 0);
});

test('active and paused jobs have no frontend expiry deadline', async () => {
  const win = boot(), el = mount(win);
  const { hass } = makeHass(win);
  push(el, hass, 'processing', { job_id: 7 });
  assert.equal(el._progressSafety, null);
  push(el, hass, 'processing-stopped', { job_id: 7, state_reasons: 'media-empty' });
  assert.equal(el._statusEl.textContent, 'Printing paused: media-empty');
  assert.equal(el._progressSafety, null);
  assert.ok(el._cancelEl.classList.contains('show'));
});

test('a late cancel body cannot affect another printer with the same job ID', async () => {
  const win = boot(), el = mount(win, { entity: SENSOR });
  let body;
  const { hass, calls } = makeHass(win, { fetchImpl: async () => ({ok:false,text:()=>new Promise(r=>{body=r;})}) });
  push(el, hass, 'processing', { job_id: 7, submitted_at: 'old' });
  const cancel = el._cancelJob(); await tick();
  push(el, hass, 'completed', { job_id: 7, submitted_at: 'old' });
  el.setConfig({entity:'sensor.other_job'});
  push(el, hass, 'processing', { job_id: 7, submitted_at: 'new', filename:'new.pdf' }, 'sensor.other_job');
  body('old failure'); await cancel;
  assert.equal(el._activeSensorId, 'sensor.other_job');
  assert.equal(el._statusEl.textContent, 'Printing…');
  assert.equal(el._fileNameEl.textContent, 'new.pdf');
  const request = JSON.parse(calls.fetch[0].init.body);
  assert.equal(request.entity_id, SENSOR);
  assert.equal(request.submitted_at, 'old');
});

test('late cancel response does not overwrite completion', async () => {
  const win = boot(), el = mount(win);
  let resolve;
  const { hass } = makeHass(win, { fetchImpl:()=>new Promise(r=>{resolve=r;}) });
  push(el, hass, 'processing', { job_id:7 });
  const cancel=el._cancelJob();
  push(el, hass, 'completed', { job_id:7 });
  resolve(jsonResponse({ok:true}));await cancel;
  assert.match(el._statusEl.textContent,/Print complete/);
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

test('removed sensor reports unknown outcome and hides cancel', async () => {
  const win=boot(),el=mount(win);const {hass}=makeHass(win);
  push(el,hass,'processing',{job_id:7});push(el,hass,null);
  assert.equal(el._activeJobId,null);
  assert.match(el._statusEl.textContent,/status unavailable.*queue/);
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
  assert.equal(el._cancelPending.token, el._jobToken());
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
  await tick(); // Settings are checked before the document POST.
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
  push(el, hass, 'completed', {job_id:42});
  assert.equal(el._primaryEl.disabled, false);
  assert.equal(el._primaryEl.textContent, 'Choose file');
  assert.equal(el._fileNameEl.textContent, 'PDF or image');
  el._stageFile(file(win, 'next.pdf', 'application/pdf'));
  push(el, hass, 'completed', {job_id:42});
  assert.equal(el._fileNameEl.textContent, 'next.pdf');
  el.shadowRoot.querySelector('.clear').click();
  assert.equal(el._fileNameEl.textContent, 'PDF or image', 'finished filename never returns');
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

test('disconnect cleans an open picker; reconnect recovers the latest job', async () => {
  const win=boot(),el=mount(win);const {hass}=makeHass(win);
  el._pick();el.remove();assert.equal(win.document.querySelector('input[type=file]'),null);
  push(el,hass,'processing',{job_id:8});
  win.document.body.append(el);
  assert.equal(el._activeJobId,8);
  assert.ok(el._primaryEl.disabled);
});

test('repeated detach and reconnect preserve staged files without submitting', async () => {
  const win=boot(),el=mount(win);const {hass,calls}=makeHass(win);el.hass=hass;
  const staged=file(win,'kept.pdf','application/pdf');el._stageFile(staged);
  for(let i=0;i<3;i++){el.remove();win.document.body.append(el);}
  assert.equal(el._stagedFile,staged);assert.equal(calls.fetch.length,0);
  assert.equal(calls.subscribe.length,0);
});

function optionCaps(entity = SENSOR) {
  return {schema_version:1,domain:'ipp_print',entity_id:entity,status:'fresh',
    request_options:['copies','sides','media','media_source','color_mode','quality'],
    supported:{copies_max:5,sides:['one-sided','two-sided-long-edge'],media:['iso_a4_210x297mm'],
      media_sources:['auto','tray-1'],color_modes:['monochrome','color'],qualities:[3,4]}};
}
function changeOption(win, el, name, value) {
  const field=el._optionFields[name];field.value=value;field.dispatchEvent(new win.Event('change'));return field;
}
test('new print backend receives explicit defaults and complete selected settings', async () => {
  const win=boot(),el=mount(win);
  const {hass,calls}=makeHass(win,{capabilitiesImpl:async()=>jsonResponse(optionCaps()),
    fetchImpl:async()=>jsonResponse({job_id:23,filename:'settings.pdf',warning:'Printer substituted a setting.'})});
  el.hass=hass;const chosen=file(win,'settings.pdf','application/pdf');el._stageFile(chosen);await tick();
  el._toggleOptions(true);
  changeOption(win,el,'media','iso_a4_210x297mm');changeOption(win,el,'media_source','tray-1');
  changeOption(win,el,'color_mode','monochrome');changeOption(win,el,'quality','3');
  await el._upload(chosen);const body=calls.fetch[0].init.body;
  assert.equal(body.get('copies'),'1');assert.equal(body.get('sides'),'one-sided');
  assert.equal(body.get('media_source'),'tray-1');assert.equal(body.get('quality'),'3');
  assert.ok(calls.capabilities.some(call=>/document_format=application%2Fpdf/.test(call.url)));
  assert.match(el._warningEl.textContent,/substituted/);
  assert.equal(el._optionFields.media.disabled,true);
});
test('print dialog preserves focus, validates copies and defers editor changes during an upload', async () => {
  const win=boot(),el=mount(win);let finish;
  const {hass}=makeHass(win,{capabilitiesImpl:async()=>jsonResponse(optionCaps()),
    fetchImpl:()=>new Promise(resolve=>{finish=resolve;})});
  el.hass=hass;const chosen=file(win,'settings.pdf','application/pdf');el._stageFile(chosen);await tick();
  el._toggleOptions(true);const copies=changeOption(win,el,'copies','6');
  assert.equal(el._primaryEl.disabled,true);changeOption(win,el,'copies','2');copies.focus();
  el.hass={...hass};assert.equal(el.shadowRoot.activeElement,copies);assert.equal(copies.value,'2');
  el.setConfig({title:'Office'});assert.equal(el._settings.copies,2);
  const upload=el._upload(chosen);await tick();el.setConfig({copies:3});assert.equal(el._settings.copies,2);
  finish(jsonResponse({message:'No print job was submitted'},400));await upload;
  assert.equal(el._stagedFile,chosen);assert.equal(el._settings.copies,3);
  copies.dispatchEvent(new win.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert.equal(el._optionsPanel.hidden,true);assert.equal(el.shadowRoot.activeElement,el._optionsButton);
});
test('printer selection ignores stale capabilities and sends the chosen queue', async () => {
  const win=boot(),el=mount(win);let first;
  const ids=['sensor.first_job','sensor.second_job'];
  const {hass,calls}=makeHass(win,{entities:Object.fromEntries(ids.map(entity_id=>[entity_id,{entity_id,platform:'ipp_print'}])),
    capabilitiesImpl:async url=>url.includes('first_job')?new Promise(resolve=>{first=resolve;}):jsonResponse(optionCaps(ids[1])),
    fetchImpl:async()=>jsonResponse({job_id:9})});
  el.hass=hass;el._toggleOptions(true);
  changeOption(win,el,'entity_id',ids[0]);changeOption(win,el,'entity_id',ids[1]);await tick();
  first(jsonResponse(optionCaps(ids[0])));await tick();
  assert.equal(el._optionCapabilities.body.entity_id,ids[1]);
  el._stageFile(file(win,'queue.pdf','application/pdf'));await tick();await el._upload(el._stagedFile);
  assert.equal(calls.fetch[0].init.body.get('entity_id'),ids[1]);
});
test('file change retains unsupported selected values with an explanation instead of silently clearing them', async () => {
  const win=boot(),el=mount(win);
  const {hass}=makeHass(win,{capabilitiesImpl:async url=>{const caps=optionCaps();if(url.includes('image%2Fpng'))caps.supported.color_modes=['monochrome'];return jsonResponse(caps);}});
  el.hass=hass;el._stageFile(file(win,'color.pdf','application/pdf'));await tick();
  changeOption(win,el,'color_mode','color');el._stageFile(file(win,'gray.png','image/png'));await tick();
  assert.equal(el._settings.color_mode,'color');assert.equal(el._primaryEl.disabled,true);
  assert.match(el._optionHelp.textContent,/unavailable/);
  changeOption(win,el,'color_mode','');assert.equal(el._primaryEl.disabled,false);
});

test('a confirmed preflight connection failure retains the selected document', async () => {
  const win=boot(),el=mount(win);
  const {hass}=makeHass(win,{fetchImpl:async()=>jsonResponse({message:'No print job was submitted',job_may_exist:false},502)});
  el.hass=hass;const chosen=file(win,'retry.pdf','application/pdf');el._stageFile(chosen);
  await el._upload(chosen);assert.equal(el._stagedFile,chosen);
});

test('a capability outage never silently discards an explicit copy count', async () => {
  const win=boot(),el=mount(win,{copies:3});
  const {hass,calls}=makeHass(win,{fetchImpl:async()=>jsonResponse({job_id:2})});
  el.hass=hass;const chosen=file(win,'three.pdf','application/pdf');el._stageFile(chosen);
  await el._upload(chosen);
  assert.equal(calls.fetch.length,0);assert.equal(el._stagedFile,chosen);
  assert.match(el._statusEl.textContent,/Selected settings are unavailable/);
  assert.equal(el._optionFields.copies.disabled,false);
  changeOption(win,el,'copies','1');await el._upload(chosen);
  assert.equal(calls.fetch.length,1);
});

// Exercise HA's public showDialog/closeDialog contract. Real browser history
// and native modal/top-layer behavior are checked on the live paired dashboard.
async function optionsHost(win, card) {
  let request;
  card.addEventListener('show-dialog', event => { request = event.detail; }, { once: true });
  card._toggleOptions(true);
  assert.ok(request);
  await request.dialogImport();
  const host = win.document.createElement(request.dialogTag);
  win.document.body.append(host);
  host.showDialog(request.dialogParams);
  return host;
}

test('HA Back closes Options once and preserves selections for the next opening', async () => {
  const win = boot(), card = mount(win);
  const host = await optionsHost(win, card);
  const settings = card._settings;
  let closed = 0;
  host.addEventListener('dialog-closed', event => {
    assert.equal(event.detail.dialog, host.localName);
    assert.equal(event.bubbles, true);
    assert.equal(event.composed, true);
    closed++;
  });
  assert.equal(card._optionsPanel.open, true);
  assert.equal(host.closeDialog(), true); // HA calls this on Back.
  host.closeDialog();
  assert.equal(closed, 1);
  assert.equal(card._optionsPanel.hidden, true);
  assert.equal(card._optionsPanel.open, false);
  assert.equal(card._optionsButton.getAttribute('aria-expanded'), 'false');
  assert.equal(card.shadowRoot.activeElement, card._optionsButton);
  card._toggleOptions(true);
  assert.equal(card._settings, settings);
  assert.equal(card._optionsPanel.open, true);
  let duplicates = 0;
  card.addEventListener('show-dialog', () => duplicates++);
  card._toggleOptions(true);
  assert.equal(duplicates, 0);
});

test('leaving and returning to a dashboard never leaves Options open inline', async () => {
  const win = boot(), card = mount(win);
  const host = await optionsHost(win, card);
  let closed = 0;
  host.addEventListener('dialog-closed', () => closed++);
  card.remove();
  win.document.body.append(card);
  assert.equal(closed, 1);
  assert.equal(card._optionsPanel.hidden, true);
  assert.equal(card._optionsPanel.open, false);
  assert.equal(card._optionsOpen, false);
  assert.equal(card._optionsButton.getAttribute('aria-expanded'), 'false');
  card._optionsButton.click();
  assert.equal(card._optionsPanel.open, true);
  assert.equal(card._optionsPanel.hidden, false);
});

test('native dismissals and Done close HA state without a delayed close dismissing a new dialog', async () => {
  const win = boot(), card = mount(win);
  const host = await optionsHost(win, card);
  let closed = 0;
  host.addEventListener('dialog-closed', () => closed++);
  card._optionsPanel.close();
  await new Promise(resolve => win.setTimeout(resolve, 5));
  assert.equal(card._optionsOpen, false);
  assert.equal(closed, 1);
  host.showDialog({ card }); // A delayed HA loader must not leave a stale dialog.
  assert.equal(host._card, null);
  await optionsHost(win, card);
  const done = [...card._optionsPanel.querySelectorAll('button')].find(b => b.textContent === 'Done');
  done.click();
  assert.equal(card._optionsPanel.hidden, true);
  card._optionsButton.click();
  await new Promise(resolve => win.setTimeout(resolve, 5));
  assert.equal(card._optionsPanel.open, true);
  assert.equal(card._optionsOpen, true);
});

test('a pending HA dialog registration cannot reopen Options after navigation', async () => {
  const win = boot(), card = mount(win);
  let request;
  card.addEventListener('show-dialog', event => { request = event.detail; });
  card._toggleOptions(true);
  card.remove();
  await request.dialogImport();
  const host = win.document.createElement(request.dialogTag);
  let closed = 0;
  host.addEventListener('dialog-closed', () => closed++);
  host.showDialog(request.dialogParams);
  assert.equal(closed, 1);
  assert.equal(host._card, null);
  win.document.body.append(card);
  assert.equal(card._optionsPanel.hidden, true);
  assert.equal(card._optionsPanel.open, false);
});

test('a restored HA history entry without live parameters closes safely', async () => {
  const win = boot(), card = mount(win);
  const host = await optionsHost(win, card);
  host.closeDialog();
  let closed = 0;
  host.addEventListener('dialog-closed', () => closed++);
  host.showDialog(null);
  assert.equal(closed, 1);
  assert.equal(host._card, null);
  assert.equal(card._optionsPanel.hidden, true);
});

// Test-only catalogs exercise localization without shipping unreviewed languages.
test('language resolution uses region, base, then English per key and plural rules', () => {
  const win = boot({
    fr: { 'card.title': 'BASE TITLE', 'status.complete': { one: 'ONE {count}', other: 'MANY {count}' } },
    'fr-ca': { 'dialog.title': 'REGIONAL OPTIONS' },
  });
  const localize = win.localize;
  const hass = { locale: { language: 'fr-CA' }, language: 'en' };
  assert.equal(localize('card.title', {}, hass), 'BASE TITLE');
  assert.equal(localize('dialog.title', {}, hass), 'REGIONAL OPTIONS');
  assert.equal(localize('action.done', {}, hass), 'Done');
  assert.equal(localize('status.complete', { count: 0 }, hass), 'ONE 0');
  assert.equal(localize('status.complete', { count: 2 }, hass), 'MANY 2');
  assert.equal(localize('card.title', {}, { language: 'fr_CA' }), 'BASE TITLE');
  assert.equal(localize('action.done', {}, { locale: { language: 'not a locale' } }), 'Done');
  assert.equal(localize('constructor', {}, hass), 'constructor');
  assert.equal(localize('missing.key', {}, hass), 'missing.key');
  const english = localize('status.complete', { count: 0 }, { language: 'xx' });
  assert.match(english, /0 pages/);
});

test('catalog references and plural placeholders are valid', () => {
  const win = boot();
  const catalogs = JSON.parse(CARD_SRC.match(/const CARD_TRANSLATIONS = (\{[\s\S]*?\});\n\/\/ END ENGLISH CATALOG/)[1]);
  assert.deepEqual(Object.keys(catalogs), ['en'], 'only reviewed English is shipped');
  for (const [key, message] of Object.entries(catalogs.en)) {
    assert.match(key, /^[a-z][a-z0-9_.]+$/);
    const forms = typeof message === 'string' ? [message] : Object.values(message);
    if (typeof message !== 'string') assert.equal(typeof message.other, 'string');
    const placeholders = forms.map(value => [...value.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort());
    for (const names of placeholders) assert.deepEqual(names, placeholders[0], key);
  }
  const refs = [...CARD_SRC.matchAll(/(?:_t|_msg|_setMessage|localize|translatedText)\('([^']+)'/g)].map(m => m[1]);
  for (const key of refs) assert.ok(Object.hasOwn(catalogs.en, key), key);
  assert.equal(win.localize('action.done'), 'Done');
});

test('Options is named, focuses its heading and describes fields without opening a keyboard', async () => {
  const win = boot(), card = mount(win);
  const host = await optionsHost(win, card);
  const heading = card._optionsPanel.querySelector('h2');
  assert.equal(card.shadowRoot.activeElement, heading);
  assert.equal(heading.autofocus, true);
  assert.equal(card._optionsButton.getAttribute('aria-label'), heading.textContent);
  for (const field of Object.values(card._optionFields)) {
    assert.equal(field.getAttribute('aria-describedby'), 'options-help');
    assert.ok(card.shadowRoot.getElementById('options-help'));
    assert.ok(field.closest('label').querySelector('[data-i18n]').textContent);
  }
  host.closeDialog();
  assert.equal(card.shadowRoot.activeElement, card._optionsButton);
});

test('translation text and placeholder data cannot create HTML', () => {
  const markup = '<img src=x onerror=alert(1)>';
  const win = boot({ fr: { 'dialog.title': markup, 'status.cancel_failed': 'ERROR {error}' } });
  const card = mount(win, { title: markup });
  card.hass = { states: {}, entities: {}, locale: { language: 'fr' } };
  card._setMessage('status.cancel_failed', { error: markup + ' $&' }, 'err');
  assert.equal(card._statusEl.textContent, 'ERROR ' + markup + ' $&');
  assert.equal(card.shadowRoot.querySelector('img'), null);
  assert.equal(card._titleEl.textContent, markup, 'custom title remains literal user data');
  assert.equal(card._optionsPanel.querySelector('h2').textContent, markup);
});

test('unchanged status and Options guidance do not repeat live-region mutations', async () => {
  const win = boot(), card = mount(win);
  card._setMessage('status.canceled', {}, 'err');
  let changed = 0;
  const observer = new win.MutationObserver(records => { changed += records.length; });
  observer.observe(card._statusEl, { childList: true, characterData: true, subtree: true });
  observer.observe(card._optionHelp, { childList: true, characterData: true, subtree: true });
  card._setMessage('status.canceled', {}, 'err');
  card._syncControls();
  card._syncControls();
  await new Promise(resolve => win.setTimeout(resolve, 0));
  observer.disconnect();
  assert.equal(changed, 0);
});

test('print editor labels preserve binding values and display the real default copy count', () => {
  const win = boot(), editor = win.customElements.get(TAG).getConfigElement();
  editor.hass = { locale: { language: 'en' } };
  let changes = 0, saved;
  editor.addEventListener('config-changed', event => { changes++; saved = event.detail.config; });
  editor.setConfig({ type: 'custom:' + TAG, custom_option: 'preserved' });
  const form = editor._form;
  assert.equal(changes, 0);
  assert.equal(form.data.copies, 1);
  assert.equal(form.data.duplex, false);
  assert.equal(form.data.binding, 'two-sided-long-edge');
  const bindings = form.schema.find(f => f.name === 'binding').selector.select.options;
  assert.equal(bindings.find(o => o.value === 'two-sided-short-edge').label, 'Short edge');
  assert.match(form.computeHelper({ name: 'binding' }), /notepad/);
  assert.match(form.computeHelper({ name: 'duplex_in_options' }), /compact/);
  form.dispatchEvent(new win.CustomEvent('value-changed', { detail: { value: { ...form.data, binding: 'two-sided-short-edge', copies: null } } }));
  assert.equal(changes, 1);
  assert.equal(saved.binding, 'two-sided-short-edge');
  assert.equal(saved.custom_option, 'preserved');
  assert.equal(Object.hasOwn(saved, 'copies'), false);
  const card = mount(win, saved);
  assert.equal(card._settings.copies, 1);
});

test('print language updates preserve the staged file, settings and focused copies input', async () => {
  const win = boot({ fr: { 'dialog.title': 'PRINT OPTIONS TEST', 'status.ready': 'READY TEST', 'status.choose': 'CHOOSE TEST', 'action.print': 'PRINT TEST' } });
  const card = mount(win);
  const { hass, calls } = makeHass(win, { capabilitiesImpl: async () => jsonResponse(optionCaps()) });
  card.hass = { ...hass, locale: { language: 'fr-CA' } };
  assert.equal(card._statusEl.textContent, 'CHOOSE TEST', 'idle text follows the selected language');
  card.hass = hass; const chosen = file(win, 'kept.pdf', 'application/pdf'); card._stageFile(chosen); await tick();
  card._toggleOptions(true);
  const field = changeOption(win, card, 'copies', '2'); field.focus();
  card.hass = { ...hass, locale: { language: 'fr-CA' } };
  assert.equal(card._optionFields.copies, field);
  assert.equal(card.shadowRoot.activeElement, field);
  assert.equal(card._settings.copies, 2);
  assert.equal(card._stagedFile, chosen);
  assert.equal(card._optionsPanel.querySelector('h2').textContent, 'PRINT OPTIONS TEST');
  assert.equal(card._primaryEl.textContent, 'PRINT TEST');
  assert.equal(card._statusEl.textContent, 'READY TEST');
  assert.equal(calls.fetch.length, 0);
});


test('checked connection is independent from idle and stale evidence becomes unknown', () => {
  const win = boot();
  const el = mount(win, { entity: SENSOR });
  const { hass, calls } = makeHass(win, { fetchImpl: async () => jsonResponse({}) });
  el.hass = hass;
  const snapshot = { state: 'unreachable', checked_at: new Date().toISOString(), next_check_at: new Date(Date.now()+60_000).toISOString() };
  push(el, hass, 'idle', { device_connection: snapshot });
  const warning = el.shadowRoot.querySelector('.connection');
  assert.equal(warning.hidden, false);
  assert.match(warning.textContent, /reach/i);
  assert.match(warning.title, /check/i);
  push(el, hass, 'idle', { device_connection: { ...snapshot, state: 'reachable' } });
  assert.equal(warning.hidden, true);
  push(el, hass, 'idle', { device_connection: { ...snapshot, state: 'reachable', next_check_at: '2000-01-01T00:00:00Z' } });
  assert.equal(warning.hidden, false);
  assert.match(warning.textContent, /not.*confirmed/i);
});

test('HA disconnect blocks actions and reconnect restores pushed state without submission', async () => {
  const win = boot();
  const el = mount(win, { entity: SENSOR });
  const { hass, calls } = makeHass(win, { fetchImpl: async () => jsonResponse({}) });
  el.hass = hass;
  push(el, hass, 'processing', { job_id: 7, submitted_at: '2026-10-09T01:00:00Z', pages_done: 0 });
  el.hass = { ...el._hass, connected: false };
  assert.equal(el.shadowRoot.querySelector('.primary').disabled, true);
  assert.equal(el.shadowRoot.querySelector('.cancel').disabled, true);
  assert.match(el.shadowRoot.querySelector('.connection').textContent, /Home Assistant/);
  el.shadowRoot.querySelector('.primary').click();
  el.shadowRoot.querySelector('.cancel').click();
  assert.equal(calls.fetch.length, 0);
  push(el, hass, 'canceled', { job_id: 7, submitted_at: '2026-10-09T01:00:00Z', pages_done: 0 });
  assert.equal(el.shadowRoot.querySelector('.primary').disabled, false);
  assert.match(el.shadowRoot.querySelector('.status').textContent, /canceled/i);
  assert.equal(calls.fetch.length, 0);
});

test('shared long errors keep device text literal and expand recovery guidance', () => {
  const win = boot();
  const el = mount(win);
  const message = 'Device could not confirm the outcome. Check the device before trying again; <img src=x onerror=alert(1)> is text, never markup.';
  el._setStatus(message, 'err');
  const node = el.shadowRoot.querySelector('.status');
  assert.equal(node.textContent, message);
  assert.equal(node.querySelector('img'), null);
  assert.ok(node.querySelector('details'));
});

test('two cards and a reloaded card recover one pushed job without subscriptions', () => {
  const win = boot();
  const { hass, calls } = makeHass(win);
  const a = mount(win, { entity: SENSOR }), b = mount(win, { entity: SENSOR });
  a.hass = b.hass = hass;
  b._stageFile(file(win, 'next.pdf', 'application/pdf'));
  push(a, hass, 'processing', { job_id: 9, submitted_at: '2026-10-09T03:00:00Z', filename: 'external.pdf', pages_done: 0, pages_total: 4 });
  b.hass = { ...hass };
  a.remove();
  const reload = mount(win, { entity: SENSOR }); reload.hass = { ...hass };
  assert.equal(b._activeJobId, 9);
  assert.equal(reload._activeJobId, 9);
  assert.equal(b._stagedFile.name, 'next.pdf');
  assert.equal(b._fileNameEl.textContent, 'external.pdf');
  push(b, hass, 'completed', { job_id: 9, submitted_at: '2026-10-09T03:00:00Z', pages_done: 4 });
  reload.hass = { ...hass };
  assert.equal(reload._activeJobId, null);
  assert.equal(reload._fileNameEl.textContent, 'PDF or image');
  assert.equal(b._stagedFile.name, 'next.pdf');
  assert.equal(calls.subscribe.length, 0);
  assert.equal(calls.fetch.length, 0);
});

test('reused queue IDs and delayed older snapshots cannot replace the submitted job', async () => {
  const win = boot();
  const el = mount(win, { entity: SENSOR });
  const oldTime = '2026-10-09T01:00:00Z', newTime = '2026-10-09T02:00:00Z';
  const { hass } = makeHass(win, { fetchImpl: async () => jsonResponse({ job_id: 7, submitted_at: newTime }) });
  el.hass = hass;
  push(el, hass, 'completed', { job_id: 7, submitted_at: oldTime });
  await el._upload(file(win, 'new.pdf', 'application/pdf'));
  assert.equal(el._activeJobId, 7);
  assert.equal(el._activeSubmittedAt, newTime);
  push(el, hass, 'processing', { job_id: 7, submitted_at: newTime, pages_done: 1 });
  push(el, hass, 'completed', { job_id: 7, submitted_at: oldTime });
  assert.equal(el._activeJobId, 7);
  assert.match(el._statusEl.textContent, /1/);
});

test('progress updates do not allow a second cancel while the first is pending', async () => {
  const win = boot();
  const el = mount(win, { entity: SENSOR });
  let finish;
  const { hass, calls } = makeHass(win, { fetchImpl: () => new Promise(resolve => { finish = resolve; }) });
  el.hass = hass;
  const attrs = { job_id: 7, submitted_at: '2026-10-09T01:00:00Z' };
  push(el, hass, 'processing', { ...attrs, pages_done: 0 });
  const cancel = el._cancelJob();
  push(el, hass, 'processing', { ...attrs, pages_done: 1 });
  await el._cancelJob();
  assert.equal(calls.fetch.length, 1);
  finish(jsonResponse({ ok: true }));
  await cancel;
  assert.match(el._statusEl.textContent, /Cancelling/);
});


test('growing HP totals never make active progress look complete', () => {
  const win = boot();
  const el = mount(win, { entity: SENSOR });
  const { hass } = makeHass(win); el.hass = hass;
  const attrs = { job_id: 371, submitted_at: '2026-10-09T12:59:30Z', progress_unit: 'impressions' };
  push(el, hass, 'processing', { ...attrs, pages_done: 0, pages_total: 0 });
  assert.equal(el._statusEl.textContent, 'Printing… 0 pages printed');
  push(el, hass, 'processing', { ...attrs, pages_done: 2, pages_total: 2 });
  assert.equal(el._statusEl.textContent, 'Printing… 2 pages printed');
  assert.equal(el._activeJobId, 371);
  push(el, hass, 'completed', { ...attrs, pages_done: 4, pages_total: 4 });
  assert.equal(el._statusEl.textContent, 'Print complete ✓ (4 pages)');
  push(el, hass, 'processing', { ...attrs, job_id: 372, progress_unit: 'sheets', pages_done: 1, pages_total: 8 });
  assert.equal(el._statusEl.textContent, 'Printing… 1 sheet printed');
});


// Native host adapter: these exercise routing/lifetime, not CSS implementation.
const FEATURE = 'ipp-print-feature';
function featureFixture(win, options = {}) {
  const other = 'sensor.another_device';
  const ids = [SENSOR, other];
  const calls = [];
  const hass = {
    connected: true,
    entities: Object.fromEntries(ids.map(id => [id, { entity_id: id, platform: 'ipp_print' }])),
    states: Object.fromEntries(ids.map(id => [id, { entity_id: id, state: 'idle', attributes: {} }])),
    fetchWithAuth: async (url, init) => {
      if (url.includes('/capabilities?')) return jsonResponse(optionCaps(new URL(url, 'http://fixture').searchParams.get('entity_id')));
      calls.push({ url, init });
      return options.fetchImpl ? options.fetchImpl(url, init) : jsonResponse({ scan_id: 'native-scan', job_id: 401 });
    },
  };
  const feature = win.document.createElement(FEATURE);
  feature.setConfig({ type: 'custom:' + FEATURE });
  win.document.body.append(feature);
  feature.hass = hass;
  feature.context = { entity_id: SENSOR };
  return { feature, hass, calls, other };
}

test('native feature registers independently and edits defaults without host identity', () => {
  const win = boot();
  const F = win.customElements.get(FEATURE);
  assert.equal(F.getStubConfig().type, 'custom:' + FEATURE);
  assert.equal(F.getStubConfig().duplex, false);
  const entry = win.customCardFeatures.find(item => item.type === FEATURE);
  assert.equal(entry.configurable, true);
  const { feature, hass } = featureFixture(win);
  assert.equal(entry.isSupported(hass, { entity_id: SENSOR }), true);
  assert.equal(entry.isSupported(hass, { area_id: 'office' }), false);
  assert.equal(entry.isSupported(hass, { entity_id: 'light.lamp' }), false);
  assert.equal(entry.isSupported({ ...hass, entities: { [SENSOR]: { platform: 'unrelated' } } }, { entity_id: SENSOR }), false);
  assert.throws(() => feature.setConfig({ entity: SENSOR }), /parent card/);
  assert.throws(() => feature.setConfig({ duplex: 'yes' }));
  const editor = F.getConfigElement();
  editor.setConfig(F.getStubConfig()); editor.hass = hass;
  const form = editor.querySelector('ha-form');
  assert.ok(form.schema.some(field => field.name === 'duplex'));
  assert.ok(form.schema.every(field => !['entity', 'title'].includes(field.name)));
  let changed;
  editor.addEventListener('config-changed', event => { changed = event.detail.config; });
  form.dispatchEvent(new win.CustomEvent('value-changed', { detail: { value: { duplex: true } } }));
  assert.equal(changed.type, 'custom:' + FEATURE);
  assert.equal(changed.duplex, true);
  assert.equal(feature._workflow.shadowRoot.querySelector('ha-card'), null);
});

test('native feature supports legacy entity delivery but empty modern context stays authoritative', () => {
  const win = boot();
  const { feature, hass } = featureFixture(win);
  const legacy = win.document.createElement(FEATURE);
  legacy.setConfig({}); legacy.stateObj = hass.states[SENSOR]; legacy.hass = hass;
  win.document.body.append(legacy);
  assert.equal(legacy._workflow._config.entity, SENSOR);
  legacy.context = {};
  legacy.stateObj = hass.states[SENSOR];
  assert.equal(legacy._workflow, null);
  assert.match(legacy.shadowRoot.textContent, /Select an/);
  feature.position = 'inline';
  assert.equal(feature._workflow, null);
  assert.match(feature.shadowRoot.textContent, /Bottom/);
  feature.position = 'bottom';
  assert.equal(feature._workflow._config.entity, SENSOR);
});

test('native feature preserves local intent across state pushes and remount without starting work', async () => {
  const win = boot();
  const { feature, hass, calls } = featureFixture(win);
  const workflow = feature._workflow;
  await workflow._refreshOptions();
  workflow._twoSidedEl.click();
  feature.hass = { ...hass };
  feature.context = { entity_id: SENSOR };
  feature.stateObj = hass.states[SENSOR];
  feature.remove(); win.document.body.append(feature);
  assert.equal(feature._workflow, workflow);
  assert.equal(workflow._twoSidedEl.checked, true);
  assert.equal(calls.length, 0);
  let bubbled = 0;
  feature.addEventListener('click', () => { bubbled++; });
  workflow._twoSidedEl.click();
  assert.equal(bubbled, 0);
});

test('native target change during submission detaches old replies and never carries intent to new device', async () => {
  const win = boot();
  let finish;
  const { feature, hass, calls, other } = featureFixture(win, {
    fetchImpl: () => new Promise(resolve => { finish = resolve; }),
  });
  const workflow = feature._workflow;
  workflow._stageFile(new win.File(['PDF'], 'test.pdf', { type: 'application/pdf' }));
  workflow._primaryEl.click(); workflow._primaryEl.click();
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.body.get('entity_id'), SENSOR);
  feature.context = { entity_id: other };
  const next = feature._workflow;
  assert.notEqual(next, workflow);
  assert.equal(next._config.entity, other);
  assert.ok(!next._stagedFile);
  finish(jsonResponse({ scan_id: 'old-reply', job_id: 402 }));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(!next._activeScanId && next._activeJobId == null);
  assert.equal(calls.length, 1);
  feature.hass = { ...hass, connected: false };
  assert.equal(next._primaryEl.disabled, true);
  feature.hass = { ...hass, connected: true };
  assert.equal(next._primaryEl.disabled, false);
});

test('native print locks its parent device and retains staged file only for that host', async () => {
  const win = boot();
  const { feature, hass, other, calls } = featureFixture(win);
  const workflow = feature._workflow;
  await workflow._refreshOptions();
  assert.equal(workflow._optionFields.entity_id.disabled, true);
  assert.equal(workflow._optionFields.entity_id.closest('label').hidden, true);
  workflow._stageFile(file(win, 'local.pdf', 'application/pdf'));
  await tick();
  feature.hass = { ...hass }; feature.context = { entity_id: SENSOR };
  assert.equal(feature._workflow._stagedFile.name, 'local.pdf');
  assert.equal(calls.length, 0);
  feature.context = { entity_id: other };
  assert.ok(!feature._workflow._stagedFile);
  assert.equal(calls.length, 0);
});


test('native editor excludes host identity even when an older standalone editor loaded first', () => {
  const win = boot({}, window => {
    window.customElements.define(TAG + '-editor', class extends window.HTMLElement {
      setConfig(config) { this._config = config; this._render(); }
      set hass(hass) { this._hass = hass; this._render(); }
      _render() {
        if (!this._form) { this._form = window.document.createElement('ha-form'); this.append(this._form); }
        this._form.schema = ['title','entity','duplex'].map(name => ({ name }));
      }
    });
  });
  const F = win.customElements.get(FEATURE), editor = F.getConfigElement();
  editor.setConfig(F.getStubConfig()); editor.hass = { states: {} };
  assert.equal(editor.localName, FEATURE + '-editor');
  assert.deepEqual(Array.from(editor.querySelector('ha-form').schema, field => field.name), ['duplex']);
});
