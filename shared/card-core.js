// BEGIN DOCUMENT CARD CORE v4
// Canonical source: ha-escl-scan/shared/card-core.js; synchronize with tools/sync-card-core.mjs.
// Shared localization contract v1. Keep this helper identical in both cards.
// Catalogs are bundled here: no build step, translation fetch or registration wait.
class LocalizedMessage {
  constructor(key, values) { this.key = key; this.values = values; }
}
function setText(element, value) {
  if (element.textContent !== value) element.textContent = value;
}
function hasOwn(object, key) { return Object.prototype.hasOwnProperty.call(object, key); }
let lastLanguageValue, lastLanguage = 'en';
function cardLanguage(hass) {
  const value = hass?.locale?.language || hass?.language || 'en';
  if (value === lastLanguageValue) return lastLanguage;
  lastLanguageValue = value;
  try { lastLanguage = Intl.getCanonicalLocales(String(value).replace(/_/g, '-'))[0].toLowerCase(); }
  catch { lastLanguage = 'en'; }
  return lastLanguage;
}
function localize(key, values = {}, hass = document.querySelector('home-assistant')?.hass) {
  const language = cardLanguage(hass);
  for (const locale of new Set([language, language.split('-')[0], 'en'])) {
    const catalog = hasOwn(CARD_TRANSLATIONS, locale) ? CARD_TRANSLATIONS[locale] : null;
    if (!catalog || !hasOwn(catalog, key)) continue;
    let message = catalog[key];
    if (message && typeof message === 'object') {
      const category = new Intl.PluralRules(locale).select(Number(values.count));
      message = hasOwn(message, category) ? message[category] : message.other;
    }
    if (typeof message !== 'string') continue;
    return message.replace(/\{(\w+)\}/g, (token, name) => {
      if (!hasOwn(values, name)) return token;
      const value = values[name];
      return value instanceof LocalizedMessage ? localize(value.key, value.values, hass) : String(value);
    });
  }
  return key;
}
function localizeElements(root, hass) {
  for (const el of root.querySelectorAll('[data-i18n]')) {
    el.textContent = localize(el.dataset.i18n, el._i18nValues || {}, hass);
  }
  for (const el of root.querySelectorAll('[data-i18n-label]')) {
    const label = localize(el.dataset.i18nLabel, {}, hass);
    el.setAttribute('aria-label', label);
    if (el.hasAttribute('title')) el.title = label;
  }
}
function translatedText(key, values = {}, hass) {
  const span = document.createElement('span');
  span.dataset.i18n = key; span._i18nValues = values;
  span.textContent = localize(key, values, hass);
  return span;
}
C.prototype._msg = function (key, values = {}) { return new LocalizedMessage(key, values); };
C.prototype._t = function (key, values) { return localize(key, values, this._hass); };
C.prototype._setMessage = function (key, values = {}, cls = '') {
  this._setStatus(this._t(key, values), cls);
  this._statusMessage = { key, values, cls };
};
C.prototype._applyLanguage = function () {
  if (!this.shadowRoot) return false;
  const language = cardLanguage(this._hass);
  if (language === this._language) return false;
  this._language = language;
  localizeElements(this.shadowRoot, this._hass);
  if (!this._config.title) this._titleEl.textContent = this._t('card.title');
  if (this._statusMessage) {
    const { key, values, cls } = this._statusMessage;
    this._setMessage(key, values, cls);
  }
  return true;
};
// Checked connection is independent of a job's idle/running state.
C.prototype._syncConnection = function () {
  if (!this._connectionEl) return;
  const offline = this._hass?.connected === false;
  const snapshot = this._connectionSnapshot();
  const checked = Date.parse(snapshot?.checked_at);
  const next = Date.parse(snapshot?.next_check_at);
  const fresh = Number.isFinite(checked) && Number.isFinite(next) && next + 30_000 > Date.now();
  const state = fresh && ['reachable','unreachable'].includes(snapshot?.state) ? snapshot.state : 'unknown';
  this._connectionEl.hidden = !offline && (!snapshot || state === 'reachable');
  setText(this._connectionEl, this._t(offline ? 'connection.ha_lost' : 'connection.' + state));
  let time = '';
  if (Number.isFinite(checked)) {
    try { time = new Date(checked).toLocaleString(cardLanguage(this._hass)); }
    catch { time = new Date(checked).toISOString(); }
  }
  this._connectionEl.title = time ? this._t('connection.checked', { time }) : '';
};
// End shared localization helper.

