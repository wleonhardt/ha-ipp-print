// Lovelace card that picks a PDF and POSTs it to /api/ipp_print/print
// with the user's HA bearer token. No iframe, no Media Browser, no ingress.
//
// Type:  custom:ipp-print-upload-card
// Options:
//   title:   string, default "Print PDF"
//   entity:  job sensor to follow, default "sensor.printer_current_job"
//
// IMPORTANT: customElements.define() is at line ~10 — register the tag as
// early as possible so HA's lovelace card factory can resolve `custom:` cards
// without timing out on slow connections (Firefox / mobile). The method bodies
// are attached to the prototype below, after the registration call. Lovelace
// only needs the tag to exist; once it does, `setConfig`/`hass`/`connectedCallback`
// will resolve via prototype lookup even if they're patched onto the prototype
// "later" in the same script.

const TAG = 'ipp-print-upload-card';
const DEFAULT_JOB_SENSOR = 'sensor.printer_current_job';

if (!customElements.get(TAG)) {
  customElements.define(TAG, class extends HTMLElement {});
}

const C = customElements.get(TAG);

C.getStubConfig = function () { return { title: 'Print PDF' }; };

C.prototype.setConfig = function (config) {
  this._config = Object.assign(
    { title: 'Print PDF', entity: DEFAULT_JOB_SENSOR }, config || {},
  );
  this._render();
  // _render is one-shot; apply config changes (card editor) directly.
  if (this._titleEl) this._titleEl.textContent = this._config.title;
};

// hass is set every state update; keep the latest reference for the token.
Object.defineProperty(C.prototype, 'hass', {
  set(hass) { this._hass = hass; },
  configurable: true,
});

C.prototype.getCardSize = function () { return 2; };

