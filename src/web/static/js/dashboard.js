/**
 * IHA Pilot Asistanı — Dashboard JavaScript
 * ==========================================
 * Gerçek zamanlı WebSocket telemetri, harita güncelleme,
 * komut gönderme ve görsel durum yönetimi.
 *
 * Mimari:
 *   Socket.IO → telemetri_update → updateTelemetry()
 *   sendCommand() → POST /api/command → updateResult()
 *   Leaflet → drone marker animasyonu
 */

'use strict';

// ── Sabitler ──────────────────────────────────────────────────────────────
const HOME_LAT  = 39.9334;   // Ankara simülasyon referansı
const HOME_LNG  = 32.8597;
const M_PER_LAT = 111320;    // 1 derece enlem ≈ 111320 metre

// ── Durum ─────────────────────────────────────────────────────────────────
let logCount = 0;
let stats = { total: 0, success: 0, safety_rejected: 0, clarified: 0 };
let droneMarker = null;
let homemarker  = null;
let droneTrail  = [];
let trailPolyline = null;
let map = null;

// ── Leaflet Harita Başlatma ────────────────────────────────────────────────
function initMap() {
  map = L.map('map', {
    center: [HOME_LAT, HOME_LNG],
    zoom: 17,
    zoomControl: true,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 20,
  }).addTo(map);

  // Başlangıç (Home) işareti
  const homeIcon = L.divIcon({
    html: `<div style="
      width:14px;height:14px;
      background:#3b82f6;
      border:2px solid white;
      border-radius:50%;
    "></div>`,
    className: '',
    iconAnchor: [7, 7],
  });
  homeMarker = L.marker([HOME_LAT, HOME_LNG], { icon: homeIcon })
    .addTo(map)
    .bindPopup('🏠 Başlangıç Noktası');

  // Drone işareti (başlangıçta home'da)
  droneMarker = createDroneMarker(HOME_LAT, HOME_LNG, 0, 0);
  droneMarker.addTo(map);

  // İz çizgisi
  trailPolyline = L.polyline([], {
    color: '#3b82f6',
    weight: 2,
    opacity: 0.6,
    dashArray: '3 3',
  }).addTo(map);
}

function createDroneMarker(lat, lng, heading, altitude) {
  const icon = L.divIcon({
    html: `<div style="
      width:20px;height:20px;
      background:${altitude > 0 ? '#10b981' : '#475569'};
      border:2px solid white;
      border-radius:50% 50% 50% 0;
      transform:rotate(${heading - 45}deg);
      transition:all 0.3s ease;
    "></div>`,
    className: '',
    iconAnchor: [10, 10],
  });

  if (droneMarker) {
    map.removeLayer(droneMarker);
  }
  const marker = L.marker([lat, lng], { icon }).addTo(map);
  marker.bindPopup(`✈ Drone<br>İrtifa: ${altitude.toFixed(1)}m<br>Yön: ${heading.toFixed(0)}°`);
  return marker;
}

// ── Koordinat Dönüşümü (metre → lat/lng) ──────────────────────────────────
function metersToLatLng(x_east, y_north) {
  const lat = HOME_LAT + (y_north / M_PER_LAT);
  const lng = HOME_LNG + (x_east / (M_PER_LAT * Math.cos(HOME_LAT * Math.PI / 180)));
  return [lat, lng];
}

