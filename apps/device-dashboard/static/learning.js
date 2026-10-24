(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const labels = {reading: '읽기', writing: '필기', typing: '키보드 입력', phone_use: '휴대전화 사용', looking_away: '시선 이동', eating_drinking: '음식·음료', handling_objects: '물건 다루기', person_present: '사람 관찰', seat_empty: '빈 자리 관찰', unknown: '판단 불가'};
  const statuses = {pending: '분석 대기', success: '분석 완료', camera_error: '카메라 오류', provider_error: 'API 오류', dropped: '대기열 초과', skipped: '전송 보류', cancelled: '수집 중지', interrupted: '재시작 중단'};
  const phases = {idle: '대화 준비', connecting: 'GPT Live 연결 중', active: '대화 중', closing: '연결 종료 중', completed: '대화 종료', failed: '연결 실패'};
  let state, busy = false, pollTimer, polling = false, recordsBefore = null, expanded = false;
  let query = new URLSearchParams(), liveBefore = null, selectedSession = '', clockUntil = 0, queryVersion = 0;
  let lastRecords = 0, autoSession = true, historyExpanded = false;
  const put = (id, value) => { if ($(id).textContent !== String(value)) $(id).textContent = value; };
  const time = value => new Date(value * 1000).toLocaleString('ko-KR', {hour12: false});

  async function get(url, options = {}, timeout = 12000) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다.');
      return data;
    } finally { clearTimeout(timer); }
  }

  async function post(path, body) {
    const session = await get('/api/session');
    return get(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token}, body: JSON.stringify(body)});
  }

  function render(value) {
    state = value;
    const provider = value.provider || {}, live = value.live || {};
    const active = ['connecting', 'active', 'closing'].includes(live.phase);
    $('collection-start').disabled = busy || value.enabled || !provider.configured;
    $('collection-stop').disabled = busy || !value.enabled;
    $('live-start').disabled = busy || active || !provider.configured;
    $('live-stop').disabled = busy || !active || live.phase === 'closing';
    $('live-mode').disabled = active;
    put('collection-badge', value.enabled ? '수집 중' : '중지');
    put('collection-queue', value.queued_batches ?? '—');
    put('collection-state', value.error ? `최근 오류: ${value.error}` : value.enabled ? `두 카메라 · 10초 간격${value.last_capture ? ' · 최근 수집 ' + time(value.last_capture) : ''}` : '수집이 중지되어 있습니다. 이미 전송한 요청은 완료 후 저장됩니다.');
    put('collection-provider', `${provider.vision_model || '분석 모델 확인 필요'} · 사진은 OpenAI로 전송 · 원본 사진 DB 저장 없음 · 창을 닫아도 수집 계속`);
    put('live-phase', phases[live.phase] || '상태 확인');
    put('live-state', live.error || (live.phase === 'active' ? '보드 마이크·스피커 사용 중 · SW1로도 종료할 수 있습니다.' : active ? phases[live.phase] : provider.configured ? 'gpt-live-1 · 보드 SW1 또는 대화 시작 버튼을 누르세요.' : 'OpenAI 분석 서비스 연결이 필요합니다.'));
    const education = live.education || provider.education;
    put('live-education', education ? `교육 지침 ${education.version} · SHA ${education.sha256.slice(0, 12)} · ${live.server_confirmed && Object.values(live.server_confirmed).every(Boolean) ? '현재 세션 API 적용 확인' : '다음 세션에 적용'}` : '교육 프롬프트 상태를 확인할 수 없습니다.');
    put('live-reference', live.reference ? `이번 대화 DB 참조 · 관찰 ${live.reference.observation_ids.length}건 · 이전 학습 대화 ${live.reference.previous_session_ids.length}건 · 시작 시점의 자료` : '시작할 때 최근 30분 관찰과 최근 24시간의 학습 대화를 참조합니다.');
    clockUntil = live.phase === 'active' ? performance.now() + (live.remaining_seconds || 0) * 1000 : 0;
    tick();
    if (autoSession && live.id) selectedSession = live.id;
  }

  function tick() {
    const seconds = clockUntil ? Math.max(0, Math.ceil((clockUntil - performance.now()) / 1000)) : state?.live?.phase === 'idle' || !state?.live?.id ? 600 : 0;
    put('live-clock', `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`);
  }

  function tags(id, items, translated) {
    const nodes = items.slice(0, 12).map(item => {
      const li = document.createElement('li'); li.textContent = `${translated ? labels[item.value] || item.value : item.value} · ${item.count}`;
      return li;
    });
    if (!nodes.length) { const li = document.createElement('li'); li.textContent = '관찰 자료 없음'; nodes.push(li); }
    $(id).replaceChildren(...nodes);
  }

  function recordRow(record) {
    const row = document.createElement('tr');
    const cells = Array.from({length: 5}, () => document.createElement('td'));
    cells[0].textContent = time(record.captured);
    cells[1].textContent = `CAM 0${record.camera + 1} · ${statuses[record.status] || record.status}`;
    if (record.status !== 'success') cells[1].classList.add('record-error');
    cells[2].textContent = record.description || record.error || '분석 대기';
    const meta = document.createElement('small');
    meta.textContent = [record.uncertainty, record.model, record.confidence == null ? '' : `근거 명료도 ${Math.round(record.confidence * 100)}%`].filter(Boolean).join(' · ');
    cells[2].append(meta);
    cells[3].textContent = record.keywords.join(', ');
    const action = document.createElement('small'); action.textContent = record.actions.map(a => labels[a] || a).join(' · '); cells[3].append(action);
    const input = document.createElement('input'); input.maxLength = 80; input.value = record.manual_label || ''; input.setAttribute('aria-label', `${time(record.captured)} CAM ${record.camera + 1} 검토 라벨`);
    const save = document.createElement('button'); save.type = 'button'; save.className = 'text-button'; save.textContent = '라벨 저장';
    save.onclick = async () => {
      if (!input.value.trim()) { put('learning-query-state', '검토 라벨을 입력해 주세요.'); input.focus(); return; }
      save.disabled = true;
      try { await post(`/api/learning/records/${record.id}/annotation`, {label: input.value, note: record.manual_note || ''}); put('learning-query-state', '검토 라벨을 저장했습니다. 내보내기에 포함됩니다.'); }
      catch (error) { put('learning-query-state', error.message); }
      finally { save.disabled = false; }
    };
    cells[4].append(input, save); row.append(...cells); return row;
  }

  async function loadRecords(append = false) {
    const version = ++queryVersion, params = new URLSearchParams(query);
    if (append && recordsBefore) params.set('before', recordsBefore);
    const [page, summary] = await Promise.all([get('/api/learning/records?' + params), append ? Promise.resolve(null) : get('/api/learning/summary?' + query)]);
    if (version !== queryVersion) return;
    if (!append) $('learning-records').replaceChildren();
    $('learning-records').append(...page.records.map(recordRow));
    if (!page.records.length && !append) { const row = document.createElement('tr'), cell = document.createElement('td'); cell.colSpan = 5; cell.textContent = '조건에 맞는 관찰 기록이 없습니다.'; row.append(cell); $('learning-records').append(row); }
    recordsBefore = page.next_before; $('learning-more').disabled = !recordsBefore;
    if (append) expanded = true;
    if (summary) {
      const success = summary.counts.filter(c => c.status === 'success').reduce((n, c) => n + c.count, 0);
      const errors = summary.counts.filter(c => !['success', 'pending'].includes(c.status)).reduce((n, c) => n + c.count, 0);
      put('collection-success', success.toLocaleString()); put('collection-errors', errors.toLocaleString());
      tags('learning-actions', summary.actions, true); tags('learning-keywords', summary.keywords, false);
      put('learning-query-state', `조회 범위 · 분석 ${success}건 · 실패·누락 ${errors}건 · 확인된 사용 토큰 ${(summary.usage.total_tokens || 0).toLocaleString()} (묶음별 집계)`);
      for (const sensor of [0, 1]) {
        const record = page.records.find(r => r.camera === sensor);
        put(`collection-camera-${sensor}`, record ? `${time(record.captured)} · ${record.description || record.error || statuses[record.status]}` : '조회 범위 내 관찰 자료 없음');
      }
    }
    for (const format of ['csv', 'jsonl']) $('learning-export-' + format).href = '/api/learning/export?' + new URLSearchParams([...query, ['format', format]]);
    lastRecords = Date.now();
  }

  async function loadHistory(append = false) {
    const requestedSession = selectedSession;
    const params = new URLSearchParams(); if (requestedSession) params.set('session_id', requestedSession);
    if (append && liveBefore) params.set('before', liveBefore);
    const history = await get('/api/learning/live/history?' + params);
    if (requestedSession !== selectedSession) return;
    if (!selectedSession) selectedSession = history.session_id;
    const select = $('live-history-session'), key = history.sessions.map(s => s.id + s.status).join();
    if (select.dataset.key !== key) {
      const options = history.sessions.map(s => { const option = document.createElement('option'); option.value = s.id; option.textContent = `${time(s.started)} · ${s.mode === 'study' ? '학습 QnA' : '자유 대화'} · ${phases[s.status] || s.status}`; return option; });
      select.replaceChildren(...options); select.dataset.key = key;
    }
    select.value = selectedSession;
    const utterances = [], lastBySpeaker = new Map();
    for (const event of history.events.filter(e => e.speaker && e.text)) {
      const previous = lastBySpeaker.get(event.speaker);
      const near = previous && (event.start_ms == null || previous.end_ms == null ? event.received - previous.received < 2.5 : event.start_ms - previous.end_ms < 1600 && event.start_ms - previous.end_ms > -1000);
      if (near) {
        previous.text += event.text; previous.end_ms = event.end_ms; previous.received = event.received;
      } else {
        const utterance = {...event}; utterances.push(utterance); lastBySpeaker.set(event.speaker, utterance);
      }
    }
    const nodes = utterances.map(event => { const row = document.createElement('div'); row.className = 'transcript-row'; const name = document.createElement('strong'); name.textContent = `${event.speaker === 'user' ? '나' : 'AI 친구'} · ${event.start_ms == null ? time(event.received) : (event.start_ms / 1000).toFixed(1) + '초'}`; const text = document.createElement('span'); text.textContent = event.text; row.append(name, text); return row; });
    if (append) $('live-transcripts').prepend(...nodes); else $('live-transcripts').replaceChildren(...nodes);
    if (append) historyExpanded = true;
    if (!nodes.length && !append) { const p = document.createElement('p'); p.className = 'muted'; p.textContent = '저장된 발화 자막이 없습니다.'; $('live-transcripts').append(p); }
    liveBefore = history.next_before; $('live-history-more').disabled = !liveBefore;
    $('live-export').hidden = !selectedSession; $('live-export').href = '/api/learning/live/export?' + new URLSearchParams({session_id: selectedSession});
    const session = history.selected_session;
    const audit = history.context;
    const referenceInfo = audit ? ` · 참조 관찰 ${audit.metadata.observation_ids.length}건 / 이전 학습 대화 ${audit.metadata.previous_session_ids.length}건 · 교육 ${audit.education?.version || 'API 확인 전'}` : ' · DB 참조 스냅샷 없음';
    put('live-history-meta', session ? `${session.finalized ? 'API 종료 확인됨' : 'API 최종 사용량 미확정'} · ${session.reason || session.status}${referenceInfo} · 원음 저장 없음 · 자막의 시각은 세션 기준` : '원음 저장 없음 · 자막은 음성 인식 결과이며 오류가 있을 수 있습니다.');
  }

  async function action(path, body, target) {
    if (busy) return;
    busy = true; if (state) render(state);
    try { await post(path, body); if (path.endsWith('/live/start')) { autoSession = true; selectedSession = ''; } }
    catch (error) { put(target, error.name === 'AbortError' ? '응답이 지연됩니다. 현재 상태를 다시 확인해 주세요.' : error.message); }
    finally { busy = false; clearTimeout(pollTimer); pollTimer = setTimeout(poll, 1200); }
  }

  async function poll() {
    clearTimeout(pollTimer);
    if (polling || document.hidden) return;
    polling = true;
    try {
      const previousSession = selectedSession;
      render(await get('/api/learning'));
      if (selectedSession !== previousSession) historyExpanded = false;
      if (!historyExpanded) {
        try { await loadHistory(); }
        catch { put('live-history-meta', '대화 기록 조회가 지연됩니다. 세션 상태와 별도로 다시 확인합니다.'); }
      }
      if (!expanded && Date.now() - lastRecords > 10000 && !$('learning-records').contains(document.activeElement)) {
        try { await loadRecords(); }
        catch { put('learning-query-state', '관찰 기록 조회가 지연됩니다. 다시 조회해 주세요.'); }
      }
    } catch { put('collection-state', '수집 서비스에 연결하지 못했습니다.'); $('collection-start').disabled = $('live-start').disabled = true; }
    finally { polling = false; if (!document.hidden) pollTimer = setTimeout(poll, 3000); }
  }

  $('collection-start').onclick = () => action('/api/learning/collection', {enabled: true}, 'collection-state');
  $('collection-stop').onclick = () => action('/api/learning/collection', {enabled: false}, 'collection-state');
  $('live-start').onclick = () => action('/api/learning/live/start', {mode: $('live-mode').value}, 'live-state');
  $('live-stop').onclick = () => action('/api/learning/live/stop', {}, 'live-state');
  $('learning-filter').onsubmit = event => {
    event.preventDefault(); const params = new URLSearchParams();
    for (const [id, name] of [['learning-since', 'since'], ['learning-until', 'until']]) if ($(id).value) params.set(name, String(new Date($(id).value).getTime() / 1000));
    if ($('learning-camera').value) params.set('camera', $('learning-camera').value);
    if ($('learning-keyword').value.trim()) params.set('keyword', $('learning-keyword').value.trim());
    query = params; expanded = false; loadRecords().catch(e => put('learning-query-state', e.message));
  };
  $('learning-more').onclick = () => loadRecords(true).catch(e => put('learning-query-state', e.message));
  $('live-history-session').onchange = () => { autoSession = false; historyExpanded = false; selectedSession = $('live-history-session').value; loadHistory().catch(e => put('live-state', e.message)); };
  $('live-history-more').onclick = () => loadHistory(true).catch(e => put('live-state', e.message));
  document.addEventListener('visibilitychange', () => { clearTimeout(pollTimer); if (!document.hidden) poll(); });
  const start = new Date(Date.now() - 86400000); start.setMinutes(start.getMinutes() - start.getTimezoneOffset());
  $('learning-since').value = start.toISOString().slice(0, 16); query.set('since', String(new Date($('learning-since').value).getTime() / 1000));
  setInterval(() => { if (!document.hidden) tick(); }, 1000);
  poll();
})();