// Text stays text, including device-supplied errors. Long recovery guidance expands.
function renderStatus(element, message, cls) {
  const className = 'status' + (cls ? ' ' + cls : '');
  if (typeof message === 'string' && element.textContent === message && element.className === className) return;
  element.replaceChildren();
  if (message instanceof Node) element.appendChild(message);
  else {
    const split = cls === 'err' && message.length > 100 ? message.indexOf('. ') : -1;
    if (split > 0) {
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = message.slice(0, split + 2);
      const recovery = document.createElement('div');
      recovery.textContent = message.slice(split + 2);
      details.append(summary, recovery);
      element.appendChild(details);
    } else element.textContent = message;
  }
  element.className = className;
}

const DOCUMENT_CARD_STYLES = `/* Shared document-card contract v1. Keep this base identical in both cards. */
      :host { display: block; height: 100%; }
      [hidden] { display: none !important; }
      ha-card {
        box-sizing: border-box; height: 100%; min-height: 200px; padding: 12px;
        display: flex; flex-direction: column; gap: 8px;
        color: var(--primary-text-color);
      }
      .header { display: flex; align-items: center; gap: 8px; min-width: 0; }
      .icon { --mdc-icon-size: 24px; width: 24px; height: 24px; color: var(--primary-color); flex: none; }
      .title { font-size: 16px; font-weight: 500; line-height: 24px; overflow-wrap: anywhere; }
      .status { color: var(--secondary-text-color); font-size: 14px; line-height: 20px; min-height: 40px; overflow-wrap: anywhere; }
      .status.err { color: var(--error-color); }
      .status.ok { color: var(--success-color, var(--primary-color)); }
      .status a { color: inherit; text-underline-offset: 2px; display: inline-flex; align-items: center; min-height: 44px; }
      .status summary { cursor: pointer; min-height: 44px; }
      .status details > div { padding-top: 8px; }
      .controls { min-height: 44px; }
      .actions { margin-top: auto; }
      button, select { font: inherit; font-size: 14px; }
      button {
        min-height: 44px; padding: 8px 12px; border: 0;
        border-radius: var(--ha-card-border-radius, 12px);
        background: var(--secondary-background-color); color: var(--primary-text-color);
        cursor: pointer; line-height: 20px; box-sizing: border-box;
      }
      button:disabled { opacity: .5; cursor: default; }
      button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, a:focus-visible {
        outline: 2px solid var(--primary-color); outline-offset: 2px;
      }
      .primary, .cancel { width: 100%; font-weight: 500; }
      .cancel { display: none; color: var(--error-color); }
      .cancel.show { display: block; }
      @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
      .options-button { margin-inline-start: auto; flex: none; width: 44px; padding: 8px; }
      .options { box-sizing: border-box; display: grid; gap: 12px; width: min(400px, calc(100vw - 32px)); max-height: 85vh; overflow: auto; padding: 20px; border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius, 12px); color: var(--primary-text-color); background: var(--card-background-color); }
      .options:not([open]) { display: none; }
      .options::backdrop { background: rgba(0, 0, 0, .45); }
      .options h2 { font-size: 20px; margin: 0 0 4px; }
      .option-field { display: grid; gap: 4px; min-width: 0; font-size: 14px; }
      .option-field select, .option-field input { box-sizing: border-box; width: 100%; min-width: 0; min-height: 44px; padding: 8px; font: inherit; color: var(--primary-text-color); background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 8px; }
      .options-help { color: var(--secondary-text-color); font-size: 12px; line-height: 18px; overflow-wrap: anywhere; }
      .warning { color: var(--warning-color, var(--primary-text-color)); font-size: 14px; line-height: 20px; overflow-wrap: anywhere; }
      .warning:empty { display: none; }
      .activity { font-size: 14px; line-height: 20px; min-width: 0; }
      .activity > summary { min-height: 44px; align-content: center; cursor: pointer; }
      .activity-list { display: grid; gap: 12px; padding: 4px 0 8px; }
      .activity-item { display: grid; gap: 4px; overflow-wrap: anywhere; }
      .activity-item + .activity-item { border-top: 1px solid var(--divider-color); padding-top: 12px; }
      .activity-meta, .activity-note { color: var(--secondary-text-color); overflow-wrap: anywhere; }
      .activity-download { margin-top: 4px; }
      .activity-feedback { color: var(--secondary-text-color); overflow-wrap: anywhere; }
      .activity-feedback.err { color: var(--error-color); }
      /* End shared document-card base. */`;

