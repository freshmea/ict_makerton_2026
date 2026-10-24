'use strict';
const $ = id => document.getElementById(id);
const text = (id, value) => { $(id).textContent = value; };
let csrf = '', socket, retryTimer, toastTimer, paused = false, lastState, audioUrl, lastEvent = '', displayedProfile, lastMessageAt = 0;
let eyePresets = [], selectedEye, eyePreviewStarted = 0, eyePreviewFrame = -1, eyeRequestPending = false, eyeNotice = '';
let audioGainDirty = false, audioGainSaving = false;
let ttsPending = false;
let servoOwner = '', servoPending = false, servoEpoch = 0;
let servoHeartbeatOwner = '';
let servoGeneration = 0;
const servoTimers = new Map();
for (let i = 1; i <= 6; i++) {
  const card = document.createElement('div'); card.className = 'servo-channel';
  card.innerHTML = `<div class="servo-channel-heading"><label for="servo-angle-${i}">서보 ${i}<small>CH${i-1}</small></label><output id="servo-value-${i}" for="servo-angle-${i}">90°</output></div><input id="servo-angle-${i}" type="range" min="0" max="180" step="1" value="90" aria-valuetext="90도" aria-describedby="servo-command-${i}"><div class="servo-scale"><span>0°</span><span>90°</span><span>180°</span></div><div class="servo-channel-footer"><span id="servo-command-${i}">아직 적용하지 않았습니다.</span><button class="secondary-button" id="servo-move-${i}" aria-label="서보 ${i} 각도 적용" type="button" disabled>이동</button></div>`;
  $('servo-sliders').append(card);
  $(`servo-angle-${i}`).addEventListener('input', event => {
    text(`servo-value-${i}`, `${event.target.value}°`);
    event.target.setAttribute('aria-valuetext', `${event.target.value}도`);
  });
  $(`servo-angle-${i}`).addEventListener('change', () => {
    clearTimeout(servoTimers.get(i)); const token = servoEpoch;
    servoTimers.set(i, setTimeout(() => { if (token === servoEpoch && servoOwner && !servoPending) sendServo(i); }, 200));
  });
  $(`servo-move-${i}`).onclick = () => { clearTimeout(servoTimers.get(i)); sendServo(i); };
}
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
  releaseServosOnLeave();
  $('connection').className = 'connection'; $('connection').replaceChildren(document.createTextNode('● 연결 끊김 · 재시도 중'));
  lastState = null; previews();
  badge('pico-badge', false, '수신 중단'); badge('audio-badge', false, '수신 중단'); badge('system-badge', false, '수신 중단');
  renderAudio({connected: false});
  text('pico-summary', '연결 확인 필요'); text('camera-count', '—');
  document.querySelectorAll('.module-test').forEach(b => b.disabled = true);
  expressionControls(null);
  renderServos(null);
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
  document.querySelectorAll('.module-test').forEach(b => { const absent = b.dataset.module === 'matrix' && installed.matrix_connected === false; b.disabled = absent || !p.connected || stopHeld || eyeRequestPending || s.eye_expression?.active || s.eye_expression?.stopping || (running !== 'None' && running !== 'Idle' && running !== null); b.title = absent ? '도트매트릭스 미연결' : stopHeld ? `SW${switchIndex} 입력을 먼저 해제하세요.` : ''; });
  expressionControls(s);
  renderServos(s.servo_control);
  const cams = c.cameras || []; text('camera-count', cams.filter(x => x.ready).length);
  if (c.profile !== displayedProfile) {
    document.querySelectorAll('[name="profile"]').forEach(input => input.checked = input.value === c.profile);
    displayedProfile = c.profile;
  }
  text('camera-detail', c.error || `${c.profile} · ${c.encoder || 'H.264'} / NVMM`);
  cams.forEach(cam => { const i = cam.sensor_id; text(`fps-${i}`, cam.ready ? cam.fps.toFixed(1) : '—');
    text(`camera-specs-${i}`, `${c.settings.width}×${c.settings.height} · H.264 ${cam.encoded_fps} fps / ${cam.encoded_mbps} Mbps · Preview ${cam.preview_delivery_fps ?? cam.preview_fps} fps`); });
  previews();
  renderAudio(a);
  const speaker = a.speaker; text('speaker-state', speaker.state === 'synthesizing' ? 'TTS 음성 합성 중' : speaker.state === 'playing' ? '스피커 재생 중' : speaker.last_result ? `스피커 PCM ${speaker.last_result.ok ? '재생 성공' : '재생 실패'}` : '스피커 대기 · 시험 버튼으로 확인');
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
function gainLabel() {
  const label = `+${Number($('audio-gain').value)} dB`;
  text('audio-gain-value', label); $('audio-gain').setAttribute('aria-valuetext', label);
}
function renderServos(state) {
  if (servoOwner && state && state.generation < servoGeneration) return;
  const update = (id, value) => { if ($(id).textContent !== value) text(id, value); };
  const mine = Boolean(servoOwner && state?.active), ready = Boolean(state?.ready);
  if (servoOwner && state && !state.active && !servoPending) { servoOwner = ''; servoEpoch++; }
  $('servo-enable').disabled = !csrf || !ready || Boolean(state?.active) || servoPending;
  $('servo-probe').disabled = !csrf || !state?.supported || !lastState?.pico?.connected || servoPending;
  $('servo-control-badge').className = `badge ${mine ? 'online' : 'neutral'}`;
  update('servo-control-badge', mine ? '제어 중' : ready ? '준비됨' : '연결 확인 필요');
  const notice = !state ? '장치 상태 수신이 중단됐습니다.' : state.reason || state.error ||
    (servoPending || state.busy ? '명령 처리 중입니다. 완료 후 다음 각도를 적용하세요.' : mine ? '제어 중 · 손을 놓거나 이동을 누르면 선택한 서보만 움직입니다.' : state.active ? '다른 창에서 제어 중입니다.' : '각도를 선택하고 서보 제어 시작을 눌러 주세요.');
  update('servo-control-state', notice);
  $('servo-control-state').classList.toggle('error', Boolean(state?.reason || state?.error));
  for (let i=1; i<=6; i++) {
    $(`servo-move-${i}`).disabled = !mine || !ready || servoPending || Boolean(state?.busy);
    const angle = state?.commanded_degrees?.[i-1];
    if (angle !== null && angle !== undefined) update(`servo-command-${i}`, `마지막 완료 명령 ${angle}°`);
  }
}
async function sendServo(i) {
  if (!servoOwner || servoPending || $(`servo-move-${i}`).disabled) return;
  const token = servoEpoch, owner = servoOwner; servoPending = true; renderServos(lastState?.servo_control);
  try {
    const result = await post('/api/pico/servo', {control_id: owner, servo:i, degrees:Number($(`servo-angle-${i}`).value)});
    if (token === servoEpoch) { lastState.servo_control = result.state; text(`servo-command-${i}`, `마지막 완료 명령 ${result.degrees}°`); }
  } catch (error) { if (token === servoEpoch) toast(error.message); }
  finally { if (token === servoEpoch) { servoPending = false; renderServos(lastState?.servo_control); } }
}
$('servo-enable').onclick = async () => {
  const token = ++servoEpoch; servoPending = true; renderServos(lastState?.servo_control);
  try {
    const result = await post('/api/pico/servos/session', {action:'enable'});
    if (token === servoEpoch) { servoOwner = result.control_id; servoGeneration = result.state.generation; lastState.servo_control = result.state; }
    else await post('/api/pico/servos/session', {action:'stop',control_id:result.control_id});
  } catch (error) { if (token === servoEpoch) toast(error.message); }
  finally { if (token === servoEpoch) { servoPending = false; renderServos(lastState?.servo_control); } }
};
function forgetServoOwner() { servoEpoch++; servoOwner = ''; servoPending = false; for (const timer of servoTimers.values()) clearTimeout(timer); }
$('servo-stop').onclick = async () => { forgetServoOwner(); renderServos(lastState?.servo_control); try { await post('/api/pico/servos/session',{action:'stop'}); } catch(error) { toast(error.message); } };
$('servo-probe').onclick = async () => { forgetServoOwner(); servoPending = true; renderServos(lastState?.servo_control); try { await post('/api/pico/servos/session',{action:'probe'}); toast('PCA9685 응답을 확인했습니다. 모터는 움직이지 않았습니다.'); } catch(error) { toast(error.message); } finally { servoPending=false; renderServos(lastState?.servo_control); } };
setInterval(async () => {
  const owner=servoOwner;
  if (!owner || document.hidden || servoHeartbeatOwner === owner) return;
  servoHeartbeatOwner = owner;
  try { await post('/api/pico/servos/session',{action:'keepalive',control_id:owner}); }
  catch(error) { if(servoOwner===owner){forgetServoOwner();renderServos(lastState?.servo_control);toast(error.message);} }
  finally { if(servoHeartbeatOwner === owner) servoHeartbeatOwner = ''; }
}, 500);
function releaseServosOnLeave() {
  const owner = servoOwner; if (!owner) return;
  forgetServoOwner();
  fetch('/api/pico/servos/session', {method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({action:'stop',control_id:owner})}).catch(()=>{});
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseServosOnLeave();});
window.addEventListener('pagehide',releaseServosOnLeave);
function renderAudio(a) {
  const db = value => a.connected && Number.isFinite(value) ? value.toFixed(1) : '—';
  text('mic-db', db(a.peak_dbfs));
  text('mic-detail', a.error || (a.connected ? `최근 ${a.meter_seconds}초 피크 · 평균 ${db(a.rms_dbfs)} dBFS` : '마이크 연결 대기'));
  badge('audio-badge', a.connected, a.connected ? 'CAPTURING' : 'OFFLINE');
  text('audio-level', `평균 ${db(a.rms_dbfs)} dBFS`);
  text('audio-peak', `${db(a.peak_dbfs)} Peak dBFS`);
  text('audio-raw', `원본 평균 ${db(a.raw_rms_dbfs)} · 피크 ${db(a.raw_peak_dbfs)} dBFS`);
  text('audio-gain-state', a.connected ? `설정 +${a.gain_db} dB · 실제 ${a.applied_gain_db > 0 ? '+' : ''}${a.applied_gain_db} dB${a.limiter_active ? ' · 피크 보호 중' : ''}` : '증폭 상태 대기');
  chart('waveform', a.connected ? a.waveform : [], 1, '#295b46');
  if (!audioGainDirty && Number.isFinite(a.gain_db)) { $('audio-gain').value = a.gain_db; gainLabel(); }
  $('audio-gain').disabled = $('audio-gain-apply').disabled = !a.connected || audioGainSaving;
  renderTTS();
}
function renderTTS() {
  const input = $('tts-text'), count = input.value.length;
  const busy = ttsPending || ['synthesizing', 'playing'].includes(lastState?.audio?.speaker?.state);
  text('tts-count', `${count} / 240자`);
  $('tts-play').disabled = !csrf || busy || !input.value.trim() || count > 240;
  $('tts-form').setAttribute('aria-busy', String(ttsPending));
  document.querySelectorAll('[data-audio]').forEach(button => { button.disabled = busy; });
}
$('tts-text').addEventListener('input', () => { $('tts-text').removeAttribute('aria-invalid'); renderTTS(); });
$('tts-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (ttsPending || $('tts-play').disabled) return;
  const value = $('tts-text').value.trim();
  if (!value) { $('tts-text').setAttribute('aria-invalid', 'true'); return; }
  ttsPending = true; renderTTS();
  text('tts-play', '음성 준비 중…'); text('tts-status', '음성을 합성하고 BA-R9에서 재생합니다. 잠시 기다려 주세요.');
  $('tts-status').classList.remove('error');
  try {
    const result = await post('/api/audio/tts', {text: value});
    if (lastState) lastState.audio.speaker = result.speaker;
    text('tts-status', `재생 완료 · Typecast 서연 · ${result.tts.requested_characters}자`);
    toast('입력한 문장을 BA-R9에서 재생했습니다.');
  } catch (error) {
    text('tts-status', error.message); $('tts-status').classList.add('error');
  } finally { ttsPending = false; text('tts-play', '▶ TTS 재생'); renderTTS(); }
});
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
$('audio-gain').addEventListener('input', () => { audioGainDirty = true; gainLabel(); });
$('audio-gain-form').addEventListener('submit', async event => {
  event.preventDefault(); if (audioGainSaving) return;
  audioGainSaving = true; $('audio-gain').disabled = $('audio-gain-apply').disabled = true;
  try {
    const audio = await post('/api/audio/settings', {gain_db: Number($('audio-gain').value)});
    audioGainDirty = false;
    if (lastState) { lastState.audio = audio; renderAudio(audio); }
    // Previously fetched audio contains the old gain. Fetch it again on Listen.
    $('recording').pause(); $('recording').removeAttribute('src'); $('recording').load(); $('recording').classList.remove('visible');
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = null; }
    toast(`녹음 증폭 +${audio.gain_db} dB를 저장했습니다.`);
  } catch (error) { toast(error.message); }
  finally { audioGainSaving = false; renderAudio(lastState?.audio || {connected: false}); }
});
document.querySelectorAll('.rtsp-copy').forEach(button => button.onclick = async () => { const input = $(`rtsp-${button.dataset.sensor}`); if (navigator.clipboard?.writeText) { try { await navigator.clipboard.writeText(input.value); toast('RTSP 주소를 복사했습니다. VLC 등에서 여세요.'); return; } catch {} } input.focus(); input.select(); toast('주소를 선택했습니다. Ctrl+C로 복사하세요.'); });

