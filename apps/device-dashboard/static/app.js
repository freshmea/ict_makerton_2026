'use strict';
const $ = id => document.getElementById(id);
const text = (id, value) => { $(id).textContent = value; };
let csrf = '', socket, retryTimer, toastTimer, paused = false, lastState, audioUrl, lastEvent = '', displayedProfile, lastMessageAt = 0;
const pins = [9, 10, 11, 12, 14, 15];
for (let i = 0; i < 6; i++) {
  const cell = document.createElement('div'); cell.className = 'touch-cell'; cell.id = `touch-${i}`;
  cell.innerHTML = `<span>SW ${i + 1}<small>GP${i + 6} / PIN ${pins[i]}</small></span><strong>—</strong><small class="touch-details">입력 대기</small>`;
  $('touch-grid').append(cell);
}
text('host', location.hostname);
function toast(message) { text('toast', message); $('toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.remove('visible'), 5000); }
async function post(path, body) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify(body)});
  const value = await response.json().catch(() => ({detail: `HTTP ${response.status}`}));
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
  return value;
}
async function action(button, path, body, message) {
  button.disabled = true;
  try { await post(path, body); toast(message); } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
}
function badge(id, ok, label) { $(id).className = `badge ${ok ? 'online' : 'neutral'}`; text(id, label); }
function chart(id, values, max, color) {
  const canvas = $(id), ctx = canvas.getContext('2d'), w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h); ctx.strokeStyle = '#dce2d8'; ctx.lineWidth = 1;
  for (let y = h / 4; y < h; y += h / 4) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  if (!values.length) return;
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
  values.forEach((v, i) => { const x = i * w / Math.max(1, values.length - 1), y = h / 2 - v / max * h * .44; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
}
function previews() {
  for (let i = 0; i < 2; i++) {
    const image = $(`camera-image-${i}`), ready = lastState?.cameras?.ready;
    if (!document.hidden && !paused && ready) {
      if (!image.hasAttribute('src')) image.src = `/api/cameras/${i}/stream.mjpg`;
    } else image.removeAttribute('src');
    text(`video-state-${i}`, document.hidden || paused ? '미리보기 정지' : ready ? 'LIVE / MJPEG' : '연결 대기');
  }
}
function disconnected() {
  $('connection').className = 'connection'; $('connection').replaceChildren(document.createTextNode('● 연결 끊김 · 재시도 중'));
  lastState = null; previews();
  badge('pico-badge', false, '수신 중단'); badge('audio-badge', false, '수신 중단'); badge('system-badge', false, '수신 중단');
  text('pico-summary', '연결 확인 필요'); text('camera-count', '—');
  document.querySelectorAll('.module-test').forEach(b => b.disabled = true);
}
function render(s) {
  lastMessageAt = Date.now();
  lastState = s; const p = s.pico, d = p.device || {}, a = s.audio, c = s.cameras, m = s.system;
  const installed = p.installation || {}, touchInstalled = installed.touch_inputs_connected !== false;
  $('connection').className = 'connection online'; text('connection', '● 실시간 연결');
  text('clock', new Date(s.server_time * 1000).toLocaleTimeString('ko-KR', {hour12: false}) + ' · 2 Hz 갱신');
  $('pico-dot').className = `tiny-dot ${p.connected ? 'online' : ''}`;
  text('pico-summary', p.connected ? 'USB 연결됨' : '연결 확인 필요');
  text('pico-detail', p.error || (p.connected ? `세션 ${p.session} · faults ${d.faults ?? '—'}` : '/dev/pico-device 대기'));
  badge('pico-badge', p.connected, p.connected ? 'LIVE' : 'OFFLINE');
  text('pico-age', `마지막 상태 ${p.age_ms ?? '—'} ms 전`);
  text('touch-mask', touchInstalled ? `RAW ${d.raw_mask ?? '—'} / PRESSED ${d.pressed_mask ?? '—'}` : '스위치 미연결');
  const touches = d.touches || d.switches || [];
  for (let i = 0; i < 6; i++) {
    const cell = $(`touch-${i}`), t = touches[i] || {}, pressed = touchInstalled && p.connected && Boolean((d.pressed_mask || 0) & (1 << i));
    cell.classList.toggle('pressed', pressed); cell.querySelector('strong').textContent = !touchInstalled ? '미연결' : !p.connected ? '—' : pressed ? 'PRESSED' : 'RELEASED';
    cell.querySelector('.touch-details').textContent = !touchInstalled ? '입력 해석 안 함' : p.connected ? `${t.held_ms ?? (d.touch_held_ms || [])[i] ?? 0} ms · ${t.press_count ?? (d.touch_press_counts || [])[i] ?? 0}회` : '입력 대기';
  }
  const config = d.config || {};
  text('local-tests', touchInstalled ? `로컬 검사 ${d.local_enabled ? '활성' : '비활성'} · 길게 누르기 ${config.hold_interval_ms ?? '—'} ms` : '스위치 미연결 · 로컬 검사 비활성');
  const running = d.running || 'None', faults = d.faults || 0;
  const switchIndex = Number(config.test_switch || 0), stopHeld = touchInstalled && switchIndex > 0 && Boolean((d.pressed_mask || 0) & (1 << (switchIndex - 1)));
  text('device-running', `실행: ${running} · faults: ${faults} · 이벤트 누락: ${d.dropped_events ?? '—'}${stopHeld ? ` · 원격 시험 전 SW${switchIndex} 입력 해제 필요` : ''}`);
  text('matrix-status', installed.matrix_connected === false ? '미연결 · 시험 비활성' : p.connected ? 'SPI 출력 · 실제 발광 피드백 없음' : '연결 대기');
  for (const side of ['left', 'right']) {
    const segments = config[`${side}_segments`] || [];
    text(`${side}-segments`, segments.length ? `${segments.join(' + ')} = ${segments.reduce((x, y) => x + y, 0)} pixels` : '설정 데이터 대기');
    text(`${side}-status`, p.connected ? 'PIO 출력 · 실제 발광 피드백 없음' : '연결 대기');
  }
  text('servo-status', p.connected ? `OE ${d.oe_high ? 'HIGH · 출력 차단' : 'LOW · 출력 허용'} · 외부 전원 별도${faults ? ' · fault 확인' : ''}` : '연결 대기');
  for (const [module, id] of [['NeoLeft','left-status'], ['NeoRight','right-status'], ['Servos','servo-status']]) {
    const event = p.module_tests?.[module];
    if (p.connected && event) text(id, event.fault ? '시험 중단/거부 · 이벤트 확인' : event.done ? (module === 'Servos' ? '명령 시험 완료 · 외부 전원 별도 필요' : '명령 시험 완료 · 발광 피드백 없음') : `시험 진행 · 단계 ${event.phase}`);
  }
  document.querySelectorAll('.module-test').forEach(b => { const absent = b.dataset.module === 'matrix' && installed.matrix_connected === false; b.disabled = absent || !p.connected || stopHeld || (running !== 'None' && running !== 'Idle' && running !== null); b.title = absent ? '도트매트릭스 미연결' : stopHeld ? `SW${switchIndex} 입력을 먼저 해제하세요.` : ''; });
  const cams = c.cameras || []; text('camera-count', cams.filter(x => x.ready).length);
  if (c.profile !== displayedProfile) {
    document.querySelectorAll('[name="profile"]').forEach(input => input.checked = input.value === c.profile);
    displayedProfile = c.profile;
  }
  text('camera-detail', c.error || `${c.profile} · ${c.encoder || 'H.264'} / NVMM`);
  cams.forEach(cam => { const i = cam.sensor_id; text(`fps-${i}`, cam.ready ? cam.fps.toFixed(1) : '—');
    text(`camera-specs-${i}`, `${c.settings.width}×${c.settings.height} · H.264 ${cam.encoded_fps} fps / ${cam.encoded_mbps} Mbps · Preview ${cam.preview_delivery_fps ?? cam.preview_fps} fps`); });
  previews();
  text('mic-db', a.connected ? a.rms_dbfs.toFixed(1) : '—'); text('mic-detail', a.error || `48 kHz · Mono · ${a.buffered_seconds}초 버퍼`);
  badge('audio-badge', a.connected, a.connected ? 'CAPTURING' : 'OFFLINE');
  text('audio-level', `${a.connected ? a.rms_dbfs : '—'} dBFS`); text('audio-peak', `${a.peak_dbfs} Peak dBFS`);
  chart('waveform', a.connected ? a.waveform : [], 1, '#295b46');
  const speaker = a.speaker; text('speaker-state', speaker.state === 'playing' ? '스피커 재생 중' : speaker.last_result ? `스피커 PCM ${speaker.last_result.ok ? '재생 성공' : '재생 실패'}` : '스피커 대기 · 시험 버튼으로 확인');
  text('cpu', m.cpu_percent ?? '—'); text('cpu-large', `${m.cpu_percent ?? '—'}%`);
  text('board-detail', `RAM ${m.memory_percent ?? '—'}% · ${m.temperature_c ?? '—'}°C`);
  text('memory', `${m.memory_used_mib ?? '—'} / ${m.memory_total_mib ?? '—'} MiB`); $('memory-bar').style.width = `${m.memory_percent || 0}%`;
  text('gpu', `${m.gpu_percent ?? '—'}%`); text('temperature', `${m.temperature_c ?? '—'} °C`);
  text('uptime', `${Math.floor((m.uptime_seconds || 0) / 3600)}h ${Math.floor((m.uptime_seconds || 0) % 3600 / 60)}m`);
  chart('cpu-chart', (m.cpu_history || []).map(v => v - 50), 55, '#295b46'); badge('system-badge', true, 'TELEMETRY');
  if (s.events?.[0]?.id !== lastEvent) {
    lastEvent = s.events?.[0]?.id; $('event-list').replaceChildren();
    s.events.slice(0, 12).forEach(e => { const row = document.createElement('div'); row.className = `event-row ${e.level}`;
      for (const value of [new Date(e.time * 1000).toLocaleTimeString('ko-KR', {hour12:false}), e.source.toUpperCase(), e.message]) { const span = document.createElement('span'); span.textContent = value; span.className = row.children.length === 2 ? 'event-message' : row.children.length === 1 ? 'event-source' : 'event-time'; row.append(span); } $('event-list').append(row); });
  }
}
async function connect() {
  if (document.hidden) return;
  try {
    const response = await fetch('/api/session'); if (!response.ok) throw new Error('세션 실패');
    const session = await response.json(); csrf = session.csrf_token;
    for (let i = 0; i < 2; i++) $(`rtsp-${i}`).value = `rtsp://${location.hostname}:${session.rtsp_port}/cam${i}`;
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/status`);
    socket.onmessage = event => render(JSON.parse(event.data));
    socket.onclose = () => { disconnected(); if (!document.hidden) retryTimer = setTimeout(connect, 3000); };
    socket.onerror = () => socket.close();
  } catch { disconnected(); retryTimer = setTimeout(connect, 3000); }
}
document.addEventListener('visibilitychange', () => { clearTimeout(retryTimer); if (document.hidden) { if (socket) { socket.onclose = null; socket.close(); } previews(); } else connect(); });
setInterval(() => { if (!document.hidden && socket?.readyState === WebSocket.OPEN && lastMessageAt && Date.now() - lastMessageAt > 3500) { disconnected(); socket.close(); } }, 1000);
$('pause-preview').onclick = () => { paused = !paused; $('pause-preview').setAttribute('aria-pressed', String(paused)); text('pause-preview', paused ? '▷ 미리보기 재개' : 'Ⅱ 미리보기 일시정지'); previews(); };
$('profile-form').onsubmit = async event => { event.preventDefault(); const button = event.submitter || $('profile-form').querySelector('button'); await action(button, '/api/cameras/profile', {profile: new FormData(event.target).get('profile')}, '두 카메라의 촬영 프로필을 적용했습니다.'); };
$('stop-all').onclick = () => action($('stop-all'), '/api/pico/command', {cmd:'stop'}, 'Stop ACK 수신. OE와 실행 상태를 확인하세요.');
$('pico-reconnect').onclick = () => action($('pico-reconnect'), '/api/pico/reconnect', {}, 'USB 브리지 연결을 요청했습니다.');
document.querySelectorAll('.module-test').forEach(button => button.onclick = () => action(button, '/api/pico/command', {cmd:'test', module:button.dataset.module}, '시험 요청 ACK 수신. 완료 여부는 장치 이벤트에서 확인하세요.'));
document.querySelectorAll('[data-audio]').forEach(button => button.onclick = () => action(button, '/api/audio/play', {action:button.dataset.audio}, '보드 스피커 PCM 재생을 마쳤습니다.'));
$('listen-mic').onclick = async () => { try { const response = await fetch('/api/audio/recent.wav'); if (!response.ok) throw new Error('마이크 버퍼를 읽지 못했습니다.'); if (audioUrl) URL.revokeObjectURL(audioUrl); audioUrl = URL.createObjectURL(await response.blob()); $('recording').classList.add('visible'); $('recording').src = audioUrl; await $('recording').play(); } catch (error) { toast(error.message); } };
document.querySelectorAll('.rtsp-copy').forEach(button => button.onclick = async () => { const input = $(`rtsp-${button.dataset.sensor}`); if (navigator.clipboard?.writeText) { try { await navigator.clipboard.writeText(input.value); toast('RTSP 주소를 복사했습니다. VLC 등에서 여세요.'); return; } catch {} } input.focus(); input.select(); toast('주소를 선택했습니다. Ctrl+C로 복사하세요.'); });
connect();