// Shared document-card option helpers. Keep this small block identical in both cards.
function optionChoices(select, choices, value) {
  const signature = JSON.stringify(choices);
  if (select.dataset.choices !== signature) {
    select.replaceChildren(...choices.map(([key, label, disabled]) => {
      const option = document.createElement('option');
      option.value = String(key); option.textContent = label; option.disabled = !!disabled;
      return option;
    }));
    select.dataset.choices = signature;
  }
  select.value = String(value);
}
function addOptionField(panel, key, label, type = 'select') {
  const wrapper = document.createElement('label');
  wrapper.className = 'option-field';
  const caption = translatedText(label, {}, panel._hass); wrapper.append(caption);
  const input = document.createElement(type === 'select' ? 'select' : 'input');
  input.dataset.option = key;
  input.setAttribute('aria-describedby', 'options-help');
  if (type !== 'select') input.type = type;
  wrapper.append(input); panel.append(wrapper);
  return input;
}
// Let HA own Back navigation, including the Android app's dialog handling.
// The native panel stays in the card's shadow root to retain its theme/styles.
const OPTIONS_TAG = `${TAG}-options-dialog`;
if (!customElements.get(OPTIONS_TAG)) {
  customElements.define(OPTIONS_TAG, class extends HTMLElement {
    showDialog(params) {
      this._open = true;
      const card = params?.card;
      this._card = card;
      // Older HA history entries cannot serialize the live card reference.
      if (!card) { this.closeDialog(); return; }
      card._optionsDialog = this;
      // HA may finish loading the host after navigation or a quick dismissal.
      if (!card.isConnected || !card._optionsOpen) this.closeDialog();
    }
    closeDialog() {
      if (!this._open) return true;
      this._open = false;
      const card = this._card;
      this._card = null;
      if (card) {
        card._optionsDialog = null;
        card._toggleOptions(false, card.isConnected);
      }
      this.dispatchEvent(new CustomEvent('dialog-closed', {
        bubbles: true, composed: true, detail: { dialog: OPTIONS_TAG },
      }));
      return true;
    }
  });
}
C.prototype._toggleOptions = function (open, restoreFocus = true) {
  if (!this._optionsPanel || (open && (!this.isConnected || this._optionsOpen))) return;
  const wasOpen = this._optionsOpen;
  this._optionsOpen = open;
  this._optionsPanel.hidden = !open;
  this._optionsButton.setAttribute('aria-expanded', String(open));
  if (open) {
    this._refreshOptions();
    this._optionsButton.focus();
    this.dispatchEvent(new CustomEvent('show-dialog', {
      bubbles: true, composed: true,
      detail: {
        dialogTag: OPTIONS_TAG, dialogImport: () => Promise.resolve(),
        dialogParams: { card: this },
      },
    }));
    if (!this._optionsPanel.open) this._optionsPanel.showModal?.();
    this._optionsPanel.querySelector('h2')?.focus();
  } else {
    this._optionsPanel.close?.();
    this._optionsDialog?.closeDialog();
    if (wasOpen && restoreFocus && this.isConnected) this._optionsButton.focus();
  }
};
C.prototype._createOptionsPanel = function () {
  this._optionsButton = this.shadowRoot.querySelector('.options-button');
  this._optionsButton[Symbol.for('HA focus target')] = true;
  const panel = document.createElement('dialog');
  panel._hass = this._hass;
  panel.className = 'options'; panel.id = 'options'; panel.hidden = true;
  panel.setAttribute('aria-labelledby', 'options-heading');
  const heading = document.createElement('h2'); heading.id = 'options-heading'; heading.tabIndex = -1; heading.autofocus = true;
  heading.dataset.i18n = 'dialog.title'; heading.textContent = this._t('dialog.title');
  panel.append(heading); this.shadowRoot.append(panel);
  panel.addEventListener('cancel', event => { event.preventDefault(); this._toggleOptions(false); });
  // Native dismissals can close the panel without going through our buttons.
  panel.addEventListener('close', () => {
    if (!panel.open) this._toggleOptions(false);
  });
  this._optionsPanel = panel;
  this._optionsButton.addEventListener('click', () => this._toggleOptions(!this._optionsOpen));
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); this._toggleOptions(false); }
  });
  this._optionHelp = document.createElement('div');
  this._optionHelp.id = 'options-help'; this._optionHelp.className = 'options-help'; this._optionHelp.setAttribute('aria-live', 'polite');
  return panel;
};
C.prototype._finishOptionsPanel = function () {
  this._optionsPanel.append(this._optionHelp);
  const done = document.createElement('button'); done.type = 'button'; done.dataset.i18n = 'action.done'; done.textContent = this._t('action.done');
  done.addEventListener('click', () => this._toggleOptions(false));
  this._optionsPanel.append(done);
};
// Native hosts own identity/surface; the existing card still owns every workflow.
const DOCUMENT_FEATURE_STYLES = `
  :host { height: auto; min-width: 0; }
  .feature-body { display: flex; flex-direction: column; gap: 8px; min-width: 0; color: var(--primary-text-color); container-type: inline-size; }
  .feature-body .actions { display: flex; align-items: stretch; gap: 8px; }
  .feature-body .primary, .feature-body .cancel { flex: 1; width: auto; min-width: 0; }
  .feature-body button { border-radius: var(--feature-border-radius, 12px); min-height: max(44px, var(--feature-height, 42px)); }
  .feature-body .options-button { margin: 0; }
  /* Allow a two-line primary label on narrow half-width mobile cards. */
  @container (max-width: 150px) { .feature-body .actions { min-height: 56px; } }
`;
C.prototype._configureFeatureView = function () {
  if (!this._featureMode) return;
  this._card.classList.add('feature-body');
  this.shadowRoot.querySelector('.header').hidden = true;
  this.shadowRoot.querySelector('.actions').append(this._optionsButton);
};

