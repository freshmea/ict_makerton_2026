(() => {
  'use strict';
  const el = id => document.getElementById(id);
  let current, pending = false, timer, polling = false, notice = '';
  const busyPhases = new Set(['capturing', 'analyzing', 'cancelling']);
  const labels = {observed: '관찰됨', not_observed: '미관찰', unknown: '판단 불가'};
  const setText = (id, value) => { el(id).textContent = value; };
  const money = value => '$' + Number(value || 0).toFixed(7);

  function showCameraRoles() {
    const face = Number(el('study-jev-cameras').value);
    setText('study-camera-roles', `Decisions / JEV: 얼굴 = 카메라 ${face + 1} · 학습 공간 = 카메라 ${2 - face}. 각 10장, 총 20장을 한 번 전송합니다. 2번 스위치는 얼굴 CAM 1 / 학습 공간 CAM 2를 사용합니다.`);
  }

  function render(state) {
    current = state;
    const job = state.job || {}, providers = state.providers || {}, result = job.result;
    const reaction = state.reaction || {}, active = busyPhases.has(job.phase) || reaction.busy, online = state.online === true;
    if (active) notice = '';
    const ready = typeof lastState !== 'undefined' && Boolean(lastState?.cameras?.ready);
    for (const provider of ['openai', 'jev', 'decisions']) {
      el(`study-${provider}`).disabled = pending || active || !online || !ready || !providers[provider]?.available;
    }
    el('study-camera').disabled = pending || active;
    el('study-jev-cameras').disabled = pending || active;
    if (active && ['jev','decisions'].includes(job.provider) && (job.camera === 0 || job.camera === 1)) {
      el('study-jev-cameras').value = String(job.camera);
      showCameraRoles();
    }
    el('study-cancel').disabled = pending || !(job.phase === 'capturing' || reaction.busy);
    const count = job.captured || 0;
    const total = job.total || 20;
    setText('study-progress-label', `사진 수집 · ${count} / ${total}장`);
    el('study-progress').max = total;
    if (job.phase === 'analyzing') el('study-progress').removeAttribute('value');
    else el('study-progress').value = count;
    const phaseText = {
      idle: '카메라 배치를 확인하고 분석을 시작해 주세요.',
      capturing: ['jev','decisions'].includes(job.provider) ? '1초마다 얼굴·학습 공간을 한 쌍씩 모으고 있습니다.' : '1초마다 최신 사진을 모으고 있습니다.',
      analyzing: `사진 ${total}장을 한 번에 분석하고 있습니다.`,
      cancelling: '사진 수집을 취소하고 있습니다.',
      cancelled: '수집을 취소했습니다. API로 전송하지 않았습니다.',
      completed: result?.status === 'ok' ? '분석을 완료했습니다.' : '분석을 완료했습니다. 관찰이 어려운 항목은 보류했습니다.',
      failed: job.error || '분석을 완료하지 못했습니다.',
      offline: state.error || '분석 서비스에 연결하지 못했습니다.'
    };
    setText('study-state', pending ? '요청을 전달하고 있습니다.' : notice || phaseText[job.phase] || '분석 서비스를 확인하고 있습니다.');
    const plan = reaction.job_id === job.id ? reaction.reaction : null;
    const speech = {pending:'준비 중',played:'재생 완료',failed:'재생 실패',speaker_busy:'다른 음성 재생 중'};
    const reactionPhase = {completed:'기기 반응 완료',cancelled:'기기 반응 취소',failed:'기기 반응 중단'};
    setText('study-reaction-state', reaction.error ? reaction.error : plan ?
      `${reaction.busy ? '기기 반응 중' : reactionPhase[reaction.phase] || '기기 반응 대기'} · NeoPixel ${plan.led === 'applied' ? '색 적용' : '준비'} · 음성 ${speech[plan.speech] || '준비'} · 서보 ${plan.servos.length}/4개 왕복${plan.errors.length ? ' · ' + plan.errors.join(' · ') : ''} · 안내: “${plan.text}”` :
      '2번: “이번” 안내 후 비프음 4회까지 길게 누르면 분석합니다. 다시 길게 누르면 취소합니다. 결과에 따라 빛·음성·서보 1~4번이 반응합니다.');
    el('study-state').classList.toggle('is-error', Boolean(notice) || !online || job.phase === 'failed');
    setText('study-focus', typeof result?.focus_score === 'number' ? result.focus_score.toFixed(1) : '—');
    setText('study-gaze', typeof result?.study_gaze_score === 'number' ? result.study_gaze_score.toFixed(1) : '—');
    setText('study-presence', result?.is_away === false ? '재석' : result?.is_away === true ? '자리비움' : result ? '판단 보류' : '분석 전');
    const face = result?.cameras?.find(camera => camera.role === 'face');
    const desk = result?.cameras?.find(camera => camera.role === 'study_area');
    const resultRoles = face && desk ? ` · 얼굴 CAM ${face.sensor_id + 1} / 학습 공간 CAM ${desk.sensor_id + 1}` : '';
    setText('study-result-meta', result ? `${result.frame_count}장 · ${result.provider.toUpperCase()}${resultRoles} · ${(result.wall_ms / 1000).toFixed(2)}초 응답` : '판단 불가 시 자리비움 처리');
    const reasons = new Set(result?.reasons || []);
    const setup = '얼굴용 카메라는 눈·머리 방향을, 학습 공간용 카메라는 손·책상 위 학습 자료를 담도록 맞춰 주세요.';
    setText('study-evidence', result?.presence_basis === 'user_policy_unknown_as_away' ? '관찰 근거 부족 · 사용자 설정에 따라 자리비움으로 처리했습니다. 집중·시선 점수는 보류합니다.' : reasons.has('seat_not_observable') || reasons.has('presence_uncertain') ? `책상·학습자 영역을 확인하기 어려워 판단을 보류했습니다. ${setup}` : result?.is_away === true ? '관찰 가능한 책상 영역에 학습자가 없어 점수는 표시하지 않습니다.' : result && (result.focus_score === null || result.study_gaze_score === null) ? `학습 행동 또는 책상 방향의 근거가 부족한 점수는 표시하지 않습니다. ${setup}` : result ? `${result.frame_count}장에 보이는 행동을 바탕으로 한 추정입니다. 미관찰은 해당 행동이 없었다는 확정이 아닙니다.` : setup);
    const catalogue = state.categories || [];
    if (catalogue.length && el('study-behaviors').dataset.catalogue !== catalogue.map(c => c.id).join(',')) {
      el('study-behaviors').replaceChildren();
      for (const item of catalogue) {
        const row = document.createElement('li'); row.dataset.behavior = item.id;
        const name = document.createElement('span'); name.textContent = item.label;
        const value = document.createElement('span'); value.className = 'study-behavior-state'; value.textContent = '대기';
        row.append(name, value); el('study-behaviors').append(row);
      }
      el('study-behaviors').dataset.catalogue = catalogue.map(c => c.id).join(',');
    }
    const observed = new Map((result?.behaviors || []).map(item => [item.id, item]));
    for (const row of el('study-behaviors').children) {
      const badge = row.querySelector('.study-behavior-state'); if (!badge) continue;
      const item = observed.get(row.dataset.behavior);
      badge.textContent = item ? labels[item.state] || '판단 불가' : '대기';
      badge.dataset.state = item?.state || '';
    }
    const budget = providers.decisions?.budget;
    setText('study-budget', budget && !budget.error ? `Decisions 오늘 추정 ${money(budget.known_standard_cost_usd)} · ${budget.attempts}/${budget.max_attempts}회 · 일일 한도 $${budget.session_cap_usd} (UTC) · 자동 재시도 없음` : 'Decisions 사용량을 확인하고 있습니다.');
    const jev = providers.jev;
    const blocked = jev?.blocked_until_unix > Date.now() / 1000;
    setText('study-jev-limit', !jev?.configured ? 'JEV 키 설정 필요' : blocked ? `JEV 무료 한도 대기 · ${new Date(jev.blocked_until_unix * 1000).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false})} KST 이후` : 'JEV 무료 모델 · 유료 자동 전환 없음');
  }

  async function fetchJson(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store'});
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : '요청을 처리하지 못했습니다.');
      return value;
    } finally { clearTimeout(timeout); }
  }

  async function poll() {
    clearTimeout(timer);
    if (polling || document.hidden) return;
    polling = true;
    try { render(await fetchJson('/api/study')); }
    catch { render({online: false, job: {phase: 'offline'}, providers: {}}); }
    finally {
      polling = false;
      if (!document.hidden) timer = setTimeout(poll, busyPhases.has(current?.job?.phase) ? 700 : 4000);
    }
  }

  async function send(path, body) {
    if (pending) return;
    notice = '';
    pending = true; if (current) render(current);
    try {
      const session = await fetchJson('/api/session');
      render(await fetchJson(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token}, body: JSON.stringify(body)}));
    } catch (error) {
      notice = error.name === 'AbortError' ? '통신이 지연됩니다. 진행 상태를 확인합니다.' : error.message;
      setText('study-state', notice);
      el('study-state').classList.add('is-error');
    } finally {
      pending = false;
      clearTimeout(timer); timer = setTimeout(poll, 200);
    }
  }
  for (const provider of ['openai', 'jev','decisions']) el(`study-${provider}`).onclick = () => send('/api/study/analyze', {provider, camera: Number(el(provider !== 'openai' ? 'study-jev-cameras' : 'study-camera').value)});
  el('study-jev-cameras').onchange = showCameraRoles;
  showCameraRoles();
  el('study-cancel').onclick = () => send('/api/study/cancel', {});
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) poll(); });
  poll();
})();
