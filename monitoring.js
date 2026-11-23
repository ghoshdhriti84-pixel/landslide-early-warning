/* ==========================================================================
   monitoring.js — reading entry form, validation and live refresh
   ========================================================================== */

'use strict';

let locTrendChart = null;
let trendLocationsReady = false;

const RULES = {
  temperature: { min: -20, max: 55, label: 'Temperature' },
  rainfall_24h: { min: 0, max: 1000, label: 'Rainfall (24 h)' },
  humidity: { min: 0, max: 100, label: 'Humidity' },
  soil_moisture: { min: 0, max: 100, label: 'Soil moisture' }
};

/** Client-side validation mirrors the server rules for instant feedback. */
function validateLocally(form) {
  const errors = {};
  const code = form.location_code.value.trim();
  if (!code) errors.location_code = 'Please choose a monitoring location.';

  Object.keys(RULES).forEach(field => {
    const rule = RULES[field];
    const raw = form[field].value.trim();
    if (raw === '') { errors[field] = rule.label + ' is required.'; return; }
    const value = Number(raw);
    if (!isFinite(value)) { errors[field] = rule.label + ' must be a number.'; return; }
    if (value < rule.min || value > rule.max) {
      errors[field] = `${rule.label} must be between ${rule.min} and ${rule.max}.`;
    }
  });
  return errors;
}

async function loadLocations() {
  const select = document.getElementById('location_code');
  try {
    const data = await api('/api/locations');
    const options = data.locations
      .map(l => `<option value="${esc(l.code)}">${esc(l.name)} — ${esc(l.state)} (terrain factor ${num(l.susceptibility, 2)})</option>`)
      .join('');
    select.innerHTML = '<option value="">— choose a location —</option>' + options;

    const trend = document.getElementById('trendLocation');
    if (trend && !trendLocationsReady) {
      trend.innerHTML = '<option value="">— choose a location —</option>' + options;
      trend.value = data.locations.length ? data.locations[0].code : '';
      trendLocationsReady = true;
      loadLocationTrend();
    }
  } catch (err) {
    select.innerHTML = '<option value="">Could not load locations</option>';
    toast('Could not load locations: ' + err.message, 'error');
  }
}

function renderSourceTag(source) {
  return source === 'observed'
    ? '<span class="badge-level" data-level="Low">Observed</span>'
    : '<span class="badge-level" data-level="No data">Simulated</span>';
}

async function loadReadingsTable() {
  const tbody = document.getElementById('readingsTable');
  try {
    const data = await api('/api/readings/recent?limit=25');
    if (!data.readings.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="muted small">No readings stored yet.</td></tr>';
      return;
    }
    tbody.innerHTML = data.readings.map(r => `
      <tr>
        <td>${esc(r.location_name)}<span class="loc-state">${esc(r.state || '')}</span></td>
        <td>${num(r.temperature, 1)}</td>
        <td>${num(r.rainfall_24h, 1)}</td>
        <td>${num(r.rainfall_72h, 1)}</td>
        <td>${num(r.humidity, 1)}</td>
        <td>${num(r.soil_moisture, 1)}</td>
        <td><span class="badge-level" data-level="${esc(r.risk_level)}">${esc(r.risk_level)} ${num(r.risk_score, 1)}</span></td>
        <td>${renderSourceTag(r.data_source)}</td>
        <td class="small">${esc(formatTime(r.recorded_at))}</td>
      </tr>`).join('');
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="9" class="muted small">Could not load readings: ' + esc(err.message) + '</td></tr>';
  }
}

function renderSubmissionResult(res) {
  const r = res.reading;
  const explanation = res.risk_explanation || {};
  const contributions = explanation.contributions || {};
  const rows = Object.keys(contributions)
    .sort((a, b) => contributions[b] - contributions[a])
    .map(key => {
      const value = contributions[key];
      const pct = Math.min(100, Math.abs(value));
      return `<div class="influence-row">
        <span class="influence-name">${esc(key)}</span>
        <span class="influence-bar"><span class="influence-fill" style="width:${pct}%"></span></span>
        <span class="influence-pct">${value >= 0 ? '+' : ''}${value}</span>
      </div>`;
    }).join('');

  document.getElementById('submissionResult').innerHTML = `
    <div class="alert-top">
      <strong>${esc(r.location_name)}</strong>
      <span class="badge-level" data-level="${esc(r.risk_level)}">${esc(r.risk_level)}</span>
      <span class="muted small">risk index ${num(r.risk_score, 1)}/100</span>
    </div>
    <dl>
      <dt>Temperature</dt><dd>${num(r.temperature, 1, ' °C')}</dd>
      <dt>Rainfall 24 h</dt><dd>${num(r.rainfall_24h, 1, ' mm')}</dd>
      <dt>Rainfall 72 h (auto)</dt><dd>${num(r.rainfall_72h, 1, ' mm')}</dd>
      <dt>Humidity</dt><dd>${num(r.humidity, 1, ' %')}</dd>
      <dt>Soil moisture</dt><dd>${num(r.soil_moisture, 1, ' %')}</dd>
      <dt>Stored as</dt><dd>Observed (id ${r.id})</dd>
      <dt>Timestamp</dt><dd>${esc(formatTime(r.recorded_at))}</dd>
    </dl>
    <p class="muted small" style="margin-top:10px">${esc(explanation.rainfall_72h_note || '')}</p>
    <p class="muted small">${esc(explanation.method || '')} Contribution = percentage points added to the index.</p>
    ${rows}
    ${res.alert ? `<div class="alert-item" data-level="${esc(res.alert.alert_level)}" style="margin-top:10px">
        <div class="alert-main">
          <div class="alert-top"><span class="badge-level" data-level="${esc(res.alert.alert_level)}">${esc(res.alert.alert_level)}</span>
            <strong>New alert raised</strong></div>
          <p class="alert-msg">${esc(res.alert.message)}</p>
          <div class="alert-action"><strong>Recommended action:</strong> ${esc(res.alert.action)}</div>
        </div>
      </div>` : '<p class="muted small">No new alert: the risk index stayed below the configured thresholds.</p>'}
  `;
}