function activityDate(value) {
  if (typeof value !== 'string' || value.length > 64) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : null;
}
const ACTIVITY_OUTCOME = { completed: 'activity.completed', canceled: 'activity.canceled', aborted: 'activity.aborted', unknown: 'activity.unknown' };
const ACTIVITY_AVAILABILITY = { available: 'activity.available', expired: 'activity.expired', missing: 'activity.missing' };
function documentActivity(attrs, scan) {
  const field = scan ? 'latest_scan' : 'recent_activity';
  const raw = attrs?.[field];
  const values = scan ? [raw] : Array.isArray(raw) ? raw.slice(0, 10) : [];
  const records = [];
  for (const value of values) {
    if (!value || typeof value !== 'object' || typeof value.filename !== 'string' || value.filename.length > 160) continue;
    const expires = activityDate(value.expires_at), finished = activityDate(value.finished_at);
    const submitted = activityDate(value.submitted_at);
    if (expires === null || (scan ? finished === null : finished === null && submitted === null)) continue;
    let key, availability, url = null;
    if (scan) {
      if (typeof value.scan_id !== 'string' || !/^[a-f0-9]{12}$/.test(value.scan_id)
          || !['available', 'expired', 'missing'].includes(value.availability)) continue;
      key = value.scan_id;
      availability = expires <= Date.now() ? 'expired' : value.availability;
      if (availability === 'available' && value.file_url === `/api/escl_scan/file/${key}`) url = value.file_url;
      else if (availability === 'available') availability = 'missing';
    } else {
      if (!Number.isInteger(value.job_id) || value.job_id < 1 || submitted === null
          || !['completed', 'canceled', 'aborted', 'unknown'].includes(value.state) || expires <= Date.now()) continue;
      key = `${value.job_id}/${value.submitted_at}`;
    }
    records.push({ key, scanId: scan ? key : null, filename: value.filename, url,
      availability, expires, date: finished ?? submitted, finished: finished !== null,
      state: scan ? 'completed' : value.state,
      pages: Number.isInteger(value.pages_done) && value.pages_done >= 0 ? value.pages_done : null,
      unit: value.progress_unit === 'sheets' ? 'sheets' : 'pages' });
  }
  return { present: !!attrs && hasOwn(attrs, field), records };
}
C.prototype._activitySensor = function () {
  if (FEATURE_DOMAIN === 'escl_scan') return this._scanState();
  try { return this._hass?.states?.[this._sensorId()]; } catch { return null; }
};
C.prototype._activityTime = function (time) {
  try {
    return new Intl.DateTimeFormat(cardLanguage(this._hass), {
      dateStyle: 'medium', timeStyle: 'short', timeZone: this._hass?.config?.time_zone,
    }).format(time);
  } catch { return new Date(time).toLocaleString(); }
};
C.prototype._clearActivityTimer = function () {
  clearTimeout(this._activityTimer);
  this._activityTimer = null;
};
C.prototype._syncActivity = function () {
  if (!this._card) return;
  const scan = FEATURE_DOMAIN === 'escl_scan';
  const sensor = this._activitySensor(), entity = sensor?.entity_id || null;
  const data = documentActivity(sensor?.attributes, scan);
  if (!this._activityEl) {
    const details = document.createElement('details'); details.className = 'activity';
    const summary = document.createElement('summary');
    summary.textContent = this._t(scan ? 'activity.latest' : 'activity.recent');
    this._activityList = document.createElement('div'); this._activityList.className = 'activity-list';
    this._activityNote = document.createElement('div'); this._activityNote.className = 'activity-note';
    this._activityFeedback = document.createElement('div'); this._activityFeedback.className = 'activity-feedback';
    this._activityFeedback.setAttribute('aria-live', 'polite');
    details.append(summary, this._activityList, this._activityNote, this._activityFeedback);
    this._card.append(details); this._activityEl = details;
  }
  if (entity !== this._activityEntity) {
    this._activityEntity = entity; this._activityEl.open = false;
    this._activityMessage = null; this._expiredActivityId = null; this._historyDownload = null;
  }
  this._activityEl.hidden = !data.present;
  const records = data.records.map(record => record.key === this._expiredActivityId
    ? { ...record, availability: 'expired', url: null } : record);
  this._activityRecords = records;
  if (scan && this._completedScan && this._completedScan.scanId === records[0]?.key && !records[0].url) {
    this._downloadedScanId = this._completedScan.scanId;
    this._completedScan = null;
    this._setStatus('');
  }
  const signature = JSON.stringify([entity, cardLanguage(this._hass), this._hass?.config?.time_zone, records]);
  if (signature !== this._activitySignature) {
    this._activitySignature = signature;
    const hadFocus = this._activityList.contains(this.shadowRoot.activeElement);
    this._activityList.replaceChildren(); this._activityDownloadButton = null;
    this._activityEl.querySelector('summary').textContent = this._t(scan ? 'activity.latest' : 'activity.recent');
    for (const record of records) {
      const item = document.createElement('div'); item.className = 'activity-item';
      const title = document.createElement('div'); title.textContent = record.filename;
      const outcome = document.createElement('div');
      outcome.textContent = this._t(ACTIVITY_OUTCOME[record.state])
        + (record.pages === null ? '' : ' · ' + this._t(record.unit === 'sheets' ? 'activity.sheets' : 'activity.pages', { count: record.pages }));
      const time = document.createElement('time'); time.className = 'activity-meta';
      time.dateTime = new Date(record.date).toISOString();
      time.textContent = this._t(record.finished ? 'activity.finished' : 'activity.submitted', { time: this._activityTime(record.date) });
      item.append(title, outcome, time);
      if (scan) {
        const help = document.createElement('div'); help.className = 'activity-meta';
        help.textContent = this._t(ACTIVITY_AVAILABILITY[record.availability], { time: this._activityTime(record.expires) });
        item.append(help);
        if (record.url) {
          const button = document.createElement('button'); button.type = 'button'; button.className = 'activity-download';
          button.addEventListener('click', () => this._downloadLatest(record));
          item.append(button); this._activityDownloadButton = button;
        }
      }
      this._activityList.append(item);
    }
    this._activityNote.textContent = this._t(records.length ? (scan ? 'activity.scan_note' : 'activity.print_note')
      : (scan ? 'activity.no_scan' : 'activity.no_print'));
    if (hadFocus) this._activityEl.querySelector('summary').focus();
  }
  const pending = this._historyDownload?.record.key === records[0]?.key;
  if (this._activityDownloadButton) {
    this._activityDownloadButton.disabled = pending || !!this._downloadRequest || this._hass?.connected === false;
    this._activityDownloadButton.textContent = this._t(pending ? 'action.downloading' : 'action.download');
  }
  const message = this._activityMessage?.key === records[0]?.key ? this._activityMessage : null;
  setText(this._activityFeedback, message ? this._t(message.message) : '');
  this._activityFeedback.classList.toggle('err', !!message?.error);
  this._clearActivityTimer();
  const next = Math.min(...records.map(r => r.expires).filter(time => time > Date.now()));
  if (this.isConnected && Number.isFinite(next)) {
    this._activityTimer = setTimeout(() => this._syncActivity(), Math.min(86_400_000, Math.max(1, next - Date.now())));
  }
};