C.prototype._render = function () {
  if (this._rendered) return;
  const root = this.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      :host {
        display: block;
        /* Set up a size-based container so children can adapt to the
           card's own width — covers the case where a horizontal-stack
           shrinks each card narrow even on a wide viewport. */
        container-type: inline-size;
      }
      /* Theme-driven: accent from --primary-color, surfaces/text from the
         active HA theme, so the card reads correctly on light and dark. */
      ha-card {
        padding: 18px 14px;
        min-height: 130px;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        gap: 6px;
        cursor: pointer;
        transition: transform .08s ease, box-shadow .15s ease;
        box-sizing: border-box;
      }
      ha-card:hover { box-shadow: 0 0 0 2px var(--primary-color); }
      ha-card:active { transform: scale(.99); }
      ha-card.busy { cursor: progress; opacity: .85; }
      .icon { width: 36px; height: 36px; color: var(--primary-color); flex-shrink: 0; }
      .title { font-weight: 700; font-size: 20px; color: var(--primary-text-color); line-height: 1.1; text-align: center; }
      .status {
        font-size: 13px;
        min-height: 16px;
        color: var(--secondary-text-color);
        text-align: center;
        padding: 0 4px;
        line-height: 1.3;
        word-break: break-word;
      }
      /* When the card itself is narrow (typically a phone, or a two-card
         horizontal-stack on a sidebar-split desktop), shrink the title
         and icon so multi-line status messages like "Printing page 3/7…"
         don't push the cancel link off the card or collide with the
         title. Container query fires on the card's own width, not the
         viewport. */
      @container (max-width: 260px) {
        ha-card { padding: 14px 10px; gap: 4px; }
        .icon { width: 30px; height: 30px; }
        .title { font-size: 17px; }
        .status { font-size: 12px; }
      }
      @container (max-width: 200px) {
        .title { font-size: 15px; }
        .status { font-size: 11px; }
        .icon { width: 26px; height: 26px; }
      }
      .status.err { color: var(--error-color); }
      .status.ok  { color: var(--success-color, var(--primary-color)); }
      .cancel {
        font-size: 11px;
        color: var(--error-color);
        cursor: pointer;
        text-decoration: underline;
        text-underline-offset: 2px;
        margin-top: -4px;
        display: none;
      }
      .cancel.show { display: inline; }
      .cancel:hover { opacity: .8; }
    </style>
    <ha-card role="button" tabindex="0">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/>
        <line x1="12" y1="3" x2="12" y2="15"/>
      </svg>
      <div class="title"></div>
      <div class="status" aria-live="polite"></div>
      <div class="cancel" role="button" tabindex="0">Cancel</div>
    </ha-card>
  `;
  this._card = root.querySelector('ha-card');
  this._titleEl = root.querySelector('.title');
  this._statusEl = root.querySelector('.status');
  this._cancelEl = root.querySelector('.cancel');
  this._titleEl.textContent = this._config.title;

  // Card click → file picker; but cancel button intercepts its own clicks.
  this._card.addEventListener('click', (ev) => {
    if (ev.target === this._cancelEl) return;
    this._pick();
  });
  this._card.addEventListener('keydown', (ev) => {
    if (ev.target === this._cancelEl) return;
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      this._pick();
    }
  });
  this._cancelEl.addEventListener('click', (ev) => {
    ev.stopPropagation();
    this._cancelJob();
  });
  this._cancelEl.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      ev.stopPropagation();
      this._cancelJob();
    }
  });
  this._rendered = true;
};

// Self-healed instances may never receive `hass` from lovelace (the parent
// hui-card can keep pointing at the replaced error card), so every consumer
// falls back to the app root's live hass object.
C.prototype._getHass = function () {
  return this._hass || document.querySelector('home-assistant')?.hass || null;
};

// hass.fetchWithAuth refreshes an expired token automatically; a raw fetch
// with a copied bearer token is the fallback for exotic auth setups.
C.prototype._authedFetch = function (path, init) {
  const hass = this._getHass();
  if (hass?.fetchWithAuth) return hass.fetchWithAuth(path, init);
  const token =
    hass?.auth?.data?.access_token ||
    hass?.connection?.auth?.data?.access_token ||
    hass?.auth?.accessToken ||
    null;
  const headers = Object.assign({}, init?.headers || {});
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(path, Object.assign({}, init, {
    headers,
    credentials: 'same-origin',
  }));
};

C.prototype._cancelJob = async function () {
  if (this._activeJobId == null) return;
  try {
    const r = await this._authedFetch('/api/ipp_print/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: this._activeJobId }),
    });
    if (!r.ok) {
      const body = await r.text();
      this._setStatus('Cancel failed: ' + body.slice(0, 80), 'err');
      return;
    }
    this._setStatus('Cancelling…');
    // The coordinator's next poll will observe IPP terminal state and the
    // sensor subscription will overwrite this with "Print canceled".
  } catch (err) {
    this._setStatus('Cancel failed: ' + (err?.message || err), 'err');
  }
};

C.prototype._setCancelVisible = function (visible) {
  if (!this._cancelEl) return;
  this._cancelEl.classList.toggle('show', !!visible);
};

C.prototype._setStatus = function (text, cls = '') {
  this._statusEl.textContent = text || '';
  this._statusEl.className = 'status' + (cls ? ' ' + cls : '');
};

C.prototype._pick = function () {
  if (this._busy) return;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'application/pdf,.pdf';
  // CRITICAL: the input must be attached to the document for the `change`
  // event to fire reliably across modern browsers. A detached `<input>`
  // silently swallows the event in current Chrome / Safari builds — the
  // user sees the file picker, selects a file, the picker closes, and
  // nothing happens. Insert it hidden, then clean up after pick/cancel.
  input.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0;pointer-events:none;width:0;height:0;';
  document.body.appendChild(input);
  const cleanup = () => {
    try { input.remove(); } catch {}
  };
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    cleanup();
    if (!file) {
      this._setStatus('Choose a PDF first.', 'err');
      return;
    }
    this._upload(file);
  }, { once: true });
  // Safety net: if the user cancels the picker, modern browsers fire
  // `cancel` (and no `change`). Clean up so we don't leak inputs.
  input.addEventListener('cancel', cleanup, { once: true });
  // Last-resort GC: if neither event fires within 5 minutes, drop the input.
  setTimeout(cleanup, 5 * 60 * 1000);
  input.click();
};

C.prototype._upload = async function (file) {
  if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
    this._setStatus('Pick a .pdf file.', 'err');
    return;
  }
  this._busy = true;
  this._card.classList.add('busy');
  this._setStatus('Uploading…');

  const form = new FormData();
  form.append('file', file, file.name);

  try {
    // Returns the printer-assigned job-id we then track via the job sensor.
    const resp = await this._authedFetch('/api/ipp_print/print', {
      method: 'POST',
      body: form,
    });
    let body = null;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      try { body = await resp.json(); } catch { /* keep null */ }
    }
    if (!resp.ok) {
      const msg = (body && (body.message || body.error)) || `HTTP ${resp.status}`;
      throw new Error(msg);
    }
    const name = (body && body.filename) || file.name;
    this._activeJobId = body?.job_id ?? null;
    this._setStatus(`Submitted ✓ ${name}`, 'ok');
    // Subscribe to printer_current_job updates for this job-id.
    this._trackPrintProgress().catch((e) => {
      console.warn('[ipp-print] progress tracking error', e);
    });
  } catch (err) {
    this._setStatus('Submit failed: ' + (err && err.message ? err.message : err), 'err');
  } finally {
    this._busy = false;
    this._card.classList.remove('busy');
  }
};

// The integration's coordinator polls IPP every 1.5s and pushes per-job
// state through the job sensor's state + attributes; the card follows it.
const TERMINAL_STATES = new Set([
  'canceled', 'aborted', 'completed',
]);
const ACTIVE_STATES = new Set([
  'pending', 'pending-held', 'processing', 'processing-stopped',
]);

C.prototype._trackPrintProgress = async function () {
  const hass = this._getHass();
  if (!hass || !hass.connection) return;

  // Cancel any previous subscription so successive uploads don't overlap.
  if (this._unsubProgress) {
    try { this._unsubProgress(); } catch {}
    this._unsubProgress = null;
  }
  clearTimeout(this._progressSafety);

  const ourJobId = this._activeJobId;
  let sawState = null;

  const render = (state, attrs) => {
    const pagesDone = attrs?.pages_done;
    const pagesTotal = attrs?.pages_total;
    let msg;
    if (state === 'processing') {
      if (pagesTotal && pagesDone != null) {
        msg = `Printing page ${pagesDone}/${pagesTotal}…`;
      } else if (pagesDone) {
        msg = `Printing page ${pagesDone}…`;
      } else {
        msg = 'Printing…';
      }
      this._setStatus(msg);
      this._setCancelVisible(true);
    } else if (state === 'pending' || state === 'pending-held') {
      this._setStatus('Queued for printer…');
      this._setCancelVisible(true);
    } else if (state === 'completed') {
      const pages = pagesDone || pagesTotal;
      const pagesMsg = pages ? ` (${pages} page${pages > 1 ? 's' : ''})` : '';
      this._setStatus(`Print complete ✓${pagesMsg}`, 'ok');
      this._setCancelVisible(false);
    } else if (state === 'canceled') {
      this._setStatus('Print canceled', 'err');
      this._setCancelVisible(false);
    } else if (state === 'aborted') {
      const reason = attrs?.state_reasons;
      this._setStatus(
        'Print failed' + (reason ? `: ${reason}` : ''),
        'err',
      );
      this._setCancelVisible(false);
    } else {
      this._setCancelVisible(false);
    }
  };

  // Push the initial render from the current sensor snapshot — the
  // coordinator may have already moved the job into pending before we
  // subscribed.
  const sensorId = this._config?.entity || DEFAULT_JOB_SENSOR;
  const initial = hass.states[sensorId];
  // Local mirror of the sensor; subscribe_entities sends diffs.
  const cur = {
    state: initial?.state ?? null,
    attributes: Object.assign({}, initial?.attributes || {}),
  };
  if (initial && initial.attributes?.job_id === ourJobId) {
    sawState = initial.state;
    render(initial.state, initial.attributes);
  }

  const onUpdate = () => {
    // Only act on changes that belong to our job, or to idle (which means
    // the coordinator cleared after the terminal hold window).
    const sensorJobId = cur.attributes.job_id;
    if (sensorJobId != null && sensorJobId !== ourJobId) return;
    sawState = cur.state;
    render(cur.state, cur.attributes);
    if (TERMINAL_STATES.has(cur.state)) {
      // Leave the message up for a bit, then unsubscribe.
      clearTimeout(this._progressSafety);
      this._progressSafety = setTimeout(() => {
        if (this._statusEl?.textContent &&
            !ACTIVE_STATES.has(sawState)) {
          this._setStatus('');
        }
      }, 10_000);
      try { this._unsubProgress(); } catch {}
      this._unsubProgress = null;
    }
  };

  // `subscribe_entities` is server-filtered to this one entity and, unlike
  // `subscribe_trigger`, is not admin-only — so non-admin dashboard users
  // get progress too. Messages carry compressed diffs:
  //   a: full add   {id: {s, a}}
  //   c: change     {id: {'+': {s?, a?(partial)}, '-': {a?: [keys]}}}
  //   r: removed    [ids]
  this._unsubProgress = await hass.connection.subscribeMessage((msg) => {
    const add = msg?.a?.[sensorId];
    if (add) {
      cur.state = add.s;
      cur.attributes = Object.assign({}, add.a || {});
      onUpdate();
      return;
    }
    const chg = msg?.c?.[sensorId];
    if (!chg) return;
    const plus = chg['+'] || {};
    const minus = chg['-'] || {};
    if (plus.s !== undefined) cur.state = plus.s;
    if (plus.a) Object.assign(cur.attributes, plus.a);
    for (const k of (minus.a || [])) delete cur.attributes[k];
    onUpdate();
  }, { type: 'subscribe_entities', entity_ids: [sensorId] });

  // Safety net: if no events arrive for 90 seconds, clean up.
  this._progressSafety = setTimeout(() => {
    if (this._unsubProgress) {
      try { this._unsubProgress(); } catch {}
      this._unsubProgress = null;
    }
    if (!sawState) {
      this._setStatus('Job submitted (no further updates)', 'ok');
      setTimeout(() => {
        if (this._statusEl?.textContent?.startsWith('Job submitted')) {
          this._setStatus('');
        }
      }, 6000);
    }
  }, 90_000);
};

window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: 'IPP Print Upload',
    description: 'Upload a PDF straight to an IPP printer with live job progress.',
    preview: true,
  });
}

// Self-healing for HA's whenDefined() race. On slow loads (Firefox / mobile /
// slow networks), lovelace can render `hui-error-card` "Configuration error"
// placeholders for our card before this script finishes loading. Once we're
// running, walk the DOM, find any error cards whose config points at our
// tag, and swap in a real instance.
//
// Recent HA changed the hui-error-card config shape: the err's own _config
// is now {type: 'error', message: 'Custom element doesn\'t exist...'} rather
// than the user-provided config. The original lives on the parent <hui-card>
// under _elementConfig. We source from there first and fall back gracefully.
const _LJP_HEALED = new WeakSet();

function _ljpHealOne(err) {
  if (_LJP_HEALED.has(err)) return;
  const parent = err.parentElement;
  let cfg = parent && parent._elementConfig;
  if (!cfg) cfg = err._config || err.config;
  if (!cfg || cfg.type !== 'custom:' + TAG) {
    // Last resort: parse the missing tag from the error message and build
    // a default config so the dashboard isn't stuck on "Configuration error".
    const msg = err._config && err._config.message;
    if (typeof msg === 'string' && msg.indexOf(TAG) !== -1) {
      cfg = {type: 'custom:' + TAG};
    } else {
      return;
    }
  }
  _LJP_HEALED.add(err);
  // If the parent hui-card already has a real instance of our element
  // (Lovelace's own whenDefined() callback may have inserted one alongside
  // the error card), just remove the error card sibling. Otherwise replace
  // the error card in place with a fresh instance.
  const existing = parent && parent.querySelector
    ? parent.querySelector(TAG)
    : null;
  if (existing) {
    err.remove();
    return;
  }
  const fresh = document.createElement(TAG);
  try {
    fresh.setConfig(cfg);
  } catch (e) {
    return;
  }
  // Lovelace won't push `hass` to a node it didn't create — seed it once
  // here; runtime consumers use _getHass() for a live fallback after this.
  const ha = document.querySelector('home-assistant');
  if (ha && ha.hass) fresh.hass = ha.hass;
  err.replaceWith(fresh);
}

function _ljpHeal() {
  const root = document.querySelector('home-assistant');
  if (!root) return;
  const stack = [root];
  while (stack.length) {
    const el = stack.pop();
    if (!el) continue;
    if (el.tagName === 'HUI-ERROR-CARD') _ljpHealOne(el);
    if (el.shadowRoot) stack.push(el.shadowRoot);
    for (const c of (el.children || [])) stack.push(c);
  }
}
// Staggered retries across the typical timing window.
[40, 120, 300, 700, 1500, 3000, 6000, 10_000].forEach(
  (ms) => setTimeout(_ljpHeal, ms),
);

// Watch for error cards that appear after the initial retry window —
// dashboard navigation, lazy view mounts, etc. Once this script has run,
// customElements.define has succeeded, so "custom element doesn't exist"
// error cards can only come from renders already in flight — disconnect
// after 30s instead of paying the observer cost for the whole session.
try {
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const n of m.addedNodes) {
        if (!n || n.nodeType !== 1) continue;
        if (n.tagName === 'HUI-ERROR-CARD') {
          _ljpHealOne(n);
        } else if (n.querySelectorAll) {
          n.querySelectorAll('hui-error-card').forEach(_ljpHealOne);
        }
      }
    }
  });
  observer.observe(document.body, {childList: true, subtree: true});
  setTimeout(() => { try { observer.disconnect(); } catch {} }, 30_000);
} catch {}