// ── Telemetri Güncelleme ───────────────────────────────────────────────────
function updateTelemetry(data) {
  const s  = data.state;
  const pos = s.position;
  const kin = s.kinematics;
  const st  = s.status;
  const bat = data.battery_alert;

  // ─ Top bar
  document.getElementById('flight-mode').textContent = st.mode;
  document.getElementById('tb-altitude').textContent  = `${pos.altitude.toFixed(1)}m`;
  document.getElementById('tb-speed').textContent     = `${kin.speed.toFixed(1)} m/s`;
  document.getElementById('tb-battery').textContent   = `%${st.battery.toFixed(0)}`;

  // Mode rengi
  const modePill = document.getElementById('flight-mode');
  modePill.className = 'mode-pill';
  if (['TAKEOFF','NAVIGATING','RETURN_TO_HOME'].includes(st.mode)) modePill.classList.add('airborne');
  if (st.mode === 'LANDING') modePill.classList.add('warning');
  if (st.mode === 'EMERGENCY') modePill.classList.add('emergency');

  // ─ Batarya bar
  const batPct = st.battery;
  const batBar = document.getElementById('bat-bar');
  batBar.style.width = `${batPct}%`;
  batBar.className = 'battery-bar-inner';
  if (batPct <= 20) batBar.classList.add('emergency');
  else if (batPct <= 30) batBar.classList.add('critical');
  else if (batPct <= 50) batBar.classList.add('low');

  document.getElementById('bat-value').textContent = `%${batPct.toFixed(1)}`;
  document.getElementById('bat-status').textContent = `${bat.status}`;

  // ─ İrtifa bar (max 120m)
  const altPct = Math.min(100, (pos.altitude / 120) * 100);
  document.getElementById('alt-bar').style.height = `${altPct}%`;
  document.getElementById('alt-value').textContent = `${pos.altitude.toFixed(1)} m`;

  // ─ Konum
  document.getElementById('pos-x').textContent   = `${pos.x >= 0 ? '+' : ''}${pos.x.toFixed(1)}m`;
  document.getElementById('pos-y').textContent   = `${pos.y >= 0 ? '+' : ''}${pos.y.toFixed(1)}m`;
  document.getElementById('pos-hdg').textContent = `${kin.heading.toFixed(0)}°`;
  const home = s.home;
  document.getElementById('pos-home').textContent = `${home.distance_2d.toFixed(1)}m`;

  // ─ Harita güncellemesi
  const [lat, lng] = metersToLatLng(pos.x, pos.y);
  document.getElementById('map-coord').textContent =
    `${lat.toFixed(5)}°N  ${lng.toFixed(5)}°E`;

  droneMarker = createDroneMarker(lat, lng, kin.heading, pos.altitude);
  droneMarker.addTo(map);

  // Haritayı drone konumuna ortala
  map.panTo([lat, lng]);

  // İz güncelleme
  droneTrail.push([lat, lng]);
  if (droneTrail.length > 200) droneTrail.shift();
  trailPolyline.setLatLngs(droneTrail);
}

// ── Komut Gönderme ─────────────────────────────────────────────────────────
async function sendCommand() {
  const input  = document.getElementById('cmd-input');
  const btn    = document.getElementById('btn-send');
  const cmdTxt = input.value.trim();
  if (!cmdTxt) return;

  btn.disabled = true;
  btn.textContent = '⏳ İşleniyor...';

  // Log'a ekle (bekliyor)
  addLogEntry('info', `→ ${cmdTxt}`, '...');

  try {
    const resp = await fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmdTxt }),
    });
    const data = await resp.json();
    handleCommandResponse(cmdTxt, data);
  } catch (err) {
    showToast('❌ Bağlantı hatası: ' + err.message, 'danger');
    addLogEntry('danger', cmdTxt, 'Bağlantı hatası');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Gönder ↵';
    input.value = '';
    input.focus();
  }
}

