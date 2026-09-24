/* Native controls over a compiled question contract. No remote libraries. */
(() => {
  'use strict';
  const spec = JSON.parse(document.getElementById('aq-spec').textContent);
  const snapshot = JSON.parse(document.getElementById('aq-snapshot').textContent);
  const form = document.getElementById('aq-form');
  const status = document.getElementById('aq-status');
  const footer = document.getElementById('aq-footer');
  const touched = new Set();
  const token = new URLSearchParams(location.search).get('t') || '';
  let finished = snapshot?.mode !== 'collect';
  const card = q => document.getElementById(`aq-question-${q.id}`);
  const fields = name => [...form.elements].filter(el => el.name === name);
  const value = (data, name) => String(data.get(name) ?? '').trim();
  function collect() {
    const data = new FormData(form), answers = Object.create(null), other = [], notes = Object.create(null);
    for (const q of spec.questions) {
      const id = q.id, type = q.type;
      if (value(data, 'note:' + id)) notes[id] = value(data, 'note:' + id);
      if (type === 'single_select') {
        const selected = value(data, id);
        if (selected === '__other__') {
          if (value(data, 'other:' + id)) { answers[id] = value(data, 'other:' + id); other.push(id); }
        } else if (selected) answers[id] = selected;
      } else if (type === 'multi_select') {
        const selected = data.getAll(id).filter(v => v !== '__other__');
        if (data.getAll(id).includes('__other__')) {
          const text = value(data, 'other:' + id);
          if (text) { selected.push(text); other.push(id); }
        }
        if (selected.length) answers[id] = selected;
      } else if (type === 'scale') {
        if (touched.has(id)) answers[id] = Number(data.get(id));
      } else if (type === 'number') {
        if (value(data, id)) answers[id] = Number(data.get(id));
      } else if (['short_text', 'long_text'].includes(type)) {
        if (value(data, id)) answers[id] = value(data, id);
      } else if (type === 'ranking') {
        if (data.has('confirm:' + id)) answers[id] = [...card(q).querySelectorAll('li[data-value]')].map(el => el.dataset.value);
      } else if (type === 'matrix') {
        const rows = Object.create(null);
        for (const row of q.rows) if (value(data, id + '.' + row.value)) rows[row.value] = value(data, id + '.' + row.value);
        if (Object.keys(rows).length) answers[id] = rows;
      } else if (type === 'review') {
        const items = Object.create(null);
        for (const item of q.items) if (value(data, id + '.' + item.id)) items[item.id] = {decision: value(data, id + '.' + item.id), comment: value(data, 'comment:' + id + ':' + item.id)};
        if (Object.keys(items).length) answers[id] = items;
      }
    }
    return {answers, other, notes, comments: value(data, 'form:comments')};
  }
  function refresh() {
    const answered = Object.keys(collect().answers).length;
    document.getElementById('aq-progress').textContent = `${answered} / ${spec.questions.length} answered`;
    for (const q of spec.questions) {
      if (['single_select', 'multi_select'].includes(q.type) && q.allow_other !== false) {
        const selected = fields(q.id).some(el => el.value === '__other__' && el.checked);
        const text = fields('other:' + q.id)[0];
        text.setCustomValidity(selected && !text.value.trim() ? 'Enter an Other answer or deselect Other.' : '');
      }
      if (q.type === 'scale') document.getElementById(`aq-output-${q.id}`).textContent = touched.has(q.id) ? fields(q.id)[0].value : 'Unanswered — move the slider';
      if (q.type === 'ranking') [...card(q).querySelectorAll('li[data-value]')].forEach((li, index, all) => {
        li.querySelector('[data-move=up]').disabled = index === 0;
        li.querySelector('[data-move=down]').disabled = index === all.length - 1;
      });
    }
  }
  function terminal(result) {
    finished = true;
    footer.hidden = true;
    document.querySelectorAll('.aq-controls').forEach(el => { el.disabled = true; });
    document.getElementById('aq-comments-input').disabled = true;
    status.textContent = result.status === 'submitted' ? (result.meta.save_error ? `Answers received; archive failed: ${result.meta.save_error}` : 'Answers received.' + (result.meta.saved ? ` Saved: ${result.meta.saved}` : '')) : `Form ${result.status}.`;
  }
  function review(result) {
    for (const q of spec.questions) {
      const node = card(q).querySelector('.aq-recorded');
      node.hidden = false;
      const title = document.createElement('strong'); title.textContent = 'Recorded answer';
      const answer = document.createElement('pre');
      answer.textContent = q.id in result.answers ? (typeof result.answers[q.id] === 'string' ? result.answers[q.id] : JSON.stringify(result.answers[q.id], null, 2)) : 'Skipped';
      node.append(title, answer);
      if (result.meta.notes?.[q.id]) { const note = document.createElement('p'); note.textContent = `Note: ${result.meta.notes[q.id]}`; node.append(note); }
      if (result.meta.diverged?.includes(q.id)) { const note = document.createElement('p'); note.textContent = 'This answer differs from the recommendation.'; node.append(note); }
      // Hide empty live controls but preserve question labels/recommendations for reading.
      card(q).querySelectorAll('input,select,textarea,button,.aq-note').forEach(el => { el.hidden = true; });
    }
    document.getElementById('aq-comments-input').value = result.meta.comments || '';
    terminal(result); status.textContent = 'Archived submission · read-only';
  }
  async function request(route, body) {
    const response = await fetch(`${route}?t=${encodeURIComponent(token)}`, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    return {ok:response.ok, result:await response.json()};
  }
  async function send(route, body) {
    if (finished) return;
    document.getElementById('aq-submit').disabled = true;
    document.getElementById('aq-cancel').disabled = true;
    status.textContent = 'Sending…';
    for (const q of spec.questions) document.getElementById(`aq-error-${q.id}`).textContent = '';
    try {
      let response;
      try { response = await request(route, body); }
      catch (error) {
        const state = await request('/state');
        if (!state.ok || state.result.status === 'waiting') throw error;
        response = state;
      }
      if (!response.ok) {
        const errors = response.result.errors || {form:response.result.message || 'Submission failed'};
        for (const [id, message] of Object.entries(errors)) {
          const el = document.getElementById(`aq-error-${id}`); if (el) el.textContent = message;
        }
        const first = spec.questions.find(q => errors[q.id]);
        if (first) card(first).focus();
        status.textContent = Object.values(errors).join('; ');
      } else {
        terminal(response.result);
        try { await request('/ack', {}); } catch { /* accepted result is already displayed */ }
      }
    } catch (error) { status.textContent = `Not submitted: ${error.message}. Answers remain here; retry while the session is running.`; }
    finally {
      if (!finished) { document.getElementById('aq-submit').disabled = false; document.getElementById('aq-cancel').disabled = false; }
    }
  }
  document.addEventListener('input', event => {
    if (finished) return;
    const changed = event.target.closest('.aq-question');
    if (changed) changed.querySelector('.aq-error').textContent = '';
    if (event.target.type === 'range') touched.add(event.target.name);
    refresh();
  });
  document.addEventListener('change', () => { if (!finished) refresh(); });
  document.addEventListener('click', event => {
    if (finished) return;
    const button = event.target.closest('[data-move]'); if (!button) return;
    const item = button.closest('li'), list = item.parentElement;
    if (button.dataset.move === 'up' && item.previousElementSibling) item.previousElementSibling.before(item);
    if (button.dataset.move === 'down' && item.nextElementSibling) item.nextElementSibling.after(item);
    fields('confirm:' + list.dataset.ranking)[0].checked = true;
    refresh(); button.focus();
  });
  form.addEventListener('submit', event => { event.preventDefault(); if (form.reportValidity()) send('/submit', collect()); });
  document.getElementById('aq-cancel').addEventListener('click', () => send('/cancel', {}));
  document.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && !finished) { event.preventDefault(); form.requestSubmit(); } });
  refresh();
  if (snapshot?.mode === 'review') review(snapshot.result);
  else if (finished) terminal({status:'read-only'});
  else status.textContent = 'Nothing submitted yet.';
})();
