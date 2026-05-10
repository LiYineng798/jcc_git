(async function () {
  const root = document.querySelector('#adminApp');
  const dialogRoot = document.querySelector('#adminDialogRoot');
  const elements = {
    themeToggle: document.querySelector('#themeToggle'),
    themeIcon: document.querySelector('#themeIcon'),
    themeText: document.querySelector('#themeText'),
    adminIdentity: document.querySelector('#adminIdentity'),
    heroTodayUv: document.querySelector('#heroTodayUv'),
  };
  if (!root) return;

  const state = {
    me: null,
    csrfToken: '',
    stats: { last_7_days_uv: [] },
    reports: [],
    lineups: [],
    users: [],
    logs: [],
    lineupQuery: '',
    userQuery: '',
    passwordUser: null,
    passwordError: '',
    notice: '',
  };
  const statusText = {
    pending: '待处理',
    resolved: '已处理',
    dismissed: '已驳回',
    normal: '正常',
    hidden: '已隐藏',
    deleted: '已删除',
    active: '正常',
    disabled: '已禁用',
  };

  initTheme();
  if (elements.themeToggle) {
    elements.themeToggle.addEventListener('click', () => {
      setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    });
  }

  function el(tag, className = '', text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function button(label, handler, className = 'small-button') {
    const node = el('button', className, label);
    node.type = 'button';
    node.addEventListener('click', async (event) => {
      try {
        await handler(event, node);
      } catch (error) {
        alert(error.message || '操作失败，请刷新后重试');
      }
    });
    return node;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrfToken, ...(options.headers || {}) },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || '操作失败');
    }
    if (response.status === 204) return null;
    return response.json();
  }

  async function loadData() {
    const me = await fetch('/api/me').then((response) => response.json());
    state.me = me.user;
    state.csrfToken = me.csrf_token;
    const lineupParam = state.lineupQuery ? `?q=${encodeURIComponent(state.lineupQuery)}` : '';
    const userParam = state.userQuery ? `?q=${encodeURIComponent(state.userQuery)}` : '';
    [state.stats, state.reports, state.lineups, state.users, state.logs] = await Promise.all([
      api('/api/admin/stats'),
      api('/api/admin/reports'),
      api(`/api/admin/lineups${lineupParam}`),
      api(`/api/admin/users${userParam}`),
      api('/api/admin/audit-logs'),
    ]);
    render();
  }

  function render() {
    syncHeader();
    root.replaceChildren();
    if (state.notice) root.append(el('div', 'message admin-inline-message', state.notice));
    root.append(renderSummary(), renderModules());
    renderPasswordDialog();
  }

  function syncHeader() {
    if (elements.adminIdentity) {
      elements.adminIdentity.textContent = state.me ? `${state.me.nickname} · 管理员` : '后台账号';
    }
    if (elements.heroTodayUv) {
      elements.heroTodayUv.textContent = String(state.stats.today_uv || 0);
    }
  }

  function renderModules() {
    const grid = el('div', 'admin-modules-grid');
    grid.append(renderTraffic(), renderReports(), renderLineups(), renderUsers(), renderLogs());
    return grid;
  }

  function renderSummary() {
    const hiddenLineups = state.lineups.filter((lineup) => lineup.status === 'hidden').length;
    const cards = el('div', 'admin-stat-grid');
    [
      ['今日 UV', state.stats.today_uv || 0, '全站按天去重'],
      ['昨日 UV', state.stats.yesterday_uv || 0, '对比前一自然日'],
      ['总用户', state.stats.total_users || 0, '不含管理员账号'],
      ['今日注册', state.stats.today_users || 0, '新用户增长'],
      ['今日登录', state.stats.today_logins || 0, '去重登录用户'],
      ['待处理举报', state.reports.length, '处理后自动移出'],
      ['已隐藏阵容', hiddenLineups, '当前搜索范围内'],
    ].forEach(([label, value, caption]) => {
      const card = el('article', 'admin-stat-card');
      card.append(el('span', 'stat-label', label), el('strong', '', String(value)), el('small', '', caption));
      cards.append(card);
    });
    return cards;
  }

  function renderTraffic() {
    const trend = state.stats.last_7_days_uv || [];
    const totalUv = trend.reduce((sum, item) => sum + Number(item.uv || 0), 0);
    const highestUv = Math.max(1, ...trend.map((item) => Number(item.uv || 0)));
    const { section, body } = createModule('访问概览', '按自然日去重，覆盖游客与登录用户');
    section.classList.add('admin-module-wide', 'admin-traffic-module');

    const overview = el('div', 'traffic-overview');
    overview.append(
      trafficMetric('今日 UV', state.stats.today_uv || 0, buildDeltaText(state.stats.today_uv || 0, state.stats.yesterday_uv || 0)),
      trafficMetric('昨日 UV', state.stats.yesterday_uv || 0, '上一自然日'),
      trafficMetric('7 日累计 UV', totalUv, '最近 7 天总访问人数'),
    );

    const trendList = el('div', 'traffic-trend-list');
    if (!trend.length) {
      trendList.append(empty('暂无访问数据'));
    } else {
      trend.forEach((item) => {
        const uv = Number(item.uv || 0);
        const row = el('article', 'traffic-trend-row');
        const head = el('div', 'traffic-trend-head');
        head.append(el('strong', '', formatDay(item.date)), el('span', '', `${uv} UV`));
        const track = el('div', 'traffic-trend-track');
        const fill = el('span', 'traffic-trend-fill');
        fill.style.width = uv ? `${Math.max((uv / highestUv) * 100, 8)}%` : '0%';
        track.append(fill);
        row.append(head, track);
        trendList.append(row);
      });
    }

    body.append(overview, trendList);
    return section;
  }

  function trafficMetric(label, value, caption) {
    const card = el('article', 'traffic-metric');
    card.append(el('span', 'stat-label', label), el('strong', '', String(value)), el('small', '', caption));
    return card;
  }

  function createModule(title, subtitle, controls = null) {
    const section = el('section', 'admin-module');
    const header = el('div', 'admin-module-header');
    header.append(sectionTitle(title, subtitle));
    if (controls) header.append(controls);
    const body = el('div', 'admin-module-body');
    section.append(header, body);
    return { section, body };
  }

  function renderReports() {
    const { section, body } = createModule('用户举报', '只展示待处理举报；处理后自动从这里移除');
    const list = el('div', 'admin-list');
    if (!state.reports.length) list.append(empty('暂无待处理举报'));
    state.reports.forEach((report) => list.append(reportCard(report)));
    body.append(list);
    return section;
  }

  function reportCard(report) {
    const card = el('article', 'admin-card is-alert');
    const head = el('div', 'admin-card-head');
    head.append(el('h3', '', `#${report.id} ${report.lineup_name || '阵容已删除'}`), pill(statusText[report.status] || report.status));
    const meta = el('p', 'admin-meta', `举报人：${report.reporter_nickname || '-'} · 作者：${report.owner_nickname || '-'} · 提交：${report.created_at}`);
    const reason = el('p', 'admin-reason', report.reason);
    const code = el('pre', 'admin-code', report.lineup_code || '无阵容码');
    const actions = el('div', 'card-actions');
    actions.append(
      button('处理并隐藏阵容', () => handleReport(report.id, 'resolved', true)),
      button('仅标记已处理', () => handleReport(report.id, 'resolved', false)),
      button('驳回举报', () => handleReport(report.id, 'dismissed', false), 'small-button danger-button'),
    );
    card.append(head, meta, reason, code, actions);
    return card;
  }

  async function handleReport(id, status, hideLineup) {
    const actionText = hideLineup ? '处理举报并隐藏阵容' : (status === 'dismissed' ? '驳回举报' : '标记举报为已处理');
    if (!confirm(`确定要${actionText}吗？`)) return;
    await api(`/api/admin/reports/${id}/resolve`, { method: 'POST', body: JSON.stringify({ status, hide_lineup: hideLineup }) });
    setNotice(hideLineup ? '举报已处理，阵容已隐藏' : '举报状态已更新');
    await loadData();
  }

  function renderLineups() {
    const controls = searchBox('搜索阵容/阵容码/作者', state.lineupQuery, async (value) => {
      state.lineupQuery = value;
      await loadData();
    });
    const { section, body } = createModule('阵容管理', '按阵容名、阵容码、作者用户名或昵称查找', controls);
    const list = el('div', 'admin-list compact');
    if (!state.lineups.length) list.append(empty('没有找到阵容'));
    state.lineups.slice(0, 50).forEach((lineup) => {
      const card = el('article', 'admin-row-card');
      const info = el('div');
      info.append(el('strong', '', lineup.name), el('p', 'admin-meta', `作者：${lineup.owner_nickname || '-'} · ${statusText[lineup.status] || lineup.status} · 赞 ${lineup.like_count} · 复制 ${lineup.copy_count} · 分 ${lineup.score}`));
      const actions = el('div', 'card-actions');
      actions.append(
        button(lineup.status === 'hidden' ? '恢复' : '隐藏', () => updateLineupStatus(lineup, lineup.status === 'hidden' ? 'normal' : 'hidden')),
        button('调整分数', () => adjustScore(lineup)),
      );
      card.append(info, actions);
      list.append(card);
    });
    body.append(list);
    return section;
  }

  function searchBox(placeholder, value, onSearch) {
    const wrap = el('form', 'admin-search');
    const input = el('input');
    input.type = 'search';
    input.placeholder = placeholder;
    input.value = value;
    const submit = button('查找', () => {}, 'small-button');
    submit.type = 'submit';
    const reset = button('清空', async () => {
      input.value = '';
      await onSearch('');
    }, 'small-button');
    wrap.append(input, submit, reset);
    wrap.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await onSearch(input.value.trim());
      } catch (error) {
        alert(error.message || '查找失败，请刷新后重试');
      }
    });
    return wrap;
  }

  async function updateLineupStatus(lineup, status) {
    await api(`/api/admin/lineups/${lineup.id}`, { method: 'PUT', body: JSON.stringify({ status }) });
    setNotice(status === 'hidden' ? '阵容已隐藏' : '阵容已恢复');
    await loadData();
  }

  async function adjustScore(lineup) {
    const likeValue = prompt('设置管理员点赞修正数', lineup.admin_like_adjustment || 0);
    if (likeValue === null) return;
    const copyValue = prompt('设置管理员复制修正数', lineup.admin_copy_adjustment || 0);
    if (copyValue === null) return;
    await api(`/api/admin/lineups/${lineup.id}/adjust-score`, { method: 'POST', body: JSON.stringify({ admin_like_adjustment: Number(likeValue), admin_copy_adjustment: Number(copyValue) }) });
    setNotice('热度修正已保存');
    await loadData();
  }

  function renderUsers() {
    const controls = searchBox('搜索用户名/邮箱/昵称', state.userQuery, async (value) => {
      state.userQuery = value;
      await loadData();
    });
    const { section, body } = createModule('用户管理', '按用户名、邮箱或昵称查找', controls);
    const list = el('div', 'admin-list compact');
    if (!state.users.length) list.append(empty('没有找到用户'));
    state.users.slice(0, 50).forEach((user) => {
      const card = el('article', 'admin-row-card');
      const info = el('div');
      info.append(el('strong', '', `${user.nickname}（${user.username}）`), el('p', 'admin-meta', `${user.email} · ${user.role} · ${statusText[user.status] || user.status} · 注册 ${user.created_at}`));
      const actions = el('div', 'card-actions');
      actions.append(button('修改密码', () => openPasswordDialog(user)));
      if (user.status !== 'disabled') actions.append(button('禁用', () => disableUser(user.id), 'small-button danger-button'));
      card.append(info, actions);
      list.append(card);
    });
    body.append(list);
    return section;
  }

  function openPasswordDialog(user) {
    state.passwordUser = user;
    state.passwordError = '';
    renderPasswordDialog();
  }

  function closePasswordDialog() {
    state.passwordUser = null;
    state.passwordError = '';
    renderPasswordDialog();
  }

  function renderPasswordDialog() {
    if (!dialogRoot) return;
    dialogRoot.replaceChildren();
    if (!state.passwordUser) return;

    const overlay = el('div', 'modal-backdrop');
    const card = el('section', 'modal-card admin-password-dialog');
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-labelledby', 'passwordDialogTitle');

    const header = el('div', 'modal-header');
    const titleWrap = el('div');
    const title = el('h2', '', '修改用户密码');
    title.id = 'passwordDialogTitle';
    titleWrap.append(
      title,
      el('p', 'admin-meta', `正在修改 ${state.passwordUser.nickname}（${state.passwordUser.username}）的登录密码`),
    );
    const closeButton = button('取消', () => closePasswordDialog());
    header.append(titleWrap, closeButton);

    const form = el('form', 'modal-form');
    form.innerHTML = `
      <label class="field">
        <span>新密码</span>
        <input id="passwordInput" name="password" type="password" placeholder="大于 5 位，且包含字母和数字" autocomplete="new-password" />
      </label>
      <label class="field">
        <span>确认密码</span>
        <input id="confirmPasswordInput" name="confirmPassword" type="password" placeholder="再次输入新密码" autocomplete="new-password" />
      </label>
      <div class="message" id="passwordDialogMessage">${state.passwordError || ''}</div>
      <div class="editor-actions">
        <button class="primary-button" type="submit">保存新密码</button>
        <button class="ghost-button" type="button" id="cancelPasswordButton">取消</button>
      </div>
    `;
    form.addEventListener('submit', submitPasswordReset);
    form.querySelector('#cancelPasswordButton').addEventListener('click', closePasswordDialog);
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) closePasswordDialog();
    });

    card.append(header, form);
    overlay.append(card);
    dialogRoot.append(overlay);
  }

  async function submitPasswordReset(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = form.querySelector('#passwordInput').value;
    const confirmPassword = form.querySelector('#confirmPasswordInput').value;
    if (!isValidPassword(password)) {
      state.passwordError = '密码需大于5位且包含字母和数字';
      renderPasswordDialog();
      return;
    }
    if (password !== confirmPassword) {
      state.passwordError = '两次输入的密码不一致';
      renderPasswordDialog();
      return;
    }
    await api(`/api/admin/users/${state.passwordUser.id}`, {
      method: 'PUT',
      body: JSON.stringify({ password }),
    });
    const passwordUser = state.passwordUser;
    closePasswordDialog();
    setNotice(`已更新 ${passwordUser.nickname} 的密码`);
    await loadData();
  }

  function isValidPassword(password) {
    const value = String(password || '');
    return value.length > 5 && /[A-Za-z]/.test(value) && /\d/.test(value);
  }

  function setNotice(text) {
    state.notice = text;
    render();
    clearTimeout(setNotice.timer);
    setNotice.timer = setTimeout(() => {
      state.notice = '';
      render();
    }, 2600);
  }

  async function disableUser(id) {
    if (!confirm('确定禁用这个用户吗？')) return;
    await api(`/api/admin/users/${id}`, { method: 'DELETE' });
    setNotice('用户已禁用');
    await loadData();
  }

  function renderLogs() {
    const { section, body } = createModule('审计日志', '最近 30 条后台关键操作');
    const list = el('div', 'admin-log-list');
    if (!state.logs.length) list.append(empty('暂无审计日志'));
    state.logs.slice(0, 30).forEach((log) => {
      const item = el('div', 'admin-log-item');
      item.append(el('strong', '', log.action), el('span', '', `${log.target_type} #${log.target_id || '-'} · ${log.created_at}`));
      list.append(item);
    });
    body.append(list);
    return section;
  }

  function sectionTitle(title, subtitle) {
    const wrap = el('div', 'admin-section-title');
    wrap.append(el('h2', '', title), el('p', '', subtitle));
    return wrap;
  }

  function pill(text) {
    return el('span', 'admin-pill', text);
  }

  function empty(text) {
    return el('div', 'empty-state', text);
  }

  function buildDeltaText(today, yesterday) {
    const delta = Number(today || 0) - Number(yesterday || 0);
    if (delta === 0) return '与昨日持平';
    return delta > 0 ? `较昨日 +${delta}` : `较昨日 ${delta}`;
  }

  function formatDay(value) {
    const parts = String(value || '').split('-');
    if (parts.length !== 3) return value || '-';
    return `${parts[1]}-${parts[2]}`;
  }

  function initTheme() {
    setTheme(localStorage.getItem('theme') || 'light');
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('theme', theme);
    if (elements.themeIcon) elements.themeIcon.textContent = theme === 'dark' ? '☼' : '☾';
    if (elements.themeText) elements.themeText.textContent = theme === 'dark' ? '白天模式' : '夜间模式';
  }

  loadData().catch((error) => {
    root.textContent = error.message || '后台加载失败';
  });
})();