async function downloadScanPdf(owner, result, isCurrent) {
  const response = await owner._apiFetch(result.url);
  if (!isCurrent()) return 'abandoned';
  if (response.status === 404 || response.status === 410) return 'expired';
  if (!response.ok) throw new Error(owner._t('error.retry'));
  const blob = await response.blob();
  if (!isCurrent()) return 'abandoned';
  if (!blob.size || (blob.type && !['application/pdf', 'application/octet-stream'].includes(blob.type))) {
    throw new Error(owner._t('error.pdf'));
  }
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = result.filename; link.hidden = true;
  document.body.appendChild(link);
  try { link.click(); } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60_000); }
  return 'downloaded';
}
C.prototype._downloadLatest = async function (record) {
  if (!record.url || this._historyDownload || this._downloadRequest || this._hass?.connected === false) return;
  const token = { record, entity: this._activityEntity, epoch: this._requestEpoch || 0 };
  const current = () => this.isConnected && this._historyDownload === token
    && this._activityEntity === token.entity && (this._requestEpoch || 0) === token.epoch
    && this._activityRecords?.[0]?.key === record.key;
  this._historyDownload = token; this._activityMessage = null; this._syncActivity();
  try {
    const outcome = await downloadScanPdf(this, record, current);
    if (!current() || outcome === 'abandoned') return;
    if (outcome === 'expired') this._expiredActivityId = record.key;
    else if (this._completedScan?.scanId === record.scanId) {
      this._completedScan = null; this._downloadedScanId = record.scanId; this._setStatus('');
    }
    this._activityMessage = { key: record.key, message: outcome === 'expired' ? 'activity.expired' : 'activity.downloaded' };
  } catch {
    if (current()) this._activityMessage = { key: record.key, message: 'activity.download_failed', error: true };
  } finally {
    if (this._historyDownload === token) this._historyDownload = null;
    this._syncActivity(); this._syncControls();
  }
};

