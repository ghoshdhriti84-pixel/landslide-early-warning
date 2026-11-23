/* ==========================================================================
   script.js — shared helpers for every page
   (API access, toasts, risk colours, notification panel, nav)
   ========================================================================== */

'use strict';

/** Colour tokens shared with style.css */
const RISK_COLORS = {
  'Low': '#22c55e',
  'Moderate': '#facc15',
  'High': '#f97316',
  'Very High': '#ef4444',
  'No data': '#64748b',
  'Advisory': '#facc15',
  'Warning': '#f97316',
  'Severe': '#ef4444'
};

const RISK_ORDER = ['Low', 'Moderate', 'High', 'Very High'];
const ALERT_ORDER = ['Advisory', 'Warning', 'Severe'];

/** Escape user/data text before inserting into innerHTML. */
function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Human readable number; returns em dash for missing values (never invents data). */
function num(value, digits = 1, unit = '') {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!isFinite(n)) return '—';
  return n.toFixed(digits) + unit;
}

function riskColor(level) { return RISK_COLORS[level] || RISK_COLORS['No data']; }

function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(String(iso).replace(' ', 'T'));
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

function timeAgo(iso) {
  if (!iso) return '—';
  const d = new Date(String(iso).replace(' ', 'T'));
  if (isNaN(d.getTime())) return String(iso);
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + ' min ago';
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return hrs + ' h ago';
  return Math.round(hrs / 24) + ' d ago';
}

/**
 * Fetch JSON from the backend.
 * Throws an Error carrying `payload` so callers can read field-level validation
 * errors from the API response.
 */
async function api(path, options = {}) {
  const config = Object.assign({ headers: {} }, options);
  if (config.body && !(config.body instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json';
    if (typeof config.body !== 'string') config.body = JSON.stringify(config.body);
  }
  const response = await fetch(path, config);
  let payload = null;
  try { payload = await response.json(); } catch (_) { payload = null; }

  if (!response.ok) {
    const message = (payload && (payload.error || Object.values(payload.errors || {})[0]))
      || ('Request failed with status ' + response.status);
    const err = new Error(message);
    err.payload = payload;
    err.status = response.status;
    throw err;
  }
  return payload;
}

/** Small toast notification stack (bottom-right). */
function toast(message, type = 'info', timeout = 4200) {
  const stack = document.getElementById('toastStack');
  if (!stack) { return; }
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.setAttribute('role', 'status');
  el.innerHTML = esc(message);
  stack.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity .3s';
    setTimeout(() => el.remove(), 320);
  }, timeout);
}

/** Loading state helper for buttons with a .spinner child. */
function setLoading(button, loading, labelWhenLoading) {
  if (!button) return;
  const spinner = button.querySelector('.spinner');
  const label = button.querySelector('.btn-label');
  button.disabled = !!loading;
  if (spinner) spinner.hidden = !loading;
  if (label) {
    if (loading) {
      label.dataset.original = label.dataset.original || label.textContent;
      label.textContent = labelWhenLoading || 'Working…';
    } else if (label.dataset.original) {
      label.textContent = label.dataset.original;
    }
  }
}

/** Show or clear per-field validation errors returned by the API. */
function showFieldErrors(container, errors) {
  container.querySelectorAll('.error-text').forEach(el => { el.textContent = ''; });
  container.querySelectorAll('input, select').forEach(el => el.classList.remove('invalid'));
  Object.keys(errors || {}).forEach(field => {
    const target = container.querySelector('[data-error="' + field + '"]');
    if (target) target.textContent = errors[field];
    const input = container.querySelector('[name="' + field + '"], #' + field);
    if (input) input.classList.add('invalid');
  });
}

/** Chart.js guard: friendly message instead of a blank canvas when offline. */
function chartsAvailable() {
  if (typeof Chart === 'undefined') {
    toast('Chart.js could not load (no internet?). Charts are unavailable but data is still shown.', 'warn', 7000);
    return false;
  }
  return true;
}

function mapAvailable() {
  if (typeof L === 'undefined') {
    toast('Leaflet could not load (no internet?). The map is unavailable.', 'warn', 7000);
    return false;
  }
  return true;
}

/* ------------------------------------------------------------------ */
/* Sidebar + notification panel (present on every page)                */
/* ------------------------------------------------------------------ */

