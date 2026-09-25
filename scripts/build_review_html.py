#!/usr/bin/env python3
"""Genera scripts/revisar_preguntas_nuevas.html a partir de
scripts/preguntas_nuevas_pendientes.json, embebiendo los datos inline (para que
el archivo funcione abierto directamente con doble clic, sin servidor local).

USO:
    .venv/bin/python scripts/build_review_html.py
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, 'preguntas_nuevas_pendientes.json')
OUTPUT_PATH = os.path.join(BASE_DIR, 'revisar_preguntas_nuevas.html')

with open(JSON_PATH, 'r', encoding='utf-8') as f:
    questions = json.load(f)

DATA_JSON = json.dumps(questions, ensure_ascii=False)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Revisar preguntas nuevas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #f4f6f8;
    --surface: #ffffff;
    --surface-2: #eef1f4;
    --border: #d7dee5;
    --text: #1b2430;
    --text-dim: #56626f;
    --accent: #0f6e5c;
    --accent-soft: #e3f3ee;
    --danger: #b3261e;
    --danger-soft: #fbe9e7;
    --warn: #9a6700;
    --warn-soft: #fdf3d8;
    --mono: 'IBM Plex Mono', ui-monospace, monospace;
    --sans: 'IBM Plex Sans', system-ui, sans-serif;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #10151b;
      --surface: #171e26;
      --surface-2: #1e2731;
      --border: #2c3944;
      --text: #e7edf2;
      --text-dim: #9aa9b6;
      --accent: #4fd3ab;
      --accent-soft: #163a30;
      --danger: #ff8a80;
      --danger-soft: #3a1d1a;
      --warn: #ffcc66;
      --warn-soft: #3a2f14;
      color-scheme: dark;
    }
  }
  :root[data-theme="dark"] {
    --bg: #10151b;
    --surface: #171e26;
    --surface-2: #1e2731;
    --border: #2c3944;
    --text: #e7edf2;
    --text-dim: #9aa9b6;
    --accent: #4fd3ab;
    --accent-soft: #163a30;
    --danger: #ff8a80;
    --danger-soft: #3a1d1a;
    --warn: #ffcc66;
    --warn-soft: #3a2f14;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    padding-inline: 16px;
    padding-block: 20px 60px;
  }
  h1, h2, h3 { text-wrap: balance; }
  .wrap { max-width: 880px; margin: 0 auto; }

  header.top {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 18px;
  }
  header.top .eyebrow {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent);
  }
  header.top h1 { font-size: 26px; margin: 0; font-weight: 700; }
  header.top p { margin: 0; color: var(--text-dim); font-size: 14px; max-width: 65ch; }

  .toolbar {
    position: sticky;
    top: env(safe-area-inset-top, 0px);
    z-index: 5;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 20px;
    box-shadow: 0 1px 0 rgba(0,0,0,0.03);
  }
  .toolbar .stats {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    font-family: var(--mono);
    font-size: 13px;
    color: var(--text-dim);
  }
  .toolbar .stats b { color: var(--text); font-variant-numeric: tabular-nums; }
  .toolbar .actions { display: flex; gap: 8px; flex-wrap: wrap; }

  select, button {
    font-family: var(--sans);
    font-size: 13px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    color: var(--text);
    padding: 7px 12px;
    cursor: pointer;
  }
  button.primary {
    background: var(--accent);
    color: #05231b;
    border-color: var(--accent);
    font-weight: 600;
  }
  button:hover { filter: brightness(1.05); }
  button.small { padding: 5px 9px; font-size: 12px; }

  .lang-toggle { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .lang-toggle button { border: none; border-radius: 0; background: var(--surface-2); }
  .lang-toggle button.active { background: var(--accent); color: #05231b; font-weight: 600; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 16px;
    transition: opacity .15s ease;
  }
  .card.rejected { opacity: 0.5; }
  .card.rejected .body { filter: grayscale(0.3); }

  .card .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
  }
  .badge {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.03em;
    padding: 3px 8px;
    border-radius: 999px;
    border: 1px solid var(--border);
    color: var(--text-dim);
    white-space: nowrap;
  }
  .badge.topic { background: var(--surface-2); color: var(--text); }
  .badge.idx { font-weight: 600; color: var(--text); }
  .badge.diff-easy { color: var(--accent); border-color: var(--accent); }
  .badge.diff-hard { color: var(--danger); border-color: var(--danger); }
  .badge.diff-medium { color: var(--warn); border-color: var(--warn); }

  .approve-toggle { margin-left: auto; display: flex; gap: 6px; }
  .approve-toggle button {
    font-size: 12px;
    padding: 5px 10px;
  }
  .approve-toggle button.approve.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .approve-toggle button.reject.active { background: var(--danger-soft); border-color: var(--danger); color: var(--danger); font-weight: 600; }

  .qtext {
    font-size: 16px;
    line-height: 1.5;
    font-weight: 500;
    margin: 0 0 14px 0;
    outline: none;
    border-radius: 6px;
    padding: 2px 4px;
    margin-inline: -4px;
  }
  .qtext:focus { background: var(--surface-2); }

  .opt {
    display: grid;
    grid-template-columns: 22px 1fr;
    gap: 10px;
    padding: 8px 6px;
    border-radius: 8px;
    align-items: start;
    margin-bottom: 4px;
  }
  .opt.correct { background: var(--accent-soft); }
  .opt .letter {
    font-family: var(--mono);
    font-weight: 700;
    font-size: 13px;
    color: var(--text-dim);
    padding-top: 2px;
  }
  .opt.correct .letter { color: var(--accent); }
  .opt .otext {
    font-size: 14px;
    outline: none;
    border-radius: 4px;
    padding: 1px 3px;
    margin-inline: -3px;
  }
  .opt .otext:focus { background: var(--surface-2); }
  .opt .explain {
    font-size: 12.5px;
    color: var(--text-dim);
    margin-top: 3px;
    outline: none;
    border-radius: 4px;
    padding: 1px 3px;
    margin-inline: -3px;
    line-height: 1.4;
  }
  .opt .explain:focus { background: var(--surface-2); color: var(--text); }

  .keywords {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px dashed var(--border);
  }

  footer.export-help {
    max-width: 880px;
    margin: 24px auto 0;
    font-size: 13px;
    color: var(--text-dim);
    border-top: 1px solid var(--border);
    padding-top: 14px;
  }
  footer.export-help code {
    font-family: var(--mono);
    background: var(--surface-2);
    padding: 1px 5px;
    border-radius: 4px;
  }

  #toast {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%) translateY(10px);
    background: var(--text);
    color: var(--bg);
    padding: 9px 16px;
    border-radius: 8px;
    font-size: 13px;
    opacity: 0;
    pointer-events: none;
    transition: opacity .2s ease, transform .2s ease;
    z-index: 20;
  }
  #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

  @media (max-width: 480px) {
    .toolbar { flex-direction: column; align-items: stretch; }
    .approve-toggle { margin-left: 0; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <span class="eyebrow">AI Mentoring &middot; Banco de preguntas</span>
    <h1>Revisar preguntas nuevas</h1>
    <p>__COUNT__ preguntas candidatas para cubrir el vacío detectado en Security, Identity &amp; Compliance
    y otros temas con servicios faltantes (DAX, Glue, ElastiCache, Detective, CloudTrail, Security Groups,
    VPC Peering, DocumentDB, etc). Los textos son editables: hacé clic sobre cualquier enunciado, opción o
    explicación para corregirlo antes de exportar.</p>
  </header>

  <div class="toolbar">
    <div class="stats">
      <span>Total: <b id="statTotal">0</b></span>
      <span>Aprobadas: <b id="statApproved">0</b></span>
      <span>Rechazadas: <b id="statRejected">0</b></span>
    </div>
    <div class="actions">
      <div class="lang-toggle">
        <button id="langEn" class="active" data-lang="en">EN</button>
        <button id="langPt" data-lang="pt">PT-BR</button>
      </div>
      <select id="topicFilter"></select>
      <button id="approveAllBtn" class="small">Aprobar todas</button>
      <button id="exportBtn" class="primary">Descargar aprobadas (JSON)</button>
    </div>
  </div>

  <div id="cards"></div>
</div>

<footer class="export-help">
  Al descargar, se genera <code>preguntas_aprobadas.json</code> con solo las preguntas marcadas como
  aprobadas (con cualquier corrección de texto que hayas hecho acá). Guardalo en
  <code>scripts/</code> y pasalo al script de carga a la base de datos.
</footer>

<div id="toast"></div>

<script id="question-data" type="application/json">__DATA_JSON__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById('question-data').textContent);
  DATA.forEach(function (q, i) { q.__id = i; q.__approved = true; });

  var state = { lang: 'en', topic: 'all' };

  var cardsEl = document.getElementById('cards');
  var topicFilterEl = document.getElementById('topicFilter');
  var toastEl = document.getElementById('toast');

  var topics = Array.from(new Set(DATA.map(function (q) { return q.topic; })));
  var optAll = document.createElement('option');
  optAll.value = 'all';
  optAll.textContent = 'Todos los temas (' + DATA.length + ')';
  topicFilterEl.appendChild(optAll);
  topics.forEach(function (t) {
    var count = DATA.filter(function (q) { return q.topic === t; }).length;
    var opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t + ' (' + count + ')';
    topicFilterEl.appendChild(opt);
  });

  function diffClass(d) {
    var k = (d || '').toLowerCase();
    if (k === 'easy') return 'diff-easy';
    if (k === 'hard') return 'diff-hard';
    return 'diff-medium';
  }

  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () { toastEl.classList.remove('show'); }, 1800);
  }

  function updateStats() {
    var approved = DATA.filter(function (q) { return q.__approved; }).length;
    document.getElementById('statTotal').textContent = DATA.length;
    document.getElementById('statApproved').textContent = approved;
    document.getElementById('statRejected').textContent = DATA.length - approved;
  }

  function makeEditable(el, obj, field) {
    el.contentEditable = 'true';
    el.spellcheck = false;
    el.addEventListener('input', function () {
      obj[field] = el.textContent;
    });
  }

  function render() {
    cardsEl.innerHTML = '';
    var visible = DATA.filter(function (q) {
      return state.topic === 'all' || q.topic === state.topic;
    });

    visible.forEach(function (q) {
      var card = document.createElement('article');
      card.className = 'card' + (q.__approved ? '' : ' rejected');

      var meta = document.createElement('div');
      meta.className = 'meta';

      var idxBadge = document.createElement('span');
      idxBadge.className = 'badge idx';
      idxBadge.textContent = '#' + (q.__id + 1);
      meta.appendChild(idxBadge);

      var topicBadge = document.createElement('span');
      topicBadge.className = 'badge topic';
      topicBadge.textContent = q.topic;
      meta.appendChild(topicBadge);

      var diffBadge = document.createElement('span');
      diffBadge.className = 'badge ' + diffClass(q.difficulty);
      diffBadge.textContent = q.difficulty;
      meta.appendChild(diffBadge);

      var toggles = document.createElement('div');
      toggles.className = 'approve-toggle';
      var approveBtn = document.createElement('button');
      approveBtn.className = 'approve' + (q.__approved ? ' active' : '');
      approveBtn.textContent = '✓ Aprobar';
      approveBtn.onclick = function () {
        q.__approved = true;
        updateStats();
        render();
      };
      var rejectBtn = document.createElement('button');
      rejectBtn.className = 'reject' + (!q.__approved ? ' active' : '');
      rejectBtn.textContent = '✕ Rechazar';
      rejectBtn.onclick = function () {
        q.__approved = false;
        updateStats();
        render();
      };
      toggles.appendChild(approveBtn);
      toggles.appendChild(rejectBtn);
      meta.appendChild(toggles);

      card.appendChild(meta);

      var body = document.createElement('div');
      body.className = 'body';

      var qtextField = state.lang === 'pt' ? 'question_text_pt' : 'question_text';
      var qtext = document.createElement('p');
      qtext.className = 'qtext';
      qtext.textContent = q[qtextField];
      makeEditable(qtext, q, qtextField);
      body.appendChild(qtext);

      Object.keys(q.options).sort().forEach(function (key) {
        var opt = q.options[key];
        var optEl = document.createElement('div');
        optEl.className = 'opt' + (opt.is_correct ? ' correct' : '');

        var letter = document.createElement('div');
        letter.className = 'letter';
        letter.textContent = key + (opt.is_correct ? ' ✓' : '');
        optEl.appendChild(letter);

        var col = document.createElement('div');

        var textField = state.lang === 'pt' ? 'text_pt' : 'text';
        var otext = document.createElement('div');
        otext.className = 'otext';
        otext.textContent = opt[textField];
        makeEditable(otext, opt, textField);
        col.appendChild(otext);

        var explField = state.lang === 'pt' ? 'explanation_pt' : 'explanation';
        var explain = document.createElement('div');
        explain.className = 'explain';
        explain.textContent = opt[explField];
        makeEditable(explain, opt, explField);
        col.appendChild(explain);

        optEl.appendChild(col);
        body.appendChild(optEl);
      });

      var kw = document.createElement('div');
      kw.className = 'keywords';
      kw.textContent = Object.keys(q.options).map(function (k) { return q.options[k].keywords; }).join(' • ');
      body.appendChild(kw);

      card.appendChild(body);
      cardsEl.appendChild(card);
    });
  }

  document.getElementById('langEn').onclick = function () {
    state.lang = 'en';
    document.getElementById('langEn').classList.add('active');
    document.getElementById('langPt').classList.remove('active');
    render();
  };
  document.getElementById('langPt').onclick = function () {
    state.lang = 'pt';
    document.getElementById('langPt').classList.add('active');
    document.getElementById('langEn').classList.remove('active');
    render();
  };
  topicFilterEl.onchange = function () {
    state.topic = topicFilterEl.value;
    render();
  };
  document.getElementById('approveAllBtn').onclick = function () {
    DATA.forEach(function (q) { q.__approved = true; });
    updateStats();
    render();
    showToast('Todas las preguntas visibles fueron aprobadas.');
  };

  document.getElementById('exportBtn').onclick = function () {
    var approved = DATA.filter(function (q) { return q.__approved; }).map(function (q) {
      var copy = JSON.parse(JSON.stringify(q));
      delete copy.__id;
      delete copy.__approved;
      return copy;
    });
    var blob = new Blob([JSON.stringify(approved, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'preguntas_aprobadas.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    showToast(approved.length + ' preguntas exportadas a preguntas_aprobadas.json');
  };

  updateStats();
  render();
})();
</script>
</body>
</html>
"""

html = HTML_TEMPLATE.replace('__DATA_JSON__', DATA_JSON).replace('__COUNT__', str(len(questions)))

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Generado: {OUTPUT_PATH} ({len(questions)} preguntas)')