function supportsDocumentFeature(hass, context) {
  const id = context?.entity_id;
  if (typeof id !== 'string' || !id.startsWith('sensor.')) return false;
  const registered = hass?.entities?.[id];
  if (registered?.platform) return registered.platform === FEATURE_DOMAIN;
  // Older frontends can omit the registry; require the integration's enum shape.
  const attrs = hass?.states?.[id]?.attributes;
  return !!attrs && hasOwn(attrs, FEATURE_DOMAIN === 'escl_scan' ? 'scan_id' : 'job_id')
    && Array.isArray(attrs.options) && attrs.options.includes('processing-stopped')
    && attrs.options.includes(FEATURE_DOMAIN === 'escl_scan' ? 'awaiting-back-sides' : 'pending-held');
}

function preserveDocumentElements() {
  // A late scoped-registry polyfill can replace window.customElements after
  // this module has run. Native elements still exist, but HA's new registry
  // cannot find them. Keep the original constructors (and mounted workflows).
  const key = Symbol.for(TAG + '.element-registration');
  const tags = [TAG, FEATURE_TAG, TAG + '-editor', FEATURE_TAG + '-editor', OPTIONS_TAG];
  const definitions = tags.map(tag => [tag, customElements.get(tag)]);
  if (window[key]) {
    window[key].definitions = definitions;
    window[key].restore();
    return;
  }
  const state = { registry: customElements, definitions };
  state.restore = () => {
    const registry = window.customElements;
    if (registry === state.registry) return;
    for (const [tag, constructor] of state.definitions) {
      if (constructor && !registry.get(tag)) registry.define(tag, constructor);
    }
    state.registry = registry;
  };
  window[key] = state;
  // Capture script loads, including resources loaded after a slow first visit.
  // Normal loads cost only an identity check; no ongoing DOM scan or polling.
  document.addEventListener('load', state.restore, true);
  window.addEventListener('load', state.restore);
  window.addEventListener('pageshow', state.restore);
  window.addEventListener('location-changed', state.restore);
  customElements.whenDefined('home-assistant').then(state.restore);
}

