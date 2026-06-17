/* =============================================================
   vid2note 客户端原型 · 共享交互
   克制、有目的：主题切换 / 流水线实时推进 / 标签页 / 复制 / 筛选
   所有 DOM 操作都有 null 守卫，静态 HTML 即使无 JS 也正确呈现
   ============================================================= */
(function () {
  'use strict';

  /* ---------- 主题切换 (light / dark) ---------- */
  var saved = null;
  try { saved = localStorage.getItem('v2n-theme'); } catch (e) {}
  if (saved) document.documentElement.setAttribute('data-theme', saved);

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-theme-toggle]');
    if (!btn) return;
    var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('v2n-theme', next); } catch (e) {}
  });

  /* ---------- 载入 reveal (错峰淡入) ---------- */
  function reveal() {
    var els = document.querySelectorAll('.reveal:not(.in)');
    els.forEach(function (el, i) {
      setTimeout(function () { el.classList.add('in'); }, 50 + i * 45);
    });
  }

  /* ---------- 标签页 ---------- */
  document.addEventListener('click', function (e) {
    var tab = e.target.closest('.tab[data-target]');
    if (!tab) return;
    var scope = tab.closest('[data-tabs]') || tab.parentElement;
    scope.querySelectorAll('.tab').forEach(function (t) {
      t.classList.toggle('active', t === tab);
    });
    var panes = scope.parentElement.querySelectorAll('.tab-pane');
    panes.forEach(function (p) { p.classList.remove('active'); });
    var target = document.querySelector(tab.dataset.target);
    if (target) target.classList.add('active');
  });

  /* ---------- 分段控制 ---------- */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.seg button');
    if (!b) return;
    b.parentElement.querySelectorAll('button').forEach(function (x) { x.classList.toggle('active', x === b); });
    var seg = b.closest('.seg');
    if (seg.dataset.bind) {
      var val = b.dataset.value;
      document.querySelectorAll('[data-seg="' + seg.dataset.bind + '"]').forEach(function (p) {
        p.style.display = (p.dataset.value === val) ? '' : 'none';
      });
    }
  });

  /* ---------- range 数值显示 ---------- */
  document.querySelectorAll('.range[data-out]').forEach(function (r) {
    var out = document.querySelector(r.dataset.out);
    function sync() { if (out) out.textContent = r.value; }
    r.addEventListener('input', sync); sync();
  });

  /* ---------- 复制 ---------- */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (!btn) return;
    var text = '';
    if (btn.dataset.copyTarget) {
      var el = document.querySelector(btn.dataset.copyTarget);
      text = el ? el.innerText : '';
    } else { text = btn.dataset.copy || ''; }
    var done = function () {
      var orig = btn.innerHTML;
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>已复制';
      setTimeout(function () { btn.innerHTML = orig; }, 1400);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, done);
    } else { done(); }
  });

  /* ============================================================
     流水线 · 节点进度边界 (取自 core/pipeline/nodes.py 的真实进度)
     ============================================================ */
  var TH = [25, 45, 70, 95, 98, 100];
  var NODE_LABELS = ['下载', '提取音频', '转录', '整理笔记', '思维导图', '清理'];

  function currentNodeIndex(p) {
    for (var i = 0; i < TH.length; i++) { if (p < TH[i]) return i; }
    return TH.length - 1;
  }

  /* 渲染横向迷你流水线 (.pipeline-rail) */
  function renderRail(rail, p) {
    var nodes = rail.querySelectorAll('.pr-node');
    var links = rail.querySelectorAll('.pr-link');
    var ci = currentNodeIndex(p);
    nodes.forEach(function (n, i) {
      n.classList.remove('done', 'active', 'failed');
      if (p >= TH[i]) n.classList.add('done');
      else if (i === ci) n.classList.add('active');
    });
    // 连接线填到「当前激活节点」为止：到达的节点(已完成或激活)都算连通
    links.forEach(function (l, i) {
      l.classList.toggle('done', (i + 1) <= ci);
    });
    var pct = rail.parentElement.querySelector('[data-pct]');
    if (pct) pct.textContent = Math.round(p) + '%';
    var bar = rail.parentElement.querySelector('.progress > i');
    if (bar) bar.style.width = p + '%';
  }

  /* 渲染纵向大流水线 (.pipeline-flow) */
  function renderFlow(flow, p) {
    var nodes = flow.querySelectorAll('.pf-node');
    var ci = currentNodeIndex(p);
    var lineFill = flow.querySelector('.pf-line > i');
    var ci2 = currentNodeIndex(p);
    nodes.forEach(function (n, i) {
      n.classList.remove('done', 'active', 'failed');
      if (p >= TH[i]) n.classList.add('done');
      else if (i === ci2) n.classList.add('active');
    });
    if (lineFill) {
      var pct = Math.min(100, (ci2 / (nodes.length - 1)) * 100);
      if (p >= 100) pct = 100;
      lineFill.style.height = pct + '%';
    }
    var headPct = document.querySelector('[data-flow-pct]');
    if (headPct) headPct.textContent = Math.round(p) + '%';
    var headBar = document.querySelector('[data-flow-bar] > i');
    if (headBar) headBar.style.width = p + '%';
  }

  /* 实时推进：在 [data-live] 上启动一个 0→100 的模拟 */
  function livePipeline() {
    document.querySelectorAll('[data-live]').forEach(function (el) {
      var start = parseFloat(el.dataset.start || '0');
      var end = parseFloat(el.dataset.end || '100');
      var dur = parseFloat(el.dataset.dur || '40') * 1000;
      var t0 = null;
      function tick(ts) {
        if (t0 === null) t0 = ts;
        var k = Math.min(1, (ts - t0) / dur);
        var p = start + (end - start) * k;
        if (el.classList.contains('pipeline-rail')) renderRail(el, p);
        else if (el.classList.contains('pipeline-flow')) {
          renderFlow(el, p);
          appendLog(el, p);
        }
        if (k < 1) requestAnimationFrame(tick);
      }
      // 初始渲染一次，保证静态正确
      if (el.classList.contains('pipeline-rail')) renderRail(el, start);
      if (el.classList.contains('pipeline-flow')) renderFlow(el, start);
      requestAnimationFrame(tick);
    });
  }

  /* 日志终端：随进度追加真实感日志行 */
  var LOG_BANK = [
    ['info', 'yt-dlp 选取格式 137 (mp4 1280x720)'],
    ['ok',   'download: video.mp4 · 184.2 MB'],
    ['dim',  'ffmpeg -i video.mp4 -vn -acodec pcm_s16le audio.wav'],
    ['ok',   'extract_audio: audio.wav · 44.1kHz / 2ch'],
    ['info', 'asrtools-b 提交音频 31:24 ...'],
    ['info', 'transcribe: 识别中 (语言=zh)'],
    ['ok',   'transcribe: transcript.srt · 412 段'],
    ['dim',  'llm=qwen-turbo · chunk=4000 · temp=0.3'],
    ['info', 'organize: 分块 3/3 · 生成笔记 ...'],
    ['ok',   'organize: note.md · 2,841 字'],
    ['info', 'mindmap: 抽取大纲 → xmind'],
    ['ok',   'mindmap: mindmap.xmind · 28 节点'],
    ['dim',  'cleanup: 移除临时音视频 (保留 srt)'],
    ['ok',   'task.completed · 用时 6m 12s']
  ];
  function appendLog(flow, p) {
    var term = flow.closest('[data-log-scope]')
      ? flow.closest('[data-log-scope]').querySelector('[data-live-log]')
      : document.querySelector('[data-live-log]');
    if (!term) return;
    var idx = Math.min(LOG_BANK.length, Math.floor((p / 100) * LOG_BANK.length) + 1);
    var lines = term.querySelectorAll('.lt-line');
    if (lines.length >= idx) return; // 已渲染到该进度
    var frag = document.createDocumentFragment();
    for (var i = lines.length; i < idx; i++) {
      var item = LOG_BANK[i];
      var div = document.createElement('div');
      div.className = 'lt-line';
      var time = '06:' + String(12 + i * 2).padStart(2, '0');
      var cls = { info: 'lt-info', ok: 'lt-ok', warn: 'lt-warn', err: 'lt-err', dim: 'lt-dim' }[item[0]] || 'lt-dim';
      div.innerHTML = '<span class="lt-time">' + time + ':0' + (i % 9) + '</span> <span class="' + cls + '">[' + item[0] + ']</span> ' + item[1];
      frag.appendChild(div);
    }
    term.appendChild(frag);
    term.scrollTop = term.scrollHeight;
  }

  /* ============================================================
     历史：筛选 + 搜索
     ============================================================ */
  function initHistory() {
    var table = document.querySelector('[data-history]');
    if (!table) return;
    var rows = table.querySelectorAll('tbody tr');
    function apply() {
      var status = (document.querySelector('[data-filter].chip.active') || {}).dataset ? document.querySelector('[data-filter].chip.active').dataset.filter : 'all';
      var q = (document.querySelector('[data-history-search]') || {}).value || '';
      q = q.toLowerCase().trim();
      rows.forEach(function (r) {
        var okS = (status === 'all' || r.dataset.status === status);
        var okQ = !q || r.textContent.toLowerCase().indexOf(q) !== -1;
        r.style.display = (okS && okQ) ? '' : 'none';
      });
    }
    document.querySelectorAll('[data-filter]').forEach(function (c) {
      c.addEventListener('click', function () {
        document.querySelectorAll('[data-filter]').forEach(function (x) { x.classList.toggle('active', x === c); });
        apply();
      });
    });
    var search = document.querySelector('[data-history-search]');
    if (search) search.addEventListener('input', apply);
  }

  /* ---------- 设置：LLM 提供商卡片单选展开 ---------- */
  function initProviders() {
    var cards = document.querySelectorAll('[data-provider]');
    if (!cards.length) return;
    cards.forEach(function (card) {
      card.addEventListener('click', function (e) {
        if (e.target.closest('input,textarea,.btn')) return;
        cards.forEach(function (c) {
          c.classList.toggle('selected', c === card);
          var body = c.querySelector('.prov-body');
          if (body) body.style.display = (c === card) ? '' : 'none';
        });
      });
    });
  }

  /* ---------- 主控台：URL 提交 → 生成任务卡 ---------- */
  function initComposer() {
    var form = document.querySelector('[data-composer]');
    if (!form) return;
    var input = form.querySelector('input');
    var list = document.querySelector('[data-active-list]');
    var btn = form.querySelector('[data-submit]');
    function submit() {
      var url = (input.value || '').trim();
      if (!url) { input.focus(); return; }
      if (!/^https?:\/\//.test(url)) { input.style.borderColor = 'var(--danger)'; return; }
      input.style.borderColor = '';
      input.value = '';
      if (!list) return;
      var card = document.createElement('div');
      card.className = 'card card-pad reveal in';
      card.style.marginBottom = '12px';
      var host = url.replace(/^https?:\/\//, '').split('/')[0];
      card.innerHTML = composerCardHtml(host, url);
      list.insertBefore(card, list.firstChild);
      // 启动该卡的迷你流水线
      var rail = card.querySelector('.pipeline-rail');
      if (rail) {
        rail.removeAttribute('data-live');
        rail.setAttribute('data-live', '');
        rail.dataset.start = 0; rail.dataset.end = 100; rail.dataset.dur = 30;
        runOneRail(rail);
      }
    }
    if (btn) btn.addEventListener('click', submit);
    if (input) input.addEventListener('keydown', function (e) { if (e.key === 'Enter') submit(); });
  }
  function composerCardHtml(host, url) {
    return ''
      + '<div class="spread" style="margin-bottom:12px">'
        + '<div class="row gap-s"><span class="plat-ico plat-yt">▶</span><div><div class="row gap-s"><strong style="font-size:13.5px">' + host + '</strong><span class="badge running"><span class="d"></span>转录中</span></div><div class="muted mono-sm" style="margin-top:2px">' + url.slice(0, 64) + (url.length > 64 ? '…' : '') + '</div></div></div>'
        + '<span class="mono-sm muted" data-pct>0%</span>'
      + '</div>'
      + '<div class="pipeline-rail" data-live data-start="0" data-end="100" data-dur="30">'
        + nodeHtml() + '</div>';
  }
  function nodeHtml() {
    var h = '';
    for (var i = 0; i < 6; i++) {
      h += '<div class="pr-node"><div class="pr-dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5"/></svg></div><div class="pr-label">' + NODE_LABELS[i] + '</div></div>';
      if (i < 5) h += '<div class="pr-link"></div>';
    }
    return h;
  }
  function runOneRail(rail) {
    var start = 0, end = 100, dur = 30000, t0 = null;
    function tick(ts) {
      if (t0 === null) t0 = ts;
      var k = Math.min(1, (ts - t0) / dur);
      renderRail(rail, start + (end - start) * k);
      if (k < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  /* ---------- 启动 ---------- */
  window.addEventListener('DOMContentLoaded', function () {
    reveal();
    livePipeline();
    initHistory();
    initProviders();
    initComposer();
  });
})();