function handleCommandResponse(cmdTxt, data) {
  const parsed  = data.parsed || {};
  const outcome = data.outcome || (data.success ? 'SUCCESS' : 'FAILED');

  // ─ LLM Analiz kutusu
  const llmBox  = document.getElementById('llm-box');
  llmBox.style.display = 'block';
  document.getElementById('llm-action').textContent =
    `▶ ${(parsed.action || '?').toUpperCase()}  ${JSON.stringify(parsed.parameters || {})}`;
  document.getElementById('llm-conf').textContent =
    `Güven: %${((parsed.confidence || 0) * 100).toFixed(0)} | ${(parsed.processing_time_ms || 0).toFixed(0)}ms`;
  document.getElementById('llm-reasoning').textContent = parsed.reasoning || '';
  document.getElementById('llm-safety').textContent =
    parsed.safety_note ? `⚠ ${parsed.safety_note}` : '';

  // ─ Sonuç kutusu
  const resultBox = document.getElementById('result-box');
  const resultMsg = document.getElementById('result-msg');
  resultBox.style.display = 'block';
  resultBox.className = 'result-box ' + (data.success ? 'success' : (outcome === 'SAFETY_REJECTED' ? 'danger' : 'warn'));
  resultMsg.textContent = data.message || '';

  // ─ Log
  const logClass = data.success ? 'success' : (outcome === 'SAFETY_REJECTED' ? 'danger' : 'warn');
  addLogEntry(logClass, cmdTxt, data.message || outcome);

  // ─ İstatistikler
  stats.total++;
  if (outcome === 'SUCCESS') stats.success++;
  else if (outcome === 'SAFETY_REJECTED') stats.safety_rejected++;
  else if (outcome === 'CLARIFIED') stats.clarified++;
  updateStats();

  // ─ Toast
  const icon = data.success ? '✅' : (outcome === 'SAFETY_REJECTED' ? '🛡️' : '❓');
  showToast(`${icon} ${(data.message || '').substring(0, 80)}`, logClass);
}

function quickCmd(text) {
  document.getElementById('cmd-input').value = text;
  sendCommand();
}

// ── Log & İstatistik ───────────────────────────────────────────────────────
function addLogEntry(type, command, message) {
  const stream = document.getElementById('log-stream');
  const empty  = stream.querySelector('.log-empty');
  if (empty) empty.remove();

  logCount++;
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;

  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  entry.innerHTML = `
    <span class="log-time">${timeStr}</span>
    <span class="log-text"><strong>${escHtml(command)}</strong> — ${escHtml(message.substring(0, 60))}</span>
  `;
  stream.appendChild(entry);
  stream.scrollTop = stream.scrollHeight;
  document.getElementById('log-count').textContent = `${logCount} komut`;
}

function updateStats() {
  document.getElementById('st-total').textContent    = stats.total;
  document.getElementById('st-success').textContent  = stats.success;
  document.getElementById('st-rejected').textContent = stats.safety_rejected;
  document.getElementById('st-clarified').textContent= stats.clarified;
}

// ── Toast Bildirimi ────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.4s';
    setTimeout(() => toast.remove(), 400);
  }, 3500);
}

// ── Rapor Kaydet ──────────────────────────────────────────────────────────
async function saveReport() {
  try {
    const r = await fetch('/api/save_report');
    const d = await r.json();
    showToast('💾 Rapor kaydedildi! HTML + JSON + CSV', 'success');
  } catch (e) {
    showToast('Kaydetme hatası: ' + e.message, 'danger');
  }
}

// ── Yardımcı ──────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Enter tuşu ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initMap();

  document.getElementById('cmd-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendCommand();
  });

  // WebSocket bağlantısı
  const socket = io();

  socket.on('connect', () => {
    showToast('🟢 Sunucuya bağlandı', 'success');
  });

  socket.on('disconnect', () => {
    showToast('🔴 Bağlantı kesildi — yeniden bağlanılıyor...', 'danger');
  });

  socket.on('telemetry_update', (data) => {
    updateTelemetry(data);
  });

  socket.on('auto_rth', (data) => {
    showToast(`🔴 OTOMATİK RTH: ${data.message}`, 'danger');
    addLogEntry('danger', '(Otomatik RTH)', data.message);
  });

  socket.on('command_result', (data) => {
    // Sunucu tarafından tetiklenen komut sonucu
    document.getElementById('mf-status').textContent =
      data.success ? '✅ Komut başarılı' : '❌ Komut başarısız';
  });

  // İlk telemetri yükleme
  fetch('/api/state').then(r => r.json()).then(updateTelemetry);
});
