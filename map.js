/* ==========================================================================
   map.js — Leaflet/OpenStreetMap risk map for NER India
   ========================================================================== */

'use strict';

let map = null;
let markersLayer = null;
let allLocations = [];
let selectedCode = null;

const MAP_CENTER = [25.6, 92.4];   // North Eastern Region of India
const MAP_ZOOM = 6;

function detailHtml(loc) {
  const r = loc.reading;
  if (!r) {
    return `<strong>${esc(loc.name)}</strong><span class="loc-state">${esc(loc.state)}</span>
      <p class="muted small">No reading stored for this location yet — shown as “No data” instead of estimating.</p>`;
  }
  return `
    <div class="alert-top">
      <strong>${esc(loc.name)}</strong>
      <span class="badge-level" data-level="${esc(r.risk_level)}">${esc(r.risk_level)}</span>
    </div>
    <span class="muted small">${esc(loc.state)} · ${esc(loc.code)}</span>
    <dl>
      <dt>Temperature</dt><dd>${num(r.temperature, 1, ' °C')}</dd>
      <dt>Rainfall 24 h</dt><dd>${num(r.rainfall_24h, 1, ' mm')}</dd>
      <dt>Rainfall 72 h</dt><dd>${num(r.rainfall_72h, 1, ' mm')}</dd>
      <dt>Humidity</dt><dd>${num(r.humidity, 1, ' %')}</dd>
      <dt>Soil moisture</dt><dd>${num(r.soil_moisture, 1, ' %')}</dd>
      <dt>Risk index</dt><dd>${num(r.risk_score, 1)}/100</dd>
      <dt>Terrain factor</dt><dd>${num(loc.susceptibility, 2)}${loc.slope_deg ? ' · ~' + loc.slope_deg + '° slope' : ''}</dd>
      <dt>Last update</dt><dd>${esc(formatTime(r.recorded_at))}</dd>
      <dt>Data source</dt><dd>${esc(r.data_source === 'observed' ? 'Observed (user entry)' : 'Simulated (sample)')}</dd>
    </dl>
    ${loc.terrain_note ? `<p class="muted small" style="margin-top:8px">${esc(loc.terrain_note)}</p>` : ''}`;
}

function popupHtml(loc) {
  const r = loc.reading;
  if (!r) return `<h4>${esc(loc.name)}</h4><p>No reading yet (No data).</p>`;
  return `
    <h4>${esc(loc.name)}, ${esc(loc.state)}</h4>
    <div><span class="badge-level" data-level="${esc(r.risk_level)}">${esc(r.risk_level)}</span>
      <span class="muted small">index ${num(r.risk_score, 1)}/100</span></div>
    <dl>
      <dt>Temp</dt><dd>${num(r.temperature, 1, ' °C')}</dd>
      <dt>Rain 24 h</dt><dd>${num(r.rainfall_24h, 1, ' mm')}</dd>
      <dt>Rain 72 h</dt><dd>${num(r.rainfall_72h, 1, ' mm')}</dd>
      <dt>Humidity</dt><dd>${num(r.humidity, 1, ' %')}</dd>
      <dt>Soil moisture</dt><dd>${num(r.soil_moisture, 1, ' %')}</dd>
      <dt>Updated</dt><dd>${esc(formatTime(r.recorded_at))}</dd>
      <dt>Source</dt><dd>${esc(r.data_source === 'observed' ? 'Observed' : 'Simulated')}</dd>
    </dl>
    <p class="muted small" style="margin-top:6px">Sample/simulated data — prototype only.</p>`;
}

function selectLocation(code) {
  selectedCode = code;
  const loc = allLocations.find(l => l.code === code);
  if (!loc) return;
  document.getElementById('mapDetail').innerHTML = detailHtml(loc);
  document.querySelectorAll('#mapList li').forEach(li => {
    li.classList.toggle('selected', li.dataset.code === code);
  });
}

function renderMarkers(filter) {
  if (!markersLayer) return;
  markersLayer.clearLayers();

  allLocations.forEach(loc => {
    const level = loc.reading ? loc.reading.risk_level : 'No data';
    if (filter !== 'all' && level !== filter) return;

    const score = loc.reading ? Number(loc.reading.risk_score) : 0;
    const marker = L.circleMarker([loc.lat, loc.lng], {
      radius: 9 + score / 12,
      color: '#04121f',
      weight: 1.5,
      fillColor: riskColor(level),
      fillOpacity: .85
    });
    marker.bindPopup(popupHtml(loc));
    marker.bindTooltip(`${loc.name} — ${level} (${num(score, 1)})`, { direction: 'top' });
    marker.on('click', () => selectLocation(loc.code));
    marker.addTo(markersLayer);
  });
}

function renderLocationList() {
  const list = document.getElementById('mapList');
  list.innerHTML = allLocations.map(loc => {
    const level = loc.reading ? loc.reading.risk_level : 'No data';
    return `<li data-code="${esc(loc.code)}">
      <span><span class="loc-name">${esc(loc.name)}</span><span class="loc-state">${esc(loc.state)}</span></span>
      <span class="badge-level" data-level="${esc(level)}">${esc(level)}</span>
    </li>`;
  }).join('');
  list.querySelectorAll('li').forEach(li => {
    li.addEventListener('click', () => {
      const loc = allLocations.find(l => l.code === li.dataset.code);
      selectLocation(li.dataset.code);
      if (map && loc) map.setView([loc.lat, loc.lng], 9);
    });
  });
}

async function loadMap() {
  if (!mapAvailable()) return;
  try {
    const data = await api('/api/locations');
    allLocations = data.locations || [];

    if (!map) {
      map = L.map('map', { scrollWheelZoom: true }).setView(MAP_CENTER, MAP_ZOOM);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(map);
      markersLayer = L.layerGroup().addTo(map);
      L.control.scale({ imperial: false }).addTo(map);
    }

    renderMarkers(document.getElementById('riskFilter').value);
    renderLocationList();
    if (selectedCode) selectLocation(selectedCode);
  } catch (err) {
    toast('Could not load map data: ' + err.message, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const filter = document.getElementById('riskFilter');
  if (filter) filter.addEventListener('change', () => renderMarkers(filter.value));
  const refresh = document.getElementById('mapRefreshBtn');
  if (refresh) refresh.addEventListener('click', () => { loadMap(); toast('Map data refreshed.', 'ok'); });
  loadMap();
});
