/* SECTION: views
   数伴前端演示 · 页面视图与启动逻辑。
   文案与交互取自项目现有 Vue 页面，公式渲染在 app.js 中完成。 */
(function () {
  'use strict';

  var A = window.SHUBAN_APP;
  var D = A.D, store = A.store, state = A.state;
  var $ = A.$, $$ = A.$$, el = A.el, esc = A.esc, uid = A.uid;
  var toast = A.toast, openDialog = A.openDialog, closeDialog = A.closeDialog;

  /* SECTION: login-view */
  var loginRole = 'student';

  function paintLogin() {
    var teacher = loginRole === 'teacher';
    $('#loginView').classList.toggle('teacher-theme', teacher);
    $('#storyEyebrow').textContent = teacher ? '为每一次有效教学' : '你的高等数学学习伙伴';
    $('#storyTitle').innerHTML = teacher
      ? '看见每一步成长，<br>让教学<em>有据可依。</em>'
      : '每一步思考，<br>都有<em>回应。</em>';
    $('#storyDesc').textContent = teacher
      ? '从课堂任务到学习反馈，连接教师的洞察与学生的进步。'
      : '把抽象变具体，把困惑变进步。和数伴一起，找到属于你的学习节奏。';
    $('#loginIcon').textContent = teacher ? '🏫' : '🎓';
    $('#loginTitle').innerHTML = (teacher ? '欢迎回来，老师' : '开启今天的学习') + '<span class="heading-dot">.</span>';
    $('#loginSubtitle').textContent = teacher
      ? '登录教学空间，陪伴每一次进步。'
      : '登录你的学习空间，从一个好问题开始。';
    $('#loginSubmitText').textContent = teacher ? '进入教学空间' : '进入学习空间';
    $('label[for=username]').textContent = teacher ? '教师账号' : '学生账号';
    $('#username').placeholder = teacher ? '请输入教师账号' : '请输入学生账号';
    $('#tabStudent').classList.toggle('active', !teacher);
    $('#tabStudent').setAttribute('aria-selected', String(!teacher));
    $('#tabTeacher').classList.toggle('active', teacher);
    $('#tabTeacher').setAttribute('aria-selected', String(teacher));
    $('#demoUser').textContent = teacher ? 'teacher' : 'student';
    $('#demoPass').textContent = teacher ? 'Teacher123!' : 'Student123!';
    $('#loginError').classList.add('hidden');
  }

  function switchRole(role) {
    if (loginRole === role) return;
    loginRole = role;
    $('#username').value = '';
    $('#password').value = '';
    $('#remember').checked = false;
    $('#rememberNote').classList.add('hidden');
    paintLogin();
  }

  function doLogin(evt) {
    evt.preventDefault();
    var username = $('#username').value.trim();
    var password = $('#password').value;
    var errBox = $('#loginError');
    function fail(msg) {
      errBox.textContent = msg;
      errBox.classList.remove('hidden');
    }
    if (!username || !password) { fail('请填写账号与密码后重试。'); return; }
    var found = D.USERS.filter(function (u) { return u.username === username && u.password === password; })[0];
    if (!found) { fail('账号或密码不正确，可点击「填入演示账号」快速体验。'); return; }
    if (found.role !== loginRole) {
      fail('该账号属于' + (found.role === 'teacher' ? '教师' : '学生') + '身份，请切换到对应标签后登录。');
      return;
    }
    errBox.classList.add('hidden');
    var btn = $('#loginSubmit');
    btn.disabled = true;
    $('#loginSubmitText').textContent = '正在验证账号…';
    setTimeout(function () {
      btn.disabled = false;
      $('#loginSubmitText').textContent = loginRole === 'teacher' ? '进入教学空间' : '进入学习空间';
      store.data.session = { userId: found.id, at: Date.now() };
      store.data.remember = $('#remember').checked;
      store.save();
      enterApp(found);
    }, 420);
  }

  /* SECTION: shell */
  function navItems() { return A.isTeacher() ? D.NAV_TEACHER : D.NAV_STUDENT; }

  function enterApp(user) {
    state.user = user;
    state.page = 'dashboard';
    state.records = A.recordsOf(user.id);
    state.assignments = A.assignmentsView();
    state.initialQuestion = '';
    state.selectedId = '';
    state.createRequested = false;
    state.courseFilter = '全部章节';
    state.recordQuery = '';
    $('#loginView').classList.add('hidden');
    $('#appShell').classList.remove('hidden');
    $('#appShell').classList.toggle('teacher-theme', user.role === 'teacher');
    $('#workspaceLabel').textContent = user.role === 'teacher' ? '教师教学空间' : '学生学习空间';
    $('#navSectionLabel').textContent = user.role === 'teacher' ? '教学工作台' : '我的学习空间';
    $('#userName').textContent = user.name;
    $('#userRole').textContent = (user.role === 'teacher' ? '教师' : '学生') + ' · 演示账号';
    $('#userAvatar').textContent = user.avatar;
    paintNav();
    render();
    window.scrollTo(0, 0);
  }

  function paintNav() {
    var list = $('#navList');
    list.innerHTML = '';
    var pending = state.assignments.some(function (a) { return !a.submitted; });
    navItems().forEach(function (item) {
      var btn = el('button');
      if (item.id === state.page) btn.className = 'active';
      btn.type = 'button';
      btn.setAttribute('data-nav', item.id);
      var icon = el('span', 'nav-icon');
      icon.textContent = item.icon;
      icon.setAttribute('aria-hidden', 'true');
      btn.appendChild(icon);
      btn.appendChild(el('span', null, item.label));
      if (item.ai) btn.appendChild(el('span', 'nav-ai', 'AI'));
      if (item.dot && !A.isTeacher() && pending) btn.appendChild(el('span', 'nav-dot'));
      btn.addEventListener('click', function () { navigate(item.id); });
      list.appendChild(btn);
    });
  }

  function navigate(id) {
    state.page = id;
    closeMobileNav();
    if (id !== 'agent') { state.initialQuestion = ''; state.selectedId = ''; }
    if (id !== 'assignments') state.createRequested = false;
    paintNav();
    render();
    window.scrollTo(0, 0);
  }

  function ask(question) {
    state.initialQuestion = question;
    state.selectedId = '';
    navigate('agent');
  }

  function openRecord(id) {
    state.initialQuestion = '';
    state.selectedId = id;
    navigate('agent');
  }

  function refreshData() {
    state.records = A.recordsOf(state.user.id);
    state.assignments = A.assignmentsView();
  }

  function openMobileNav() {
    state.mobileNav = true;
    $('#sidebar').classList.add('is-open');
    $('#navBackdrop').classList.remove('hidden');
  }
  function closeMobileNav() {
    state.mobileNav = false;
    $('#sidebar').classList.remove('is-open');
    $('#navBackdrop').classList.add('hidden');
  }

  /* SECTION: render-root */
  function render() {
    var main = $('#mainContent');
    var item = navItems().filter(function (n) { return n.id === state.page; })[0];
    $('#crumbCurrent').textContent = item ? item.label : '工作台';
    main.innerHTML = '';
    var view = VIEWS[state.page];
    if (!view) view = VIEWS.dashboard;
    main.appendChild(view());
    var footer = el('footer', 'workspace-footer');
    footer.innerHTML = '<span>数伴 · 让每一步学习都有回应</span><span>MVP 0.1 <span class="tiny-dot"></span> 持续生长中</span>';
    main.appendChild(footer);
  }

  /* SECTION: shared-blocks */
  function pageHeading(eyebrow, title, subtitle, rightNode) {
    var wrap = el('div', 'page-heading');
    var left = el('div');
    left.appendChild(el('div', 'eyebrow', eyebrow));
    var h1 = el('h1');
    h1.innerHTML = title;
    left.appendChild(h1);
    if (subtitle) left.appendChild(el('p', null, subtitle));
    wrap.appendChild(left);
    if (rightNode) wrap.appendChild(rightNode);
    return wrap;
  }

  function panel(cls) { return el('section', 'panel' + (cls ? ' ' + cls : '')); }

  function sectionHeading(title, sub, rightNode) {
    var head = el('div', 'section-heading');
    var h3 = el('h3');
    h3.innerHTML = esc(title) + (sub ? ' <span class="section-sub">' + esc(sub) + '</span>' : '');
    head.appendChild(h3);
    if (rightNode) head.appendChild(rightNode);
    return head;
  }

  function statCard(iconCls, icon, label, value, unit, detail, actionLabel, onAction) {
    var card = el('div', 'stat-card');
    var badge = el('span', 'stat-icon ' + iconCls);
    badge.textContent = icon;
    badge.setAttribute('aria-hidden', 'true');
    card.appendChild(badge);
    var body = el('div');
    body.appendChild(el('span', null, label));
    var strong = el('strong');
    strong.appendChild(document.createTextNode(String(value)));
    if (unit) strong.appendChild(el('small', null, unit));
    body.appendChild(strong);
    card.appendChild(body);
    if (detail) card.appendChild(el('span', 'stat-detail', detail));
    if (actionLabel) {
      var btn = el('button', 'icon-button');
      btn.type = 'button';
      btn.setAttribute('aria-label', actionLabel);
      btn.title = actionLabel;
      btn.textContent = '↗';
      btn.addEventListener('click', onAction);
      card.appendChild(btn);
    }
    return card;
  }

  function activityChart(isoList, green) {
    var wrap = el('div', 'chart-wrap');
    var days = [];
    for (var i = 6; i >= 0; i--) {
      var d = new Date();
      d.setHours(0, 0, 0, 0);
      d.setDate(d.getDate() - i);
      days.push(d);
    }
    var counts = days.map(function (day) {
      var key = day.getFullYear() + '-' + String(day.getMonth() + 1).padStart(2, '0') + '-' + String(day.getDate()).padStart(2, '0');
      return isoList.filter(function (iso) { return String(iso).slice(0, 10) === key; }).length;
    });
    var max = Math.max.apply(null, counts.concat([1]));
    days.forEach(function (day, idx) {
      var col = el('div', 'chart-bar-col');
      col.appendChild(el('span', 'chart-bar-count', counts[idx] ? String(counts[idx]) : ''));
      var bar = el('div', 'chart-bar' + (green ? ' green' : '') + (counts[idx] ? '' : ' zero'));
      bar.style.height = counts[idx] ? Math.max(10, Math.round(counts[idx] / max * 62)) + 'px' : '3px';
      bar.title = (day.getMonth() + 1) + '/' + day.getDate() + '：' + counts[idx] + ' 次';
      col.appendChild(bar);
      col.appendChild(el('span', 'chart-bar-label', (day.getMonth() + 1) + '/' + day.getDate()));
      wrap.appendChild(col);
    });
    return wrap;
  }

  function gentleNote(icon, lines) {
    var box = el('div', 'gentle-note');
    var ic = el('span', 'note-icon');
    ic.textContent = icon;
    ic.setAttribute('aria-hidden', 'true');
    box.appendChild(ic);
    var p = el('p');
    p.innerHTML = lines;
    box.appendChild(p);
    return box;
  }

  /* SECTION: view-student-home */
  function studentHome() {
    var frag = document.createDocumentFragment();
    var todo = state.assignments.filter(function (a) { return !a.submitted; });
    var done = state.assignments.filter(function (a) { return a.submitted; }).length;
    var favs = state.records.filter(function (r) { return r.favorite; }).length;

    var chip = el('div', 'date-chip');
    chip.innerHTML = '🕒 ' + esc(A.greetingDate());
    frag.appendChild(pageHeading('A LITTLE PROGRESS, EVERY DAY',
      '你好，' + esc(state.user.name) + ' <span class="greeting-sun">☀</span>',
      '不必一下子弄懂所有，从今天的一小步开始。', chip));

    /* hero */
    var hero = el('section', 'hero-banner');
    var copy = el('div', 'hero-copy');
    copy.innerHTML =
      '<span class="hero-tag">✨ 你的专属学习伙伴</span>' +
      '<h2>有点难的高数，<br>我们一起<span>慢慢懂。</span></h2>' +
      '<p>从概念理解到解题思路，数伴陪你走好每一步。</p>';
    var heroBtn = el('button', 'primary-button', null);
    heroBtn.type = 'button';
    heroBtn.innerHTML = '和数伴聊一聊 <span aria-hidden="true">↗</span>';
    heroBtn.addEventListener('click', function () { navigate('agent'); });
    copy.appendChild(heroBtn);
    copy.appendChild(el('small', null, '当前为交互演示，真实 AI 能力即将接入'));
    hero.appendChild(copy);

    var art = el('div', 'hero-art');
    art.setAttribute('aria-hidden', 'true');
    art.innerHTML =
      '<div class="art-ring"></div><div class="floating-math">f′(x) = <em>2x</em></div>' +
      '<svg viewBox="0 0 280 190" role="img" aria-label="函数曲线示意">' +
      '<path d="M30 156H257M83 179V13" stroke="#afa0d0" stroke-width="1"/>' +
      '<path d="M33 51Q135 261 248 32" stroke="#9579d3" stroke-width="3" fill="none"/>' +
      '<path d="M138 150L255 62" stroke="#d7b381" stroke-width="1.5" stroke-dasharray="5 5"/>' +
      '<circle cx="209" cy="96" r="6" fill="white" stroke="#9579d3" stroke-width="3"/>' +
      '<text x="243" y="175" fill="#a194b6" font-size="13">x</text></svg>' +
      '<div class="art-caption">✨ 每一次「为什么」，都是进步的开始。</div><span class="art-star">✧</span>';
    hero.appendChild(art);
    frag.appendChild(hero);

    /* stats */
    var stats = el('div', 'stats-grid');
    stats.appendChild(statCard('lilac', '💬', '与数伴的探索', state.records.length, '次提问', '真实记录'));
    stats.appendChild(statCard('peach', '🔖', '我的复习收藏', favs, '条记录', null, '查看复习收藏', function () { navigate('favorites'); }));
    stats.appendChild(statCard('green', '✎', '已完成的作业', done, '/ ' + state.assignments.length + ' 份', '继续加油'));
    frag.appendChild(stats);

    /* grid */
    var grid = el('div', 'dashboard-grid');
    var mainCol = el('div', 'dashboard-main');

    var pathPanel = panel();
    var allLink = el('button', 'subtle-link');
    allLink.type = 'button';
    allLink.innerHTML = '全部章节 <span aria-hidden="true">→</span>';
    allLink.addEventListener('click', function () { navigate('courses'); });
    pathPanel.appendChild(sectionHeading('从这里，继续学习', 'LEARNING PATH', allLink));

    var courseGrid = el('div', 'course-grid');
    var courses = [
      { n: '01', pill: '基础篇', sym: 'lim', sub: 'x → a', title: '函数与极限', desc: '从无限接近，理解确定的值', foot: '概念入门 · 例题探索', q: '如何理解 sin(x)/x 在 x→0 时的极限？', mint: false },
      { n: '02', pill: '进阶篇', sym: 'f′(x)', sub: '', title: '导数与微分', desc: '看见变化，认识瞬时的力量', foot: '几何直觉 · 定义推导', q: '用定义求 x² 的导数', mint: true }
    ];
    courses.forEach(function (c) {
      var card = el('button', 'course-card' + (c.mint ? ' mint' : ''));
      card.type = 'button';
      card.innerHTML =
        '<div class="course-top"><span class="course-number">' + c.n + '</span><span class="small-pill">' + esc(c.pill) + '</span></div>' +
        '<div class="course-symbol">' + esc(c.sym) + (c.sub ? ' <small>' + esc(c.sub) + '</small>' : '') + '</div>' +
        '<h4>' + esc(c.title) + '</h4><p>' + esc(c.desc) + '</p>' +
        '<div class="course-bottom"><span>' + esc(c.foot) + '</span><span class="circle-arrow" aria-hidden="true">↗</span></div>';
      card.addEventListener('click', function () { ask(c.q); });
      courseGrid.appendChild(card);
    });
    pathPanel.appendChild(courseGrid);
    mainCol.appendChild(pathPanel);

    /* daily thought */
    var thought = panel('daily-thought');
    var tIcon = el('div', 'thought-icon');
    tIcon.textContent = 'Σ';
    tIcon.setAttribute('aria-hidden', 'true');
    thought.appendChild(tIcon);
    var tBody = el('div');
    tBody.innerHTML = '<span class="section-kicker">今日一问</span>' +
      '<h3>函数在一点有极限，就一定在这一点有定义吗？</h3>' +
      '<p>先写下你的直觉，再用一个例子验证它。</p>';
    thought.appendChild(tBody);
    var tBtn = el('button', 'outline-button');
    tBtn.type = 'button';
    tBtn.innerHTML = '想一想 <span aria-hidden="true">↗</span>';
    tBtn.addEventListener('click', function () { ask('函数在一点有极限，就一定在这一点有定义吗？'); });
    thought.appendChild(tBtn);
    mainCol.appendChild(thought);
    grid.appendChild(mainCol);

    /* side */
    var side = el('aside', 'dashboard-side');
    var todoPanel = panel();
    todoPanel.appendChild(sectionHeading('待办学习', null, el('span', 'count-badge', String(todo.length))));
    if (!todo.length) {
      todoPanel.appendChild(el('p', 'empty-small', '今天的作业都完成啦，去探索新问题吧。'));
    } else {
      todo.slice(0, 3).forEach(function (a) {
        var item = el('button', 'todo-item');
        item.type = 'button';
        item.innerHTML = '<span class="todo-circle"></span><div><strong>' + esc(a.title) + '</strong><small>' +
          esc(a.due_date) + ' 截止</small></div><span class="chev" aria-hidden="true">›</span>';
        item.addEventListener('click', function () { navigate('assignments'); });
        todoPanel.appendChild(item);
      });
    }
    var todoLink = el('button', 'subtle-link full-link');
    todoLink.type = 'button';
    todoLink.innerHTML = '查看我的作业 <span aria-hidden="true">→</span>';
    todoLink.addEventListener('click', function () { navigate('assignments'); });
    todoPanel.appendChild(todoLink);
    side.appendChild(todoPanel);

    var actPanel = panel('activity-panel');
    actPanel.appendChild(sectionHeading('学习的足迹', null, el('span', 'muted small', '近 7 天')));
    actPanel.appendChild(activityChart(state.records.map(function (r) { return r.created_at; }), false));
    var cap = el('p', 'chart-caption');
    cap.innerHTML = '每一个问题，都算数。<span>实际提问次数</span>';
    actPanel.appendChild(cap);
    side.appendChild(actPanel);

    side.appendChild(gentleNote('📖', '学习不是一场竞赛，<br>理解比速度更重要。'));
    grid.appendChild(side);
    frag.appendChild(grid);
    return frag;
  }

  /* SECTION: view-teacher-home */
  function teacherHome() {
    var frag = document.createDocumentFragment();
    var totalSubs = state.assignments.reduce(function (s, a) { return s + a.submissions.length; }, 0);

    var pubBtn = el('button', 'primary-button');
    pubBtn.type = 'button';
    pubBtn.innerHTML = '<span aria-hidden="true">＋</span> 发布新作业';
    pubBtn.setAttribute('data-primary-action', 'create-assignment');
    pubBtn.addEventListener('click', function () { state.createRequested = true; navigate('assignments'); });
    frag.appendChild(pageHeading('TEACH WITH INSIGHT',
      esc(state.user.name) + '，今天也一起启发思考。',
      '连接课堂、练习与反馈，让每一次教学都有迹可循。', pubBtn));

    var hero = el('section', 'hero-banner teacher-hero');
    var copy = el('div', 'hero-copy');
    copy.innerHTML =
      '<span class="hero-tag">✨ 数伴 · 教学助手</span>' +
      '<h2>把更多时间，<br>留给<span>真正的启发。</span></h2>' +
      '<p>整理教学思路，发布课堂任务，查看学生的作答。</p>';
    var heroBtn = el('button', 'primary-button');
    heroBtn.type = 'button';
    heroBtn.innerHTML = '打开教学助手 <span aria-hidden="true">↗</span>';
    heroBtn.addEventListener('click', function () { navigate('agent'); });
    copy.appendChild(heroBtn);
    copy.appendChild(el('small', null, '教学建议为预设示例，使用前请自行复核'));
    hero.appendChild(copy);
    var art = el('div', 'teacher-art');
    art.setAttribute('aria-hidden', 'true');
    art.innerHTML =
      '<div class="paper-card back"></div>' +
      '<div class="paper-card"><span>LESSON NOTES</span><h3>从「知道」<br>到「理解」</h3>' +
      '<div class="paper-line"></div><div class="paper-line short"></div>' +
      '<span class="paper-equation">Δy / Δx → f′(x)</span><span class="cap-icon">🎓</span></div>' +
      '<span class="art-star">✧</span>';
    hero.appendChild(art);
    frag.appendChild(hero);

    var stats = el('div', 'stats-grid');
    stats.appendChild(statCard('green', '👥', '演示班级学生', 1, '人', '预设账号'));
    stats.appendChild(statCard('lilac', '📋', '已发布作业', state.assignments.length, '份'));
    stats.appendChild(statCard('peach', '✓', '收到学生作答', totalSubs, '份', '实际提交'));
    frag.appendChild(stats);

    var grid = el('div', 'dashboard-grid');
    var mainCol = el('div', 'dashboard-main');
    var listPanel = panel();
    var allLink = el('button', 'subtle-link');
    allLink.type = 'button';
    allLink.innerHTML = '全部作业 <span aria-hidden="true">→</span>';
    allLink.addEventListener('click', function () { navigate('assignments'); });
    listPanel.appendChild(sectionHeading('最近发布的作业', null, allLink));

    if (!state.assignments.length) {
      listPanel.appendChild(el('p', 'empty-small', '还没有发布作业，点击右上角「发布新作业」开启教学闭环。'));
    } else {
      state.assignments.slice(0, 4).forEach(function (a) {
        var row = el('div', 'teacher-assignment');
        var badge = el('span', 'stat-icon green');
        badge.textContent = '📋';
        badge.setAttribute('aria-hidden', 'true');
        row.appendChild(badge);
        var body = el('div');
        body.innerHTML = '<h4>' + esc(a.title) + '</h4><p>' + esc(a.topic) + ' · 截止 ' + esc(a.due_date) + '</p>';
        row.appendChild(body);
        row.appendChild(el('span', 'small-pill', a.submissions.length + ' 份提交'));
        var go = el('button', 'icon-button');
        go.type = 'button';
        go.textContent = '↗';
        go.setAttribute('aria-label', '查看' + a.title);
        go.addEventListener('click', function () { navigate('assignments'); });
        row.appendChild(go);
        listPanel.appendChild(row);
      });
    }

    var remind = el('div', 'teaching-reminder');
    remind.innerHTML = '<h4>让反馈成为下一次教学的起点</h4>' +
      '<p>当前演示班级仅包含预设学生账号。真实班级导入、知识点掌握度与反馈复核将在后续版本接入。</p>';
    var remindLink = el('button', 'subtle-link');
    remindLink.type = 'button';
    remindLink.innerHTML = '查看演示班级 <span aria-hidden="true">→</span>';
    remindLink.addEventListener('click', function () { navigate('students'); });
    remind.appendChild(remindLink);
    listPanel.appendChild(remind);
    mainCol.appendChild(listPanel);
    grid.appendChild(mainCol);

    var side = el('aside', 'dashboard-side');
    var actPanel = panel('activity-panel');
    actPanel.appendChild(sectionHeading('我的教学探索', null, el('span', 'muted small', '近 7 天')));
    actPanel.appendChild(activityChart(state.records.map(function (r) { return r.created_at; }), true));
    actPanel.appendChild(el('p', 'chart-caption', '与教学助手的实际对话次数'));
    side.appendChild(actPanel);
    side.appendChild(gentleNote('✨', '一个好的问题，<br>往往比答案更有力量。'));
    grid.appendChild(side);
    frag.appendChild(grid);
    return frag;
  }

  /* SECTION: view-agent */
  function agentView() {
    var frag = document.createDocumentFragment();
    var teacher = A.isTeacher();
    frag.appendChild(pageHeading('THINK TOGETHER',
      teacher ? '教学灵感，从对话开始' : '把困惑说出来，一起想明白',
      '数伴智能体 · 你的高数' + (teacher ? '教学' : '学习') + '伙伴',
      (function () {
        var pill = el('span', 'status-pill');
        pill.innerHTML = '<span class="tiny-dot"></span> 演示模式';
        return pill;
      })()));

    var layout = el('div', 'agent-layout');
    var chat = panel('chat-panel');

    var header = el('header', 'chat-header');
    var av = el('div', 'agent-avatar');
    av.textContent = '✦';
    av.setAttribute('aria-hidden', 'true');
    header.appendChild(av);
    var hInfo = el('div');
    hInfo.innerHTML = '<strong>数伴 AI</strong><small>耐心听你说，陪你一步步探索</small>';
    header.appendChild(hInfo);
    var newBtn = el('button', 'subtle-link');
    newBtn.type = 'button';
    newBtn.innerHTML = '<span aria-hidden="true">＋</span> 新问题';
    newBtn.addEventListener('click', function () {
      state.selectedId = '';
      state.initialQuestion = '';
      render();
    });
    header.appendChild(newBtn);
    chat.appendChild(header);

    var body = el('div', 'chat-body');
    body.setAttribute('aria-live', 'polite');
    var active = state.selectedId
      ? state.records.filter(function (r) { return r.id === state.selectedId; })[0] || null
      : null;

    if (!active) {
      var welcome = el('div', 'chat-welcome');
      var sym = el('div', 'welcome-symbol');
      sym.textContent = '✦';
      sym.setAttribute('aria-hidden', 'true');
      welcome.appendChild(sym);
      welcome.appendChild(el('h2', null, '你好，' + state.user.name + ' 👋'));
      var wIntro = el('p');
      wIntro.innerHTML = '不用急着得到答案。<br>我们可以先从你最想理解的那一步开始。';
      welcome.appendChild(wIntro);
      var prompts = el('div', 'prompt-list');
      (teacher ? D.PROMPTS_TEACHER : D.PROMPTS_STUDENT).forEach(function (p) {
        var b = el('button');
        b.type = 'button';
        b.innerHTML = '<span class="p-icon" aria-hidden="true">' + esc(p.icon) + '</span><span>' + esc(p.text) + '</span><span class="p-go" aria-hidden="true">↑</span>';
        b.addEventListener('click', function () {
          state.initialQuestion = p.text;
          render();
          var ta = $('#agentInput');
          if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
        });
        prompts.appendChild(b);
      });
      welcome.appendChild(prompts);
      body.appendChild(welcome);
    } else {
      var userMsg = el('div', 'user-message');
      userMsg.innerHTML = '<span class="message-label">' + esc(state.user.name) + ' · ' + esc(A.formatDateTime(active.created_at)) + '</span>' +
        '<div>' + esc(active.question) + '</div>';
      body.appendChild(userMsg);

      var agentMsg = el('div', 'agent-message');
      var av2 = el('div', 'agent-avatar');
      av2.textContent = '✦';
      av2.setAttribute('aria-hidden', 'true');
      agentMsg.appendChild(av2);
      var content = el('div', 'answer-content');
      content.innerHTML = '<div class="message-label">数伴 AI <span class="demo-label">预设演示回复</span></div>';
      var mdBody = el('div', 'md-body');
      mdBody.innerHTML = A.renderAnswer(active.answer);
      content.appendChild(mdBody);
      var favBtn = el('button', 'subtle-link save-answer' + (active.favorite ? ' saved' : ''));
      favBtn.type = 'button';
      favBtn.innerHTML = (active.favorite ? '✓ 已收藏到复习本' : '🔖 收藏到复习本');
      favBtn.addEventListener('click', function () {
        toggleFavorite(active.id);
      });
      content.appendChild(favBtn);
      agentMsg.appendChild(content);
      body.appendChild(agentMsg);
    }
    chat.appendChild(body);

    /* compose */
    var compose = el('form', 'chat-compose');
    var topicRow = el('div', 'compose-topic');
    topicRow.innerHTML = '<span class="tiny-dot"></span><label for="topicSelect">本次主题</label>';
    var select = el('select', null);
    select.id = 'topicSelect';
    ['函数与极限', '导数与微分', '费曼练习'].concat(teacher ? ['教学设计'] : []).forEach(function (t) {
      var opt = el('option', null, t);
      opt.value = t;
      select.appendChild(opt);
    });
    select.value = guessTopic(state.initialQuestion, teacher);
    topicRow.appendChild(select);
    var charCount = el('span', 'char-count', '0/2000');
    topicRow.appendChild(charCount);
    compose.appendChild(topicRow);

    var ta = el('textarea');
    ta.id = 'agentInput';
    ta.maxLength = 2000;
    ta.rows = 3;
    ta.setAttribute('aria-label', teacher ? '向教学助手提问' : '向数伴提问');
    ta.placeholder = '写下你的问题或思考，让我们一起探索…';
    ta.value = state.initialQuestion || '';
    charCount.textContent = ta.value.length + '/2000';
    ta.addEventListener('input', function () { charCount.textContent = ta.value.length + '/2000'; updateSendState(); });
    ta.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submitQuestion(); }
    });
    compose.appendChild(ta);

    var bottom = el('div', 'compose-bottom');
    bottom.appendChild(el('span', null, 'Enter 发送 · Shift + Enter 换行'));
    var sendBtn = el('button', 'send-button');
    sendBtn.type = 'submit';
    sendBtn.textContent = '↑';
    sendBtn.setAttribute('aria-label', '发送问题');
    sendBtn.setAttribute('data-primary-action', 'ask-agent');
    bottom.appendChild(sendBtn);
    compose.appendChild(bottom);

    var errLine = el('p', 'form-error hidden');
    errLine.setAttribute('role', 'alert');
    compose.appendChild(errLine);

    compose.addEventListener('submit', function (e) { e.preventDefault(); submitQuestion(); });
    chat.appendChild(compose);
    chat.appendChild(el('p', 'chat-disclaimer', '当前回复为固定示例，未接入真实模型；请结合教材核对。'));
    layout.appendChild(chat);

    function updateSendState() {
      sendBtn.disabled = state.busy || !ta.value.trim();
    }

    function submitQuestion() {
      var text = ta.value.trim();
      if (!text) {
        errLine.textContent = '请先输入问题，或点击左侧示例问题。';
        errLine.classList.remove('hidden');
        return;
      }
      errLine.classList.add('hidden');
      state.busy = true;
      updateSendState();
      var topic = select.value;
      var thinking = el('div', 'thinking');
      thinking.innerHTML = '正在读取演示反馈<span>···</span>';
      body.appendChild(thinking);
      body.scrollTop = body.scrollHeight;
      setTimeout(function () {
        if (thinking.parentNode) thinking.parentNode.removeChild(thinking);
        var record = {
          id: uid('c'),
          question: text,
          answer: demoReply(text, topic, state.user.role),
          topic: topic,
          favorite: false,
          created_at: new Date().toISOString(),
          mode: 'demo'
        };
        var list = A.recordsOf(state.user.id);
        list.unshift(record);
        A.persistRecords(state.user.id, list);
        state.busy = false;
        state.initialQuestion = '';
        state.selectedId = record.id;
        refreshData();
        paintNav();
        render();
        toast('已保存这次提问，可在「学习记录」中查看。', 'success');
      }, 520);
    }

    /* aside */
    var aside = el('aside', 'agent-aside');
    var tip = panel('side-tip');
    tip.innerHTML = '<div class="section-kicker">💡 好问题的小提示</div><h3>让思考更进一步</h3>' +
      '<p>告诉数伴你正在学什么、尝试过什么，以及具体卡在哪里。</p>' +
      '<div class="quote">“我知道导数的公式，<br>但为什么要用极限定义它？”</div>';
    aside.appendChild(tip);

    var recentPanel = panel();
    recentPanel.appendChild(sectionHeading('最近的问题', null, (function () {
      var s = el('span'); s.textContent = '💬'; return s;
    })()));
    if (!state.records.length) {
      recentPanel.appendChild(el('p', 'empty-small', '还没有提问，从左边开始吧。'));
    } else {
      state.records.slice(0, 5).forEach(function (r) {
        var b = el('button', 'recent-question');
        b.type = 'button';
        b.innerHTML = '<span>' + esc(r.question) + '</span><small>' + esc(A.formatDateTime(r.created_at)) + '</small>';
        b.addEventListener('click', function () { openRecord(r.id); });
        recentPanel.appendChild(b);
      });
    }
    aside.appendChild(recentPanel);

    var coming = el('div', 'coming-note');
    coming.innerHTML = '<span>接下来，我们还会…</span><p>拍照识题 · 课程引用 · 分层提示</p><small>这些能力正在规划中</small>';
    aside.appendChild(coming);
    layout.appendChild(aside);
    frag.appendChild(layout);

    setTimeout(function () { updateSendState(); if (!active && ta) ta.focus(); }, 30);
    return frag;
  }

  function guessTopic(question, teacher) {
    if (teacher) return '教学设计';
    var q = String(question || '');
    if (q.indexOf('费曼') >= 0) return '费曼练习';
    if (q.indexOf('导数') >= 0 || q.indexOf('微分') >= 0) return '导数与微分';
    return '函数与极限';
  }

  /* 与 backend demo_reply 相同的分支顺序 */
  function demoReply(question, topic, role) {
    if (role === 'teacher') return D.REPLY_TEACHER;
    if (topic === '费曼练习') return D.REPLY_FEYNMAN;
    var q = String(question).toLowerCase();
    if (q.indexOf('sin') >= 0 && (question.indexOf('极限') >= 0 || q.indexOf('lim') >= 0)) return D.REPLY_SIN_LIMIT;
    if (question.indexOf('x^2') >= 0 || question.indexOf('x²') >= 0 || question.indexOf('导数') >= 0) return D.REPLY_DERIVATIVE;
    return D.REPLY_FALLBACK;
  }

  function toggleFavorite(id) {
    var list = A.recordsOf(state.user.id);
    var hit = list.filter(function (r) { return r.id === id; })[0];
    if (!hit) return;
    hit.favorite = !hit.favorite;
    A.persistRecords(state.user.id, list);
    refreshData();
    render();
    toast(hit.favorite ? '已收藏到复习本。' : '已从复习本移除。', hit.favorite ? 'success' : 'info');
  }

  /* SECTION: view-courses */
  function coursesView() {
    var frag = document.createDocumentFragment();
    frag.appendChild(pageHeading('LEARN AT YOUR OWN PACE', '循着好奇，走进高数',
      '当前提供概念入口与预设例题，完整课程知识库将在后续接入。',
      (function () { var s = el('span', 'heading-illustration'); s.textContent = '📖'; return s; })()));

    var tabs = el('div', 'filter-tabs');
    ['全部章节', '函数与极限', '导数与微分'].forEach(function (tab) {
      var b = el('button', state.courseFilter === tab ? 'active' : '', tab);
      b.type = 'button';
      b.addEventListener('click', function () { state.courseFilter = tab; render(); });
      tabs.appendChild(b);
    });
    frag.appendChild(tabs);

    var grid = el('div', 'lesson-grid');
    var shown = D.LESSONS.filter(function (l) {
      return state.courseFilter === '全部章节' || l.chapter === state.courseFilter;
    });
    shown.forEach(function (lesson) {
      var card = el('article', 'panel lesson-card');
      var art = el('div', 'lesson-art');
      art.innerHTML = '<span>' + esc(lesson.formula) + '</span><small>' + esc(lesson.number) + '</small>';
      card.appendChild(art);
      var copy = el('div', 'lesson-copy');
      copy.innerHTML = '<div class="section-kicker">' + esc(lesson.chapter) + ' <span>· ' + esc(lesson.label) + '</span></div>' +
        '<h3>' + esc(lesson.title) + '</h3><p>' + esc(lesson.text) + '</p>';
      var go = el('button', 'subtle-link');
      go.type = 'button';
      go.innerHTML = '带着问题去探索 <span aria-hidden="true">↗</span>';
      go.addEventListener('click', function () { ask(lesson.prompt); });
      copy.appendChild(go);
      card.appendChild(copy);
      grid.appendChild(card);
    });
    if (!shown.length) {
      var empty = panel('empty-state');
      empty.innerHTML = '<span class="empty-icon">📖</span><h3>该章节还没有内容</h3><p>试试切换到「全部章节」。</p>';
      grid.appendChild(empty);
    }
    frag.appendChild(grid);

    var note = el('div', 'course-note');
    note.innerHTML = '<span class="note-icon" aria-hidden="true">💡</span>' +
      '<p>先理解概念，再练习迁移。数伴不会仅凭一次对话就认定你已经掌握。</p>' +
      '<span class="sigma" aria-hidden="true">Σ</span>';
    frag.appendChild(note);
    return frag;
  }

  /* SECTION: view-assignments */
  function assignmentsView() {
    var frag = document.createDocumentFragment();
    var teacher = A.isTeacher();
    var right = null;
    if (teacher) {
      right = el('button', 'primary-button');
      right.type = 'button';
      right.innerHTML = '<span aria-hidden="true">＋</span> 发布新作业';
      right.setAttribute('data-primary-action', 'create-assignment');
      right.addEventListener('click', function () { openCreateDialog(); });
    }
    frag.appendChild(pageHeading('PRACTICE & REFLECTION',
      teacher ? '让课堂的思考继续' : '把理解，写进练习里',
      teacher ? '发布给演示班级的作业，并查看学生的实际提交。' : '完成老师的课堂任务，留下你的解题过程。',
      right));

    var grid = el('div', 'assignment-grid');
    if (!state.assignments.length) {
      var empty = panel('empty-state');
      empty.innerHTML = '<span class="empty-icon">📋</span><h3>还没有作业</h3><p>' +
        esc(teacher ? '发布第一份练习，开启教学闭环。' : '老师发布后，作业会出现在这里。') + '</p>';
      grid.appendChild(empty);
    } else {
      state.assignments.forEach(function (a) { grid.appendChild(assignmentCard(a, teacher)); });
    }
    frag.appendChild(grid);
    if (state.createRequested && teacher) { state.createRequested = false; setTimeout(openCreateDialog, 60); }
    return frag;
  }

  function assignmentCard(a, teacher) {
    var card = el('article', 'panel assignment-card');
    var head = el('div', 'section-heading');
    var badge = el('span', 'stat-icon ' + (a.submitted ? 'green' : 'lilac'));
    badge.textContent = a.submitted ? '✓' : '📋';
    badge.setAttribute('aria-hidden', 'true');
    head.appendChild(badge);
    var pillText, pillCls;
    if (teacher) {
      pillText = a.submissions.length + ' 份提交';
      pillCls = a.submissions.length ? 'success' : 'neutral';
    } else if (a.submitted) {
      pillText = '已提交';
      pillCls = 'success';
    } else if (a.due_date < A.todayISO()) {
      pillText = '已截止';
      pillCls = 'neutral';
    } else {
      pillText = '待完成';
      pillCls = 'warn';
    }
    var pill = el('span', 'small-pill ' + pillCls, pillText);
    head.appendChild(pill);
    card.appendChild(head);
    card.appendChild(el('span', 'section-kicker', a.topic));
    card.appendChild(el('h3', null, a.title));
    card.appendChild(el('p', 'assignment-preview', a.content));

    var foot = el('div', 'assignment-footer');
    foot.innerHTML = '<span>📅 ' + esc(a.due_date) + '</span>';
    var btn = el('button', 'subtle-link');
    btn.type = 'button';
    btn.innerHTML = esc(teacher ? '查看作答' : (a.submitted ? '查看 / 修改' : '开始作答')) + ' <span aria-hidden="true">→</span>';
    btn.addEventListener('click', function () { openAssignmentDialog(a); });
    foot.appendChild(btn);
    card.appendChild(foot);
    return card;
  }

  function openCreateDialog() {
    var form = el('form', 'dialog-form');
    form.innerHTML =
      '<p class="muted">发布至「高等数学 · 演示班级」，预设学生可立即查看。</p>' +
      '<label>作业标题<input type="text" id="fTitle" maxlength="100" placeholder="例如：导数定义与几何意义" required></label>' +
      '<div class="form-row"><label>所属章节<select id="fTopic"><option>函数与极限</option><option>导数与微分</option></select></label>' +
      '<label>截止日期<input type="date" id="fDue" required></label></div>' +
      '<label>题目与要求<textarea id="fContent" rows="5" maxlength="3000" placeholder="写下题目，鼓励学生展示思考过程。" required></textarea></label>';
    var err = el('p', 'form-error hidden');
    err.setAttribute('role', 'alert');
    form.appendChild(err);
    var actions = el('div', 'dialog-actions');
    var cancel = el('button', 'outline-button', '取消');
    cancel.type = 'button';
    cancel.addEventListener('click', closeDialog);
    var ok = el('button', 'primary-button');
    ok.type = 'submit';
    ok.innerHTML = '<span aria-hidden="true">➤</span> 确认发布';
    actions.appendChild(cancel);
    actions.appendChild(ok);
    form.appendChild(actions);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var title = $('#fTitle', form).value.trim();
      var content = $('#fContent', form).value.trim();
      var due = $('#fDue', form).value;
      if (!title || !content || !due) {
        err.textContent = '请完整填写标题、题目要求与截止日期。';
        err.classList.remove('hidden');
        return;
      }
      if (due < A.todayISO()) {
        err.textContent = '截止日期不能早于今天。';
        err.classList.remove('hidden');
        return;
      }
      store.data.assignments.push({
        id: uid('a'),
        title: title,
        content: content,
        topic: $('#fTopic', form).value,
        due_date: due,
        created_at: new Date().toISOString(),
        submissions: []
      });
      store.save();
      closeDialog();
      refreshData();
      paintNav();
      render();
      toast('作业已发布，学生端现在可以查看。', 'success');
    });
    openDialog('发布新作业', form, { wide: false });
    setTimeout(function () {
      var due = $('#fDue', form);
      if (due) {
        var d = new Date();
        d.setDate(d.getDate() + 7);
        due.min = A.todayISO();
        due.value = D.isoDate(d);
      }
    }, 40);
  }

  function openAssignmentDialog(a) {
    var wrap = el('div');
    wrap.appendChild(el('span', 'small-pill', a.topic + ' · ' + a.due_date + ' 截止'));
    var full = el('div', 'assignment-full', a.content);
    wrap.appendChild(full);

    if (A.isTeacher()) {
      var subHead = el('h4', null, '学生作答（' + a.submissions.length + '）');
      subHead.style.marginTop = '20px';
      wrap.appendChild(subHead);
      if (!a.submissions.length) {
        wrap.appendChild(el('p', 'empty-small', '暂未收到提交。可退出后使用学生账号体验作答流程。'));
      } else {
        a.submissions.forEach(function (s) {
          var card = el('div', 'submission-card');
          card.innerHTML = '<strong><span class="tiny-dot"></span> ' + esc(s.student_name) + '</strong>' +
            '<p>' + esc(s.answer) + '</p><small class="muted">' + esc(A.formatDateTime(s.created_at)) + '</small>';
          wrap.appendChild(card);
        });
      }
      var note = el('p', 'muted small');
      note.style.marginTop = '14px';
      note.textContent = '本版本只记录提交，不自动评分，也不推断知识点掌握程度。';
      wrap.appendChild(note);
    } else {
      var expired = a.due_date < A.todayISO();
      var form = el('form', 'dialog-form');
      var label = el('label', null, '我的作答');
      var ta = el('textarea');
      ta.rows = 7;
      ta.maxLength = 5000;
      ta.placeholder = '写出你的答案与推理步骤…';
      ta.value = a.answer || '';
      if (expired) ta.disabled = true;
      label.appendChild(ta);
      form.appendChild(label);
      form.appendChild(el('p', 'muted small', expired
        ? '作业已过截止日期，作答已锁定，仍可查看此前提交的内容。'
        : '提交后仍可在截止前修改；本版本不自动评分。'));
      var err = el('p', 'form-error hidden');
      err.setAttribute('role', 'alert');
      form.appendChild(err);
      var actions = el('div', 'dialog-actions');
      var cancel = el('button', 'outline-button', '关闭');
      cancel.type = 'button';
      cancel.addEventListener('click', closeDialog);
      var ok = el('button', 'primary-button');
      ok.type = 'submit';
      ok.textContent = a.submitted ? '保存修改' : '提交作答';
      ok.setAttribute('data-primary-action', 'submit-answer');
      ok.disabled = expired;
      if (expired) ok.textContent = '作业已截止';
      actions.appendChild(cancel);
      actions.appendChild(ok);
      form.appendChild(actions);
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var text = ta.value.trim();
        if (!text) {
          err.textContent = '请先写下你的作答内容。';
          err.classList.remove('hidden');
          return;
        }
        A.setSubmission(a.id, state.user.id, text);
        closeDialog();
        refreshData();
        paintNav();
        render();
        toast('作答已保存，老师可以查看你的思考。', 'success');
      });
      wrap.appendChild(form);
    }
    openDialog(a.title, wrap, { wide: true });
  }

  /* SECTION: view-records */
  function recordsView(favoritesOnly) {
    var frag = document.createDocumentFragment();
    var list = state.records.filter(function (r) { return !favoritesOnly || r.favorite; });
    var q = state.recordQuery.trim().toLowerCase();
    if (q) {
      list = list.filter(function (r) {
        return r.question.toLowerCase().indexOf(q) >= 0 || r.answer.toLowerCase().indexOf(q) >= 0;
      });
    }
    frag.appendChild(pageHeading(favoritesOnly ? 'KEEP FOR REVIEW' : 'YOUR LEARNING TRACE',
      favoritesOnly ? '值得再看一遍的思考' : '每一次提问，都留在这里',
      favoritesOnly
        ? '收藏是你在对话中主动标记的记录，不自动判定为错题。'
        : '这里保存你与数伴的真实对话，按时间倒序排列。'));

    var toolbar = el('div', 'records-toolbar');
    var search = el('div', 'search-box');
    search.innerHTML = '<span class="s-icon" aria-hidden="true">🔍</span>';
    var input = el('input');
    input.type = 'search';
    input.placeholder = favoritesOnly ? '搜索收藏的问题或讲解…' : '搜索你的问题或讲解…';
    input.value = state.recordQuery;
    input.setAttribute('aria-label', '搜索记录');
    input.addEventListener('input', function () {
      state.recordQuery = input.value;
      var box = $('#recordsList');
      if (box && box.parentNode) {
        var next = buildList();
        box.parentNode.replaceChild(next, box);
        var q2 = input.value.trim().toLowerCase();
        var n = state.records.filter(function (r) {
          if (favoritesOnly && !r.favorite) return false;
          if (!q2) return true;
          return r.question.toLowerCase().indexOf(q2) >= 0 || r.answer.toLowerCase().indexOf(q2) >= 0;
        }).length;
        count.textContent = n + ' 条记录';
      }
    });
    search.appendChild(input);
    toolbar.appendChild(search);
    var count = el('span', 'small-pill neutral', list.length + ' 条记录');
    toolbar.appendChild(count);
    var clearBtn = el('button', 'outline-button', '清空搜索');
    clearBtn.type = 'button';
    clearBtn.addEventListener('click', function () { state.recordQuery = ''; render(); });
    if (state.recordQuery) toolbar.appendChild(clearBtn);
    frag.appendChild(toolbar);

    function buildList() {
      var q2 = state.recordQuery.trim().toLowerCase();
      var rows = state.records.filter(function (r) { return !favoritesOnly || r.favorite; });
      if (q2) {
        rows = rows.filter(function (r) {
          return r.question.toLowerCase().indexOf(q2) >= 0 || r.answer.toLowerCase().indexOf(q2) >= 0;
        });
      }
      var box = el('div', 'records-list');
      box.id = 'recordsList';
      if (!rows.length) {
        var empty = panel('empty-state');
        empty.innerHTML = '<span class="empty-icon">' + (favoritesOnly ? '🔖' : '🕘') + '</span><h3>' +
          (q2 ? '没有匹配的记录' : (favoritesOnly ? '复习收藏还是空的' : '还没有学习记录')) + '</h3><p>' +
          (q2 ? '换个关键词试试，或清空搜索查看全部。'
            : (favoritesOnly ? '在对话中点击「收藏到复习本」，重要的讲解就会出现在这里。' : '去数伴智能体提出第一个问题吧。')) + '</p>';
        if (!q2) {
          var go = el('button', 'primary-button');
          go.type = 'button';
          go.style.marginTop = '16px';
          go.innerHTML = '和数伴聊一聊 <span aria-hidden="true">↗</span>';
          go.addEventListener('click', function () { navigate('agent'); });
          empty.appendChild(go);
        }
        box.appendChild(empty);
        return box;
      }
      rows.forEach(function (r) {
        var card = el('div', 'record-card');
        var main = el('div', 'record-main');
        var top = el('div', 'record-top');
        top.appendChild(el('span', 'small-pill', r.topic));
        top.appendChild(el('span', 'small-pill neutral', '演示回复'));
        top.appendChild(el('span', 'muted small', A.formatDateTime(r.created_at)));
        main.appendChild(top);
        main.appendChild(el('h4', null, r.question));
        var preview = el('div', 'record-answer');
        preview.textContent = r.answer.replace(/\n+/g, ' ').replace(/【|】/g, '');
        main.appendChild(preview);
        card.appendChild(main);

        var actions = el('div', 'record-actions');
        var fav = el('button', 'icon-button fav-button' + (r.favorite ? ' active' : ''));
        fav.type = 'button';
        fav.textContent = r.favorite ? '★' : '☆';
        fav.setAttribute('aria-label', r.favorite ? '取消收藏' : '收藏到复习本');
        fav.title = r.favorite ? '取消收藏' : '收藏到复习本';
        fav.addEventListener('click', function () { toggleFavorite(r.id); });
        actions.appendChild(fav);
        var open = el('button', 'icon-button');
        open.type = 'button';
        open.textContent = '↗';
        open.setAttribute('aria-label', '查看完整对话');
        open.title = '查看完整对话';
        open.addEventListener('click', function () { openRecord(r.id); });
        actions.appendChild(open);
        card.appendChild(actions);
        box.appendChild(card);
      });
      return box;
    }
    frag.appendChild(buildList());
    return frag;
  }

  /* SECTION: view-students */
  function studentsView() {
    var frag = document.createDocumentFragment();
    var submittedCount = state.assignments.filter(function (a) { return a.submissions.length; }).length;
    var pill = el('span', 'status-pill', '1 位学生');
    frag.appendChild(pageHeading('GROW TOGETHER', '看见每一位同学',
      '高等数学 · 演示班级，当前只有一名预设学生。', pill));

    var p = panel();
    p.appendChild(sectionHeading('班级成员', null, el('span', 'muted small', '账号与作业数据')));
    var row = el('div', 'class-student');
    var av = el('span', 'user-avatar', '林');
    row.appendChild(av);
    var info = el('div');
    info.innerHTML = '<h3>林同学</h3><p class="muted">student · 学生演示账号</p>';
    row.appendChild(info);
    var stat = el('div');
    stat.innerHTML = '<strong>' + submittedCount + ' / ' + state.assignments.length + '</strong><p class="muted">已提交作业</p>';
    row.appendChild(stat);
    var go = el('button', 'outline-button');
    go.type = 'button';
    go.innerHTML = '查看作业 <span aria-hidden="true">↗</span>';
    go.addEventListener('click', function () { navigate('assignments'); });
    row.appendChild(go);
    p.appendChild(row);

    var remind = el('div', 'teaching-reminder');
    remind.innerHTML = '<h4>先观察，再判断</h4><p>本版仅记录作业提交，不推断知识点掌握程度。多班级管理、成员邀请、学情诊断和反馈复核尚未开放。</p>';
    p.appendChild(remind);
    frag.appendChild(p);
    return frag;
  }

  /* SECTION: views-map */
  var VIEWS = {
    dashboard: function () { return A.isTeacher() ? teacherHome() : studentHome(); },
    agent: agentView,
    courses: function () { return A.isTeacher() ? teacherHome() : coursesView(); },
    assignments: assignmentsView,
    favorites: function () { return recordsView(true); },
    records: function () { return recordsView(false); },
    students: function () { return A.isTeacher() ? studentsView() : studentHome(); }
  };

  /* SECTION: help-dialog */
  function openHelp() {
    var wrap = el('div', 'help-content');
    wrap.innerHTML =
      '<p>这是一个高数教学与学习的最小可行版本前端演示。</p>' +
      '<p><strong>已经可以体验：</strong></p><ul>' +
      '<li>学生 / 教师登录与身份校验，勾选「记住密码」后刷新仍保持登录</li>' +
      '<li>课程探索与章节筛选，点卡片即带着问题进入对话</li>' +
      '<li>演示问答、公式渲染、收藏与历史记录、按账号隔离</li>' +
      '<li>教师发布作业 → 学生提交作答 → 教师查看实际作答</li>' +
      '<li>近 7 天提问次数统计，只计算真实发生的提问</li></ul>' +
      '<p><strong>当前尚未接入：</strong></p><ul>' +
      '<li>真实 AI 模型、拍照识题、语音、课程检索（RAG）、自动评分与多班级管理</li></ul>' +
      '<p><span class="help-badge">数据说明</span>对话、作业与作答保存在当前浏览器，不连接后端；智能体回复为固定示例，页面会明确标注。</p>' +
      '<p><span class="help-badge">演示账号</span>学生 student / Student123!；教师 teacher / Teacher123!。账号切换请先退出登录。</p>';
    openDialog('欢迎体验数伴', wrap, { wide: false });
  }

  /* SECTION: boot */
  function logout() {
    store.data.session = null;
    store.data.remember = false;
    store.save();
    state.user = null;
    state.page = 'dashboard';
    state.records = [];
    state.assignments = [];
    state.initialQuestion = '';
    state.selectedId = '';
    state.createRequested = false;
    state.mobileNav = false;
    $('#appShell').classList.add('hidden');
    $('#sidebar').classList.remove('is-open');
    $('#navBackdrop').classList.add('hidden');
    $('#username').value = '';
    $('#password').value = '';
    $('#remember').checked = false;
    $('#rememberNote').classList.add('hidden');
    loginRole = 'student';
    paintLogin();
    $('#loginView').classList.remove('hidden');
    toast('已退出登录，本次会话已撤销。', 'info');
  }

  function bindEvents() {
    $('#tabStudent').addEventListener('click', function () { switchRole('student'); });
    $('#tabTeacher').addEventListener('click', function () { switchRole('teacher'); });
    $('#loginForm').addEventListener('submit', doLogin);
    $('#fillDemo').addEventListener('click', function () {
      $('#username').value = loginRole === 'teacher' ? 'teacher' : 'student';
      $('#password').value = loginRole === 'teacher' ? 'Teacher123!' : 'Student123!';
      $('#loginError').classList.add('hidden');
      $('#username').focus();
    });
    $('#togglePassword').addEventListener('click', function () {
      var input = $('#password');
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      this.textContent = show ? '🙈' : '👁';
      this.setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
    });
    $('#remember').addEventListener('change', function () {
      $('#rememberNote').classList.toggle('hidden', !this.checked);
    });
    $('#openNav').addEventListener('click', openMobileNav);
    $('#closeNav').addEventListener('click', closeMobileNav);
    $('#navBackdrop').addEventListener('click', closeMobileNav);
    $('#logoutBtn').addEventListener('click', logout);
    $('#openHelp').addEventListener('click', openHelp);
    $('#dialogClose').addEventListener('click', closeDialog);
    $('#dialogBackdrop').addEventListener('click', function (e) {
      if (e.target === this) closeDialog();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        if (!$('#dialogBackdrop').classList.contains('hidden')) closeDialog();
        else if (state.mobileNav) closeMobileNav();
      }
    });
  }

  function boot() {
    store.load();
    bindEvents();
    paintLogin();
    var session = store.data.session;
    var resumed = null;
    if (session && session.userId) {
      resumed = D.USERS.filter(function (u) { return u.id === session.userId; })[0] || null;
      var maxAge = store.data.remember ? 7 * 24 * 3600 * 1000 : 8 * 3600 * 1000;
      if (resumed && Date.now() - Number(session.at || 0) > maxAge) {
        store.data.session = null;
        store.save();
        resumed = null;
      }
    }
    $('#bootScreen').classList.add('hidden');
    if (resumed) {
      loginRole = resumed.role;
      enterApp(resumed);
    } else {
      $('#loginView').classList.remove('hidden');
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