function initNav() {
  const toggle = document.getElementById('navToggle');
  const sidebar = document.getElementById('sidebar');
  if (toggle && sidebar) {
    toggle.addEventListener('click', () => {
      const open = sidebar.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  }
}

function alertItemHtml(alert, options = {}) {
  const level = alert.alert_level;
  const ackBtn = options.showAck && !alert.acknowledged
    ? `<button class="btn btn-ghost btn-sm" data-ack="${alert.id}" type="button">Mark read</button>`
    : (alert.acknowledged ? '<span class="muted small">Read</span>' : '');
  return `
    <div class="alert-item ${alert.acknowledged ? 'acked' : ''}" data-level="${esc(level)}">
      <div class="alert-main">
        <div class="alert-top">
          <span class="badge-level" data-level="${esc(level)}">${esc(level)}</span>
          <span class="alert-loc">${esc(alert.location_name)}${alert.state ? ', ' + esc(alert.state) : ''}</span>
          <span class="muted small">risk index ${num(alert.risk_score, 1)}/100</span>
        </div>
        <p class="alert-msg">${esc(alert.message)}</p>
        <div class="alert-action"><strong>Recommended action:</strong> ${esc(alert.action)}</div>
        <div class="alert-meta">${esc(formatTime(alert.created_at))} · ${esc(timeAgo(alert.created_at))}</div>
      </div>
      <div class="alert-side">${ackBtn}</div>
    </div>`;
}

function bindAckButtons(scope, onDone) {
  scope.querySelectorAll('[data-ack]').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await api('/api/alerts/' + btn.dataset.ack + '/ack', { method: 'POST' });
        toast('Alert marked as read.', 'ok');
        if (onDone) onDone();
        refreshNotificationPanel();
      } catch (err) {
        btn.disabled = false;
        toast('Could not update alert: ' + err.message, 'error');
      }
    });
  });
}

/** Top-bar bell: unread count + dropdown preview. */
async function refreshNotificationPanel() {
  const countEl = document.getElementById('notifCount');
  const bodyEl = document.getElementById('notifBody');
  if (!countEl || !bodyEl) return;
  try {
    const data = await api('/api/alerts?limit=5&include_ack=0');
    const total = data.total_unacknowledged || 0;
    countEl.textContent = String(total);
    countEl.hidden = total === 0;
    if (!data.alerts.length) {
      bodyEl.innerHTML = '<p class="muted small" style="padding:12px">No unread alerts right now.</p>';
      return;
    }
    bodyEl.innerHTML = data.alerts.map(a => alertItemHtml(a, { showAck: true })).join('');
    bindAckButtons(bodyEl, null);
  } catch (err) {
    bodyEl.innerHTML = '<p class="muted small" style="padding:12px">Could not load alerts: ' + esc(err.message) + '</p>';
  }
}

function initNotificationPanel() {
  const btn = document.getElementById('notifBtn');
  const panel = document.getElementById('notifPanel');
  const ackAll = document.getElementById('ackAllBtn');
  if (btn && panel) {
    btn.addEventListener('click', (event) => {
      event.stopPropagation();
      const hidden = panel.hidden;
      panel.hidden = !hidden;
      btn.setAttribute('aria-expanded', String(hidden));
      if (hidden) refreshNotificationPanel();
    });
    document.addEventListener('click', (event) => {
      if (!panel.hidden && !panel.contains(event.target) && event.target !== btn) {
        panel.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') panel.hidden = true; });
  }
  if (ackAll) {
    ackAll.addEventListener('click', async () => {
      try {
        const res = await api('/api/alerts/ack-all', { method: 'POST' });
        toast(res.acknowledged_count + ' alert(s) marked as read.', 'ok');
        refreshNotificationPanel();
        if (typeof window.onAlertsChanged === 'function') window.onAlertsChanged();
      } catch (err) {
        toast('Could not update alerts: ' + err.message, 'error');
      }
    });
  }
}

/** Shared risk-distribution bars used on the dashboard. */
function renderDistribution(container, counts, total) {
  if (!container) return;
  const sum = total || RISK_ORDER.reduce((acc, k) => acc + (counts[k] || 0), 0) || 1;
  container.innerHTML = RISK_ORDER.map(level => {
    const value = counts[level] || 0;
    const pct = Math.round((value / sum) * 100);
    return `<div class="dist-row" data-level="${level}">
      <span class="badge-level" data-level="${level}" style="min-width:78px;text-align:center">${level}</span>
      <span class="dist-bar"><span class="dist-fill" style="width:${pct}%"></span></span>
      <span class="dist-val">${value}</span>
    </div>`;
  }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initNotificationPanel();
  refreshNotificationPanel();
  // keep the bell count fresh without a manual reload
  setInterval(refreshNotificationPanel, 60000);
});