function drawEye(id, rows) {
  const canvas = $(id), ctx = canvas.getContext('2d'), step = canvas.width / 8;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) {
    const on = Boolean(rows[y] & (128 >> x));
    ctx.beginPath(); ctx.arc((x + .5) * step, (y + .5) * step, step * .32, 0, Math.PI * 2);
    ctx.fillStyle = on ? '#d1e6a3' : '#283c2e'; ctx.fill();
  }
}
function previewEyes() {
  if (!selectedEye || document.hidden) return;
  const frames = selectedEye.frames, reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const live = lastState?.eye_expression, playingSelected = lastState?.pico?.connected && live?.active && live.preset_id === selectedEye.id;
  let index = playingSelected ? Math.min(live.frame_index, frames.length - 1) : 0;
  if (!playingSelected && !reduced) {
    let ms = (performance.now() - eyePreviewStarted) % frames.reduce((sum, frame) => sum + frame.ms, 0);
    index = frames.findIndex(frame => { if (ms < frame.ms) return true; ms -= frame.ms; return false; });
  }
  if (index === eyePreviewFrame) return;
  eyePreviewFrame = index;
  const frame = frames[Math.max(0, index)]; drawEye('expression-left', frame.left); drawEye('expression-right', frame.right);
}
function chooseEye(id) {
  selectedEye = eyePresets.find(item => item.id === id); if (!selectedEye) return;
  $('expression-select').value = id; eyePreviewStarted = performance.now(); eyePreviewFrame = -1; eyeNotice = '';
  text('expression-name', selectedEye.name); text('expression-group', selectedEye.group);
  text('expression-description', selectedEye.description);
  $('expression-preview').setAttribute('aria-label', `${selectedEye.name} · ${selectedEye.description}`);
  previewEyes(); expressionControls(lastState);
}
function expressionControls(s) {
  const p = s?.pico, state = s?.eye_expression, d = p?.device || {}, running = d.running;
  const online = Boolean(p?.connected), absent = p?.installation?.matrix_connected === false;
  const busy = Boolean(running && running !== 'None' && running !== 'Idle');
  const testSwitch = Number(d.config?.test_switch || 0), held = testSwitch > 0 && Boolean((d.pressed_mask || 0) & (1 << (testSwitch - 1)));
  $('expression-play').disabled = !selectedEye || !online || absent || busy || held || eyeRequestPending || Boolean(state?.stopping);
  $('expression-stop').disabled = !online || (!state?.active && !eyeRequestPending) || Boolean(state?.stopping);
  const error = eyeNotice || state?.error;
  $('expression-state').classList.toggle('is-error', Boolean(error));
  let message = error || (!online ? '미리보기 가능 · Pico 연결을 기다리는 중' : absent ? '도트매트릭스 연결 설정을 확인해 주세요.' : state?.stopping ? '표정을 끄고 있습니다.' : state?.active ? `${state.name} 표시 중 · ${Math.ceil(state.remaining_ms / 1000)}초 뒤 자동 소등` : busy ? '다른 장치 시험이 끝나면 표정을 표시할 수 있어요.' : state?.last?.result === 'completed' ? `${state.last.name} · 표시 완료, 소등됨` : state?.last?.result === 'stopped' ? '표정을 껐습니다. 새 시험을 선택해 주세요.' : '선택하면 미리보기 · 시험을 누르면 양쪽 눈에 표시');
  text('expression-state', message);
  if (online && state?.active) text('matrix-status', `${state.name} · 표정 표시 중`);
  previewEyes();
}
async function loadEyes() {
  try {
    const response = await fetch('/api/pico/expressions'); if (!response.ok) throw new Error('표정 목록을 불러오지 못했습니다.');
    const result = await response.json(); eyePresets = result.presets;
    $('expression-select').replaceChildren(); let group, groupName;
    eyePresets.forEach((item, index) => {
      if (groupName !== item.group) { groupName = item.group; group = document.createElement('optgroup'); group.label = item.group; $('expression-select').append(group); }
      const option = document.createElement('option'); option.value = item.id; option.textContent = `${String(index + 1).padStart(2, '0')} · ${item.name}`; group.append(option);
    });
    text('expression-count', `${eyePresets.length} PRESETS`);
    for (const id of ['expression-select', 'expression-prev', 'expression-next']) $(id).disabled = false;
    chooseEye(eyePresets[0].id);
  } catch (error) { eyeNotice = error.message; expressionControls(lastState); }
}
$('expression-select').onchange = event => chooseEye(event.target.value);
for (const [id, delta] of [['expression-prev', -1], ['expression-next', 1]]) $(id).onclick = () => { if (selectedEye) chooseEye(eyePresets[(eyePresets.indexOf(selectedEye) + delta + eyePresets.length) % eyePresets.length].id); };
$('expression-form').onsubmit = async event => {
  event.preventDefault(); if (!selectedEye || $('expression-play').disabled) return;
  const chosen = selectedEye;
  eyeRequestPending = true; eyeNotice = ''; expressionControls(lastState);
  try { await post('/api/pico/expression', {preset_id: chosen.id, seconds: Number($('expression-seconds').value)}); toast(`${chosen.name} 표정 시험을 시작했습니다.`); }
  catch (error) { eyeNotice = error.message; }
  finally { eyeRequestPending = false; expressionControls(lastState); }
};
$('expression-stop').onclick = async () => {
  eyeRequestPending = true; eyeNotice = ''; expressionControls(lastState);
  try { await post('/api/pico/command', {cmd: 'stop'}); }
  catch (error) { eyeNotice = error.message; }
  finally { eyeRequestPending = false; expressionControls(lastState); }
};
setInterval(previewEyes, 100);
loadEyes();
connect();
