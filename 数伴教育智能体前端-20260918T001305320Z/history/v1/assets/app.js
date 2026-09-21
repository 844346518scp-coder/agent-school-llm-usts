/* SECTION: app-core
   数伴前端演示 · 交互逻辑。
   数据保存在当前浏览器 localStorage，不连接后端；
   智能体回复为固定示例，页面明确标注未接入真实模型。 */
(function () {
  'use strict';

  var D = window.SHUBAN;
  var STORE_KEY = 'shuban-demo-v1';

  /* SECTION: utils */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function uid(prefix) {
    return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  }
  function formatDateTime(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return (d.getMonth() + 1) + '/' + d.getDate() + ' ' +
      String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }
  function todayISO() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function greetingDate() {
    return new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' });
  }

  /* SECTION: store */
  var store = {
    data: null,
    load: function () {
      var raw = null;
      try { raw = localStorage.getItem(STORE_KEY); } catch (e) { raw = null; }
      if (raw) {
        try {
          var parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object') { this.data = this.normalize(parsed); return; }
        } catch (e) { /* fall through to seed */ }
      }
      this.data = this.seed();
      this.save();
    },
    normalize: function (parsed) {
      return {
        session: parsed.session && parsed.session.userId ? parsed.session : null,
        remember: !!parsed.remember,
        conversations: Array.isArray(parsed.conversations) ? parsed.conversations : {},
        assignments: Array.isArray(parsed.assignments) ? parsed.assignments : D.seedAssignments(),
        submissions: parsed.submissions && typeof parsed.submissions === 'object' ? parsed.submissions : {}
      };
    },
    seed: function () {
      return {
        session: null,
        remember: false,
        conversations: {},
        assignments: D.seedAssignments(),
        submissions: {}
      };
    },
    save: function () {
      try { localStorage.setItem(STORE_KEY, JSON.stringify(this.data)); } catch (e) { /* storage unavailable */ }
    },
    reset: function () {
      this.data = this.seed();
      this.save();
    }
  };

  /* SECTION: state */
  var state = {
    user: null,
    page: 'dashboard',
    records: [],
    assignments: [],
    initialQuestion: '',
    selectedId: '',
    createRequested: false,
    mobileNav: false,
    courseFilter: '全部章节',
    recordQuery: '',
    busy: false
  };

  function currentUser() { return state.user; }
  function isTeacher() { return !!(state.user && state.user.role === 'teacher'); }

  function recordsOf(userId) {
    var list = store.data.conversations[userId];
    return Array.isArray(list) ? list.slice() : [];
  }
  function persistRecords(userId, list) {
    store.data.conversations[userId] = list;
    store.save();
  }
  function submissionOf(assignmentId, userId) {
    var bag = store.data.submissions[assignmentId];
    return bag && typeof bag === 'object' ? bag[userId] || null : null;
  }
  function setSubmission(assignmentId, userId, answer) {
    if (!store.data.submissions[assignmentId]) store.data.submissions[assignmentId] = {};
    store.data.submissions[assignmentId][userId] = {
      student_name: state.user.name,
      answer: answer,
      created_at: new Date().toISOString()
    };
    store.save();
  }
  function submissionsOf(assignmentId) {
    var bag = store.data.submissions[assignmentId];
    if (!bag) return [];
    return Object.keys(bag).map(function (k) { return bag[k]; })
      .sort(function (a, b) { return new Date(b.created_at) - new Date(a.created_at); });
  }

  /* 组装带提交态与提交列表的作业视图（与后端 Assignment 字段对齐） */
  function assignmentsView() {
    var uidKey = state.user ? state.user.id : '';
    return store.data.assignments.map(function (a) {
      var mine = submissionOf(a.id, uidKey);
      return {
        id: a.id,
        title: a.title,
        content: a.content,
        topic: a.topic,
        due_date: a.due_date,
        created_at: a.created_at,
        submitted: !!mine,
        answer: mine ? mine.answer : '',
        submissions: submissionsOf(a.id)
      };
    }).sort(function (x, y) { return new Date(y.created_at) - new Date(x.created_at); });
  }

  /* SECTION: toast */
  var toastStack = null;
  function toast(message, kind) {
    if (!toastStack) toastStack = $('#toastStack');
    if (!toastStack) return;
    var icons = { success: '✓', error: '⚠', info: '✦' };
    var node = el('div', 'toast ' + (kind || 'success'));
    node.innerHTML = '<span class="t-icon" aria-hidden="true">' + (icons[kind || 'success'] || '✓') + '</span><span>' + esc(message) + '</span>';
    toastStack.appendChild(node);
    setTimeout(function () {
      node.classList.add('out');
      setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 240);
    }, 3200);
  }

  /* SECTION: dialog */
  var dialogBackdrop = null, dialogBody = null, dialogTitle = null, dialogLastFocus = null;
  function openDialog(title, bodyNode, opts) {
    dialogBackdrop = $('#dialogBackdrop');
    dialogBody = $('#dialogBody');
    dialogTitle = $('#dialogTitle');
    if (!dialogBackdrop || !dialogBody) return;
    dialogLastFocus = document.activeElement;
    dialogTitle.textContent = title;
    dialogBody.innerHTML = '';
    dialogBody.appendChild(bodyNode);
    dialogBackdrop.classList.remove('hidden');
    var wide = $('.dialog', dialogBackdrop);
    if (wide) wide.classList.toggle('wide', !!(opts && opts.wide));
    var focusTarget = $('input,textarea,select,button.primary-button', dialogBody);
    if (focusTarget) setTimeout(function () { focusTarget.focus(); }, 60);
  }
  function closeDialog() {
    if (dialogBackdrop) dialogBackdrop.classList.add('hidden');
    if (dialogBody) dialogBody.innerHTML = '';
    if (dialogLastFocus && dialogLastFocus.focus) { try { dialogLastFocus.focus(); } catch (e) {} }
  }

  /* SECTION: math
     轻量行内/块级公式渲染，覆盖演示回复中出现的 LaTeX 子集，不引入外部库。 */
  var SYMBOLS = {
    'ne': '≠', 'le': '≤', 'ge': '≥', 'pm': '±', 'times': '×', 'cdot': '·',
    'infty': '∞', 'pi': 'π', 'alpha': 'α', 'beta': 'β', 'theta': 'θ',
    'Delta': 'Δ', 'delta': 'δ', 'to': '→', 'rightarrow': '→', 'quad': ' ',
    'sin': 'sin', 'cos': 'cos', 'tan': 'tan', 'lim': 'lim', 'log': 'log'
  };
  var FUNCTIONS = ['sin', 'cos', 'tan', 'log', 'ln', 'lim', 'max', 'min'];

  function renderLatex(src) {
    var out = '';
    var i = 0;
    var n = src.length;
    while (i < n) {
      var ch = src[i];
      if (ch === '\\') {
        var m = /^\\([a-zA-Z]+)/.exec(src.slice(i));
        if (m) {
          var name = m[1];
          i += m[0].length;
          if (name === 'frac') {
            var num = readGroup(src, i); i = num.next;
            var den = readGroup(src, i); i = den.next;
            out += '<span class="frac"><span class="num">' + renderLatex(num.body) + '</span><span class="den">' + renderLatex(den.body) + '</span></span>';
          } else if (name === 'lim') {
            var sub = readSubscript(src, i); i = sub.next;
            out += '<span class="limsub"><span class="op">lim</span>' +
              (sub.body ? '<span>' + renderLatex(sub.body) + '</span>' : '') + '</span>';
          } else if (name === 'sqrt') {
            var body = readGroup(src, i); i = body.next;
            out += '<span class="mop">√</span><span class="sqrt">' + renderLatex(body.body) + '</span>';
          } else if (SYMBOLS[name] != null) {
            var sym = SYMBOLS[name];
            var isFn = FUNCTIONS.indexOf(name) >= 0;
            out += isFn ? '<span class="mfn">' + sym + '</span>' : '<span class="mop">' + sym + '</span>';
          } else {
            out += '<span class="mi">' + esc(name) + '</span>';
          }
          continue;
        }
        var sym2 = /^\\([^a-zA-Z])/.exec(src.slice(i));
        if (sym2) { i += sym2[0].length; out += '<span class="mop">' + esc(sym2[1]) + '</span>'; continue; }
        i++; continue;
      }
      if (ch === '^' || ch === '_') {
        i++;
        var sup = readGroup(src, i); i = sup.next;
        out += (ch === '^' ? '<sup>' : '<sub>') + renderLatex(sup.body) + (ch === '^' ? '</sup>' : '</sub>');
        continue;
      }
      if (ch === '{' || ch === '}') { i++; continue; }
      if (/[0-9]/.test(ch)) {
        var digits = /^[0-9.]+/.exec(src.slice(i))[0];
        i += digits.length;
        out += '<span class="mn">' + digits + '</span>';
        continue;
      }
      if (/[+\-=*/<>(),\[\]!|]/.test(ch)) { i++; out += '<span class="mop">' + esc(ch) + '</span>'; continue; }
      if (/\s/.test(ch)) { i++; out += ' '; continue; }
      i++;
      out += '<span class="mi">' + esc(ch) + '</span>';
    }
    return out;
  }

  function readGroup(src, i) {
    while (i < src.length && /\s/.test(src[i])) i++;
    if (src[i] === '{') {
      var depth = 0, start = i + 1;
      for (var j = i; j < src.length; j++) {
        if (src[j] === '{') depth++;
        else if (src[j] === '}') { depth--; if (depth === 0) return { body: src.slice(start, j), next: j + 1 }; }
      }
      return { body: src.slice(start), next: src.length };
    }
    var m = /^\\[a-zA-Z]+/.exec(src.slice(i));
    if (m) return { body: m[0], next: i + m[0].length };
    if (i < src.length) return { body: src[i], next: i + 1 };
    return { body: '', next: i };
  }

  function readSubscript(src, i) {
    while (i < src.length && /\s/.test(src[i])) i++;
    if (src[i] === '_') return readGroup(src, i + 1);
    return { body: '', next: i };
  }

  /* 单行渲染：先切出行内公式（原始 LaTeX），文本部分再转义，避免二次转义 */
  function renderLineWithMath(line) {
    var out = '';
    var re = /\$([^$]+)\$/g;
    var last = 0;
    var m;
    while ((m = re.exec(line)) !== null) {
      out += esc(line.slice(last, m.index));
      out += '<span class="math-inline">' + renderLatex(m[1]) + '</span>';
      last = m.index + m[0].length;
    }
    out += esc(line.slice(last));
    return out;
  }

  /* 把预设回复文本转成安全 HTML：先抽出 $$块$$，再逐行处理 $行内$、有序列表与标签 */
  function renderAnswer(text) {
    var blocks = [];
    var withBlocks = String(text).replace(/\$\$([\s\S]+?)\$\$/g, function (_, tex) {
      var idx = blocks.push('<span class="math-block"><span class="mrow">' + renderLatex(tex) + '</span></span>') - 1;
      return '\u0000B' + idx + '\u0000';
    });
    function restore(str) {
      return str.replace(/\u0000B(\d+)\u0000/g, function (_, idx) { return blocks[Number(idx)]; });
    }
    var html = '';
    var listBuffer = [];
    function flushList() {
      if (!listBuffer.length) return;
      html += '<ol>' + listBuffer.map(function (li) { return '<li>' + li + '</li>'; }).join('') + '</ol>';
      listBuffer = [];
    }
    withBlocks.split('\n').forEach(function (line) {
      var olItem = /^(\d+)\.\s+(.*)$/.exec(line.trim());
      if (olItem) { listBuffer.push(renderLineWithMath(olItem[2])); return; }
      flushList();
      if (!line.trim()) return;
      var tagMatch = /^【(.+)】$/.exec(line.trim());
      if (tagMatch) { html += '<span class="md-tag">' + esc(tagMatch[1]) + '</span>'; return; }
      html += '<p>' + restore(renderLineWithMath(line)) + '</p>';
    });
    flushList();
    return html;
  }

  window.SHUBAN_APP = {
    D: D, store: store, state: state, $: $, $$: $$, el: el, esc: esc, uid: uid,
    formatDateTime: formatDateTime, todayISO: todayISO, greetingDate: greetingDate,
    currentUser: currentUser, isTeacher: isTeacher,
    recordsOf: recordsOf, persistRecords: persistRecords,
    assignmentsView: assignmentsView, submissionsOf: submissionsOf, setSubmission: setSubmission,
    toast: toast, openDialog: openDialog, closeDialog: closeDialog, renderAnswer: renderAnswer
  };
})();
