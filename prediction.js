/* ==========================================================================
   prediction.js — ML prediction page (demo mode aware, no invented metrics)
   ========================================================================== */

'use strict';

let importanceChart = null;
let compareChart = null;
let modelInfo = null;

function renderModeBanner(info) {
  modelInfo = info;
  const isDemo = info.mode === 'demo';
  const metrics = info.metrics || {};
  document.getElementById('modeText').innerHTML = `
    <strong>${esc(info.mode_label)}.</strong> ${esc(info.dataset_description)}
    Trained on <strong>${esc(info.trained_on_rows)}</strong> rows using
    <code>${esc(info.algorithm)}</code>.
    ${isDemo
      ? '<br><span class="badge-level" data-level="High">Demonstration mode — synthetic training data</span> ' +
        'Results below illustrate the pipeline only and are <strong>not real-world landslide predictions</strong>.'
      : '<br><span class="badge-level" data-level="Low">User dataset</span> Results apply to that dataset only.'}`;

  document.getElementById('modelStats').innerHTML = `
    <div class="model-stat"><span class="k">Data source</span><span class="v">${isDemo ? 'Synthetic (demo)' : 'User dataset'}</span></div>
    <div class="model-stat"><span class="k">Training rows</span><span class="v">${esc(info.trained_on_rows)}</span></div>
    <div class="model-stat"><span class="k">Held-out accuracy (this data only)</span><span class="v">${metrics.accuracy !== undefined ? (metrics.accuracy * 100).toFixed(1) + '%' : '—'}</span></div>
    <div class="model-stat"><span class="k">Macro F1 (this data only)</span><span class="v">${metrics.macro_f1 !== undefined ? metrics.macro_f1.toFixed(3) : '—'}</span></div>
    <div class="model-stat"><span class="k">3-fold CV accuracy (this data only)</span><span class="v">${metrics.cv_accuracy_mean != null ? (metrics.cv_accuracy_mean * 100).toFixed(1) + '% ± ' + (metrics.cv_accuracy_std * 100).toFixed(1) : '—'}</span></div>
    <div class="model-stat"><span class="k">Classes</span><span class="v" style="font-size:.95rem">${esc((metrics.classes || []).join(', '))}</span></div>`;

  document.getElementById('metricsNote').textContent = info.metrics_note;
  document.getElementById('importanceNote').textContent =
    'Feature importance from the trained Random Forest. In demo mode these reflect the synthetic rule, not field-verified drivers.';
}

function renderImportance(importances) {
  if (!chartsAvailable()) return;
  const ctx = document.getElementById('chartImportance');
  if (!ctx) return;
  const entries = Object.entries(importances).sort((a, b) => b[1] - a[1]);
  if (importanceChart) importanceChart.destroy();
  importanceChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: entries.map(e => e[0]),
      datasets: [{
        label: 'Relative importance',
        data: entries.map(e => e[1]),
        backgroundColor: 'rgba(34, 211, 238, .75)',
        borderColor: '#22d3ee', borderWidth: 1, borderRadius: 5
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: '#0d1a2e', borderColor: '#1e3763', borderWidth: 1 }
      },
      scales: { x: { beginAtZero: true, title: { display: true, text: 'Gini importance', font: { size: 11 } } } }
    }
  });
}

async function loadModelInfo() {
  try {
    const info = await api('/api/model-info');
    renderModeBanner(info);
    renderImportance(info.feature_importances || {});
    renderIndexTable(info.index_details || {});
  } catch (err) {
    document.getElementById('modeText').textContent = 'Could not load model information: ' + err.message;
  }
}

function renderIndexTable(details) {
  const list = document.getElementById('compareList');
  const bands = (details.risk_bands || [])
    .map(b => `${b.level}: ${b.min}–${b.max}`).join(' · ');
  const weights = Object.entries(details.weights || {})
    .map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(' · ');
  list.innerHTML = `
    <li><strong>Index weights:</strong> ${esc(weights)} · susceptibility multiplier from location terrain metadata.</li>
    <li><strong>Risk bands:</strong> ${esc(bands)}</li>
    <li><strong>Alert thresholds:</strong> ${esc(Object.entries(details.alert_thresholds || {}).map(([k, v]) => k + ' ≥ ' + v).join(' · '))}</li>
    <li>Both the index and the classifier are agreement checks on the same inputs — agreement does not make either one correct.</li>`;
}

async function loadLocations() {
  const select = document.getElementById('pLocation');
  try {
    const data = await api('/api/locations');
    select.innerHTML = '<option value="">— choose a location —</option>' +
      data.locations.map(l => `<option value="${esc(l.code)}">${esc(l.name)} — ${esc(l.state)} (terrain factor ${num(l.susceptibility, 2)})</option>`).join('');
  } catch (err) {
    toast('Could not load locations: ' + err.message, 'error');
  }
}