function registerDocumentFeature() {
  const F = customElements.get(FEATURE_TAG);
  F.getStubConfig = () => ({ type: 'custom:' + FEATURE_TAG, duplex: false });
  const editorTag = FEATURE_TAG + '-editor';
  if (!customElements.get(editorTag)) {
    // Own tag and filtering also work when an older standalone editor loaded first.
    const Editor = customElements.get(TAG + '-editor');
    customElements.define(editorTag, class extends Editor {
      _render() {
        super._render();
        this._form.schema = this._form.schema.filter(field => !['title', 'entity'].includes(field.name));
      }
    });
  }
  F.getConfigElement = () => document.createElement(editorTag);
  F.prototype._t = C.prototype._t;
  F.prototype.setConfig = function (config) {
    if (!config || typeof config !== 'object') throw new Error(this._t('feature.config'));
    if (config.entity || config.title) throw new Error(this._t('feature.host_config'));
    C.prototype._validateConfig.call(this, config);
    this._config = { ...config };
    this._configRevision = (this._configRevision || 0) + 1;
    this._updateFeature();
  };
  for (const property of ['hass', 'context', 'stateObj', 'position']) {
    Object.defineProperty(F.prototype, property, {
      get() { return this['_' + property]; },
      set(value) {
        this['_' + property] = value;
        if (property === 'context') this._hasContext = true;
        this._updateFeature();
      },
      configurable: true,
    });
  }
  F.prototype._updateFeature = function () {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) {
      const root = this.attachShadow({ mode: 'open' });
      const style = document.createElement('style');
      style.textContent = ':host { display: block; min-width: 0; } .guidance { font-size: 14px; line-height: 20px; color: var(--secondary-text-color); overflow-wrap: anywhere; }';
      this._container = document.createElement('div');
      root.append(style, this._container);
      // Control gestures must not also invoke the host's tap/hold/double action.
      for (const type of ['click', 'dblclick', 'pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'keydown', 'keyup', 'action']) {
        root.addEventListener(type, event => event.stopPropagation());
      }
    }
    const context = this._hasContext ? this._context : this._stateObj;
    const entity = context?.entity_id;
    const supported = this._position !== 'inline' && supportsDocumentFeature(this._hass, context);
    if (!supported) {
      this._workflow?.remove();
      this._workflow = null;
      this._entity = null;
      this._container.className = 'guidance';
      this._container.textContent = this._t(this._position === 'inline' ? 'feature.bottom' : 'feature.target');
      return;
    }
    if (this._entity !== entity || !this._workflow) {
      this._workflow?.remove();
      this._workflow = document.createElement(TAG);
      this._workflow._featureMode = true;
      this._entity = entity;
      this._appliedRevision = null;
      this._container.className = '';
      this._container.replaceChildren();
    }
    if (this._appliedRevision !== this._configRevision) {
      this._workflow.setConfig({ ...this._config, type: 'custom:' + TAG, entity });
      this._appliedRevision = this._configRevision;
    }
    this._workflow.hass = this._hass;
    if (!this._workflow.parentNode) this._container.append(this._workflow);
  };
  window.customCardFeatures ||= [];
  if (!window.customCardFeatures.some(feature => feature.type === FEATURE_TAG)) {
    window.customCardFeatures.push({ type: FEATURE_TAG, name: localize('picker.name'), isSupported: supportsDocumentFeature, configurable: true });
  }
  preserveDocumentElements();
}
// END DOCUMENT CARD CORE v4
