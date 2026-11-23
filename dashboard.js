/* ==========================================================================
   dashboard.js — summary cards, risk indicator and charts
   ========================================================================== */

'use strict';

const charts = { trend: null, pie: null, bar: null };

// Guarded so the dashboard still renders when Chart.js is unavailable (offline).
if (typeof Chart !== 'undefined') {
  Chart.defaults.color = '#9fb4d6';
  Chart.defaults.borderColor = 'rgba(30, 55, 99, .55)';
  Chart.defaults.font.family = '"Segoe UI", Roboto, Arial, sans-serif';
}

function fillSummary(data) {
  const current = data.current || {};
  document.getElementById('mTemp').textContent = num(current.temperature, 1);
  document.getElementById('mRain').textContent = num(current.rainfall_24h, 1);
  document.getElementById('mHum').textContent = num(current.humidity, 1);
  document.getElementById('mSoil').textContent = num(current.soil_moisture, 1);

  const pill = document.getElementById('riskPill');
  pill.textContent = data.overall_risk_level;
  pill.dataset.level = data.overall_risk_level;
  document.getElementById('riskScore').textContent = num(current.risk_score, 1);

  document.getElementById('statLocations').textContent = data.monitored_locations;
  document.getElementById('statAlerts').textContent = data.active_alerts;

  const peak = data.highest_risk_location;
  document.getElementById('peakName').textContent = peak ? peak.name + ', ' + peak.state : '—';
  document.getElementById('peakMeta').textContent = peak
    ? `index ${num(peak.risk_score, 1)}/100 · ${peak.risk_level}`
    : 'No readings stored yet';

  document.getElementById('riskDistribution').innerHTML = '';
  renderDistribution(document.getElementById('riskDistribution'), data.risk_distribution || {}, data.monitored_locations);

  document.getElementById('lastUpdate').textContent =
    'Last update: ' + formatTime(data.last_update) + ` · ${data.locations_reporting} of ${data.monitored_locations} locations reporting`;
}

function renderTrend(series) {
  if (!chartsAvailable()) return;
  const ctx = document.getElementById('chartTrend');
  if (!ctx) return;
  const config = {
    type: 'line',
    data: {
      labels: series.labels,
      datasets: [
        {
          label: 'Avg rainfall (mm/24 h)',
          data: series.rainfall,
          borderColor: '#22d3ee',
          backgroundColor: 'rgba(34, 211, 238, .18)',
          fill: true,
          tension: .35,
          yAxisID: 'y'
        },
        {
          label: 'Avg risk index (0–100)',
          data: series.risk_score,
          borderColor: '#f97316',
          backgroundColor: 'rgba(249, 115, 22, .12)',
          borderDash: [6, 4],
          tension: .35,
          yAxisID: 'y1'
        },
        {
          label: 'Alerts generated',
          data: series.alerts,
          borderColor: '#ef4444',
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          tension: .2,
          yAxisID: 'y1'
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
        y: {
          position: 'left', beginAtZero: true,
          title: { display: true, text: 'Rainfall (mm)', font: { size: 11 } }
        },
        y1: {
          position: 'right', beginAtZero: true, max: 100, grid: { drawOnChartArea: false },
          title: { display: true, text: 'Risk index / alerts', font: { size: 11 } }
        }
      }
    }
  };
  if (charts.trend) charts.trend.destroy();
  charts.trend = new Chart(ctx, config);
  document.getElementById('trendNote').textContent =
    `${series.labels.length} day(s) of stored readings · ${series.data_note}`;
}

function renderPie(counts) {
  if (!chartsAvailable()) return;
  const ctx = document.getElementById('chartRiskPie');
  if (!ctx) return;
  const labels = RISK_ORDER.filter(l => (counts[l] || 0) > 0);
  const values = labels.map(l => counts[l] || 0);
  const config = {
    type: 'doughnut',
    data: {
      labels: labels.length ? labels : ['No data'],
      datasets: [{
        data: values.length ? values : [1],
        backgroundColor: (labels.length ? labels : ['No data']).map(riskColor),
        borderColor: '#0d1a2e',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '58%',
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, usePointStyle: true, font: { size: 11 } } },
        tooltip: { backgroundColor: '#0d1a2e', borderColor: '#1e3763', borderWidth: 1 }
      }
    }
  };
  if (charts.pie) charts.pie.destroy();
  charts.pie = new Chart(ctx, config);
}

function renderRiskByLocation(locations) {
  if (!chartsAvailable()) return;
  const ctx = document.getElementById('chartRiskBar');
  if (!ctx) return;
  const rows = locations
    .filter(l => l.reading)
    .map(l => ({
      name: l.name,
      score: Number(l.reading.risk_score),
      level: l.reading.risk_level
    }))
    .sort((a, b) => a.score - b.score);

  const config = {
    type: 'bar',
    data: {
      labels: rows.map(r => r.name),
      datasets: [{
        label: 'Risk index',
        data: rows.map(r => r.score),
        backgroundColor: rows.map(r => riskColor(r.level) + 'cc'),
        borderColor: rows.map(r => riskColor(r.level)),
        borderWidth: 1,
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0d1a2e', borderColor: '#1e3763', borderWidth: 1,
          callbacks: {
            afterLabel: (item) => 'Category: ' + rows[item.dataIndex].level
          }
        }
      },
      scales: {
        x: { beginAtZero: true, max: 100, title: { display: true, text: 'Risk index (0–100)', font: { size: 11 } } },
        y: { ticks: { font: { size: 10 } } }
      }
    }
  };
  if (charts.bar) charts.bar.destroy();
  charts.bar = new Chart(ctx, config);
}

async function loadDashboardAlerts() {
  const box = document.getElementById('dashAlertList');
  box.innerHTML = '<p class="muted small">Loading alerts…</p>';
  try {
    const data = await api('/api/alerts?limit=5&include_ack=0');
    if (!data.alerts.length) {
      box.innerHTML = '<p class="muted small">No unacknowledged alerts. Risk levels are currently below the configured thresholds.</p>';
      return;
    }
    box.innerHTML = data.alerts.map(a => alertItemHtml(a, { showAck: true })).join('');
    bindAckButtons(box, loadDashboardAlerts);
  } catch (err) {
    box.innerHTML = '<p class="muted small">Could not load alerts: ' + esc(err.message) + '</p>';
  }
}

async function loadDashboard() {
  try {
    const [summary, series, locations] = await Promise.all([
      api('/api/summary'),
      api('/api/trends?hours=168'),
      api('/api/locations')
    ]);
    fillSummary(summary);
    renderTrend(series);
    renderPie(summary.risk_distribution || {});
    renderRiskByLocation(locations.locations || []);
  } catch (err) {
    toast('Dashboard could not refresh: ' + err.message, 'error');
  }
  loadDashboardAlerts();
}

document.addEventListener('DOMContentLoaded', () => {
  const refreshBtn = document.getElementById('refreshAllBtn');
  if (refreshBtn) refreshBtn.addEventListener('click', () => { loadDashboard(); toast('Dashboard refreshed.', 'ok'); });
  const alertBtn = document.getElementById('refreshAlertsBtn');
  if (alertBtn) alertBtn.addEventListener('click', loadDashboardAlerts);
  window.onAlertsChanged = () => { loadDashboard(); };

  loadDashboard();
  // Auto-refresh every 60 s so new readings appear without a manual reload.
  setInterval(loadDashboard, 60000);
});