async function loadLocationTrend() {
  const select = document.getElementById('trendLocation');
  const code = select ? select.value : '';
  const ctx = document.getElementById('chartLocationTrend');
  if (!ctx) return;
  if (!chartsAvailable()) return;
  if (!code) { if (locTrendChart) { locTrendChart.destroy(); locTrendChart = null; } return; }

  try {
    const data = await api('/api/readings?location_code=' + encodeURIComponent(code) + '&limit=48');
    const rows = data.readings.slice().reverse();  // oldest first
    const labels = rows.map(r => formatTime(r.recorded_at).replace(/,.*$/, ''));
    locTrendChart && locTrendChart.destroy();
    locTrendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Risk index',
            data: rows.map(r => r.risk_score),
            borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,.15)',
            fill: true, tension: .35, yAxisID: 'y1'
          },
          {
            label: 'Rainfall 24 h (mm)',
            data: rows.map(r => r.rainfall_24h),
            borderColor: '#22d3ee', backgroundColor: 'transparent', tension: .35, yAxisID: 'y'
          },
          {
            label: 'Soil moisture (%)',
            data: rows.map(r => r.soil_moisture),
            borderColor: '#3b82f6', backgroundColor: 'transparent',
            borderDash: [5, 4], tension: .35, yAxisID: 'y'
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { boxWidth: 12, usePointStyle: true, font: { size: 11 } } },
          tooltip: { backgroundColor: '#0d1a2e', borderColor: '#1e3763', borderWidth: 1 }
        },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: 'mm / %', font: { size: 11 } } },
          y1: { position: 'right', beginAtZero: true, max: 100, grid: { drawOnChartArea: false },
                title: { display: true, text: 'Risk index', font: { size: 11 } } }
        }
      }
    });
  } catch (err) {
    toast('Could not load the location trend: ' + err.message, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('readingForm');
  const msg = document.getElementById('formMsg');
  const submitBtn = document.getElementById('submitReading');

  loadLocations();
  loadReadingsTable();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    msg.textContent = '';
    msg.className = 'form-msg';
    showFieldErrors(form, {});

    const localErrors = validateLocally(form);
    if (Object.keys(localErrors).length) {
      showFieldErrors(form, localErrors);
      msg.textContent = 'Please correct the highlighted fields — nothing was submitted.';
      msg.classList.add('error');
      toast('Validation failed. Fix the highlighted fields.', 'warn');
      return;
    }

    const payload = {
      location_code: form.location_code.value.trim(),
      temperature: Number(form.temperature.value),
      rainfall_24h: Number(form.rainfall_24h.value),
      humidity: Number(form.humidity.value),
      soil_moisture: Number(form.soil_moisture.value)
    };

    setLoading(submitBtn, true, 'Saving…');
    try {
      const res = await api('/api/readings', { method: 'POST', body: payload });
      msg.textContent = res.alert
        ? `Reading stored. Risk level: ${res.reading.risk_level}. A ${res.alert.alert_level} alert was raised.`
        : `Reading stored. Risk level: ${res.reading.risk_level}. No alert threshold crossed.`;
      msg.classList.add('ok');
      renderSubmissionResult(res);
      toast('Reading saved and risk recalculated.', 'ok');
      loadReadingsTable();
      loadLocationTrend();
      refreshNotificationPanel();
    } catch (err) {
      if (err.payload && err.payload.errors) {
        showFieldErrors(form, err.payload.errors);
        msg.textContent = 'Server rejected the reading. Please check the highlighted fields.';
      } else {
        msg.textContent = 'Could not save the reading: ' + err.message;
      }
      msg.classList.add('error');
      toast('Submission failed: ' + err.message, 'error');
    } finally {
      setLoading(submitBtn, false);
    }
  });

  document.getElementById('fillSampleBtn').addEventListener('click', () => {
    const select = document.getElementById('location_code');
    if (!select.value) select.value = select.options[1] ? select.options[1].value : '';
    form.temperature.value = '23.4';
    form.rainfall_24h.value = '168';
    form.humidity.value = '93';
    form.soil_moisture.value = '78';
    msg.textContent = 'Example monsoon values filled in — review before submitting.';
    msg.className = 'form-msg';
  });

  document.getElementById('resetBtn').addEventListener('click', () => {
    showFieldErrors(form, {});
    msg.textContent = '';
    msg.className = 'form-msg';
  });

  document.getElementById('readingsRefreshBtn').addEventListener('click', () => {
    loadReadingsTable();
    toast('Readings refreshed.', 'ok');
  });

  document.getElementById('trendLocation').addEventListener('change', loadLocationTrend);
});