function renderPrediction(res) {
  const influenceRows = Object.entries(res.influences || {})
    .map(([name, pct]) => `<div class="influence-row">
        <span class="influence-name">${esc(name)}</span>
        <span class="influence-bar"><span class="influence-fill" style="width:${Math.min(100, pct)}%"></span></span>
        <span class="influence-pct">${pct}%</span>
      </div>`).join('');

  const probRows = Object.entries(res.class_probabilities || {})
    .map(([label, p]) => `<tr data-level="${esc(label)}">
        <td><span class="badge-level" data-level="${esc(label)}">${esc(label)}</span></td>
        <td>${(p * 100).toFixed(1)}%</td></tr>`).join('');

  const modeTag = res.mode === 'demo'
    ? '<span class="badge-level" data-level="High">Demo mode — synthetic model</span>'
    : '<span class="badge-level" data-level="Low">User dataset model</span>';

  document.getElementById('predictResult').innerHTML = `
    <div class="alert-top">
      <strong style="font-size:1.15rem">${esc(res.predicted_category)}</strong>
      <span class="badge-level" data-level="${esc(res.predicted_category)}">Predicted category</span>
      ${modeTag}
    </div>
    <p class="muted small" style="margin:6px 0 10px">${esc(res.mode_notice)}</p>

    <h3 class="mini-title">Inputs used</h3>
    <dl>
      <dt>Rainfall 24 h</dt><dd>${num(res.inputs.rainfall_24h, 1, ' mm')}</dd>
      <dt>Rainfall 72 h</dt><dd>${num(res.inputs.rainfall_72h, 1, ' mm')}</dd>
      <dt>Humidity</dt><dd>${num(res.inputs.humidity, 1, ' %')}</dd>
      <dt>Soil moisture</dt><dd>${num(res.inputs.soil_moisture, 1, ' %')}</dd>
      <dt>Temperature</dt><dd>${num(res.inputs.temperature, 1, ' °C')}</dd>
      <dt>Terrain susceptibility</dt><dd>${num(res.inputs.susceptibility, 2)}</dd>
    </dl>

    <h3 class="mini-title" style="margin-top:12px">Which factors influenced this result</h3>
    ${influenceRows}
    <p class="muted small">${esc(res.influences_note)}</p>

    <h3 class="mini-title" style="margin-top:12px">Class probabilities</h3>
    <table class="table"><tbody>${probRows}</tbody></table>

    <h3 class="mini-title" style="margin-top:12px">Cross-check with the transparent index</h3>
    <p class="small">
      Threshold index: <strong>${num(res.heuristic_index.score, 1)}/100</strong>
      (<span class="badge-level" data-level="${esc(res.heuristic_index.level)}">${esc(res.heuristic_index.level)}</span>)
      · classifier says <strong>${esc(res.predicted_category)}</strong> —
      ${res.agreement ? '<span style="color:#86efac">they agree</span>' : '<span style="color:#ffd7a8">they differ</span>'}.
    </p>
    <p class="muted small">${esc(res.metrics_note)}</p>`;

  renderCompareChart(res);
}

function renderCompareChart(res) {
  if (!chartsAvailable()) return;
  const ctx = document.getElementById('chartCompare');
  if (!ctx) return;
  const levels = ['Low', 'Moderate', 'High', 'Very High'];
  const probs = levels.map(l => ((res.class_probabilities || {})[l] || 0) * 100);
  if (compareChart) compareChart.destroy();
  compareChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: levels,
      datasets: [
        { label: 'Model probability (%)', data: probs, backgroundColor: levels.map(l => riskColor(l) + 'cc'),
          borderColor: levels.map(riskColor), borderWidth: 1, borderRadius: 5 },
        { label: 'Transparent index (0–100)', data: levels.map(() => res.heuristic_index.score),
          type: 'line', borderColor: '#22d3ee', borderDash: [5, 4], pointRadius: 0, tension: 0 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { boxWidth: 12, usePointStyle: true, font: { size: 11 } } },
        tooltip: { backgroundColor: '#0d1a2e', borderColor: '#1e3763', borderWidth: 1 }
      },
      scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: 'Percent / index', font: { size: 11 } } } }
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('predictForm');
  const msg = document.getElementById('predictMsg');
  const btn = document.getElementById('predictBtn');

  loadModelInfo();
  loadLocations();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    msg.textContent = '';
    msg.className = 'form-msg';
    showFieldErrors(form, {});

    const payload = { location_code: form.location_code.value, use_latest: document.getElementById('useLatest').checked ? 1 : 0 };
    ['rainfall_24h', 'rainfall_72h', 'humidity', 'soil_moisture', 'temperature'].forEach(field => {
      const value = form[field].value.trim();
      if (value !== '') payload[field] = Number(value);
    });

    if (!payload.location_code && !payload.rainfall_24h) {
      msg.textContent = 'Choose a location or type the readings to predict from.';
      msg.classList.add('error');
      return;
    }

    setLoading(btn, true, 'Predicting…');
    try {
      const res = await api('/api/predict', { method: 'POST', body: payload });
      renderPrediction(res);
      msg.textContent = `Prediction complete: ${res.predicted_category}` +
        (res.mode === 'demo' ? ' (demonstration model trained on synthetic data).' : '.');
      msg.classList.add('ok');
      toast('Prediction complete: ' + res.predicted_category, res.mode === 'demo' ? 'warn' : 'ok');
    } catch (err) {
      if (err.payload && err.payload.errors) {
        showFieldErrors(form, err.payload.errors);
        msg.textContent = 'Please provide valid inputs for the highlighted fields.';
      } else {
        msg.textContent = 'Prediction failed: ' + err.message;
      }
      msg.classList.add('error');
      toast('Prediction failed: ' + err.message, 'error');
    } finally {
      setLoading(btn, false);
    }
  });

  document.getElementById('pLocation').addEventListener('change', (e) => {
    if (e.target.value) {
      msg.textContent = 'Latest stored reading for this location will be used where a field is left blank.';
      msg.className = 'form-msg';
    }
  });
});
