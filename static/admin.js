(async function () {
  const root = document.querySelector('#adminApp');
  const dialogRoot = document.querySelector('#adminDialogRoot');
  const elements = {
    tabBar: document.querySelector('#adminTabBar'),
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
    activeTab: 'overview',
    overview: null,
    growth: null,
    growthDate: todayInputValue(),
    reports: { items: [], total: 0, page: 1, page_size: 20, total_pages: 1, status: 'pending', loadedAt: 0 },
    lineups: { items: [], total: 0, page: 1, page_size: 20, total_pages: 1, query: '', searched: false, loadedAt: 0 },
    users: { items: [], total: 0, page: 1, page_size: 20, total_pages: 1, query: '', searched: false, loadedAt: 0 },
    audit: { items: [], total: 0, page: 1, page_size: 30, total_pages: 1, loadedAt: 0 },
    controllers: {},
    cacheTtlMs: 30000,
    notice: '',
    passwordUser: null,
    passwordError: '',
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
  elements.themeToggle?.addEventListener('click', () => {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  });
  elements.tabBar?.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-admin-tab]');
    if (!button) return;
    await activateTab(button.dataset.adminTab);
  });

  await boot();

  function el(tag, className = '', text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function button(label, handler, className = 'small-button', disabled = false) {
    const node = el('button', className, label);
    node.type = 'button';
    node.disabled = disabled;
    node.addEventListener('click', async (event) => {
      try {
        await handler(event, node);
      } catch (error) {
        if (error?.name === 'AbortError') return;
        alert(error.message || '操作失败，请刷新后重试');
      }
    });
    return node;
  }

  async function boot() {
    const me = await fetch('/api/me').then((response) => response.json());
    state.me = me.user;
    state.csrfToken = me.csrf_token;
    await loadOverview({ force: true });
    render();
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': state.csrfToken,
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || '操作失败');
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function isFresh(loadedAt) {
    return loadedAt && (Date.now() - loadedAt < state.cacheTtlMs);
  }

  function abortRequest(key) {
    if (state.controllers[key]) {
      state.controllers[key].abort();
      delete state.controllers[key];
    }
  }

  async function activateTab(tabKey) {
    if (!tabKey) return;
    state.activeTab = tabKey;
    render();
    if (tabKey === 'overview') await loadOverview();
    if (tabKey === 'reports') await loadReports();
    if (tabKey === 'analytics') await loadGrowth();
    if (tabKey === 'audit') await loadAudit();
    render();
  }

  async function loadOverview({ force = false } = {}) {
    if (!force && state.overview && isFresh(state.overview.loadedAt)) return;
    const payload = await api('/api/admin/overview');
    state.overview = { ...payload, loadedAt: Date.now() };
  }

  async function loadReports({ force = false } = {}) {
    if (!force && isFresh(state.reports.loadedAt)) return;
    const query = new URLSearchParams({
      status: state.reports.status,
      page: String(state.reports.page),
      page_size: String(state.reports.page_size),
    });
    const payload = await api(`/api/admin/reports?${query.toString()}`);
    state.reports = { ...state.reports, ...payload, loadedAt: Date.now() };
  }

  async function loadLineups({ force = false } = {}) {
    if (!state.lineups.searched) return;
    if (!force && isFresh(state.lineups.loadedAt)) return;
    abortRequest('lineups');
    state.controllers.lineups = new AbortController();
    const query = new URLSearchParams({
      q: state.lineups.query,
      page: String(state.lineups.page),
      page_size: String(state.lineups.page_size),
    });
    const payload = await api(`/api/admin/lineups?${query.toString()}`, { signal: state.controllers.lineups.signal });
    state.lineups = { ...state.lineups, ...payload, loadedAt: Date.now() };
  }

  async function loadUsers({ force = false } = {}) {
    if (!state.users.searched) return;
    if (!force && isFresh(state.users.loadedAt)) return;
    abortRequest('users');
    state.controllers.users = new AbortController();
    const query = new URLSearchParams({
      q: state.users.query,
      page: String(state.users.page),
      page_size: String(state.users.page_size),
    });
    const payload = await api(`/api/admin/users?${query.toString()}`, { signal: state.controllers.users.signal });
    state.users = { ...state.users, ...payload, loadedAt: Date.now() };
  }

  async function loadAudit({ force = false } = {}) {
    if (!force && isFresh(state.audit.loadedAt)) return;
    const query = new URLSearchParams({
      page: String(state.audit.page),
      page_size: String(state.audit.page_size),
    });
    const payload = await api(`/api/admin/audit-logs?${query.toString()}`);
    state.audit = { ...state.audit, ...payload, loadedAt: Date.now() };
  }

  async function loadGrowth({ force = false } = {}) {
    if (!force && state.growth && state.growth.date === state.growthDate && isFresh(state.growth.loadedAt)) return;
    const payload = await api(`/api/admin/growth?date=${encodeURIComponent(state.growthDate)}`);
    state.growth = { ...payload, loadedAt: Date.now() };
  }

  function render() {
    syncHeader();
    syncTabs();
    root.replaceChildren();
    if (state.notice) root.append(el('div', 'message admin-inline-message', state.notice));
    if (state.activeTab === 'overview') root.append(renderOverviewDashboard());
    if (state.activeTab === 'reports') root.append(renderReportsWorkspace());
    if (state.activeTab === 'lineups') root.append(renderLineupsWorkspace());
    if (state.activeTab === 'users') root.append(renderUsersWorkspace());
    if (state.activeTab === 'analytics') root.append(renderAnalyticsWorkspace());
    if (state.activeTab === 'audit') root.append(renderAuditWorkspace());
    renderPasswordDialog();
  }

  function syncHeader() {
    if (elements.adminIdentity) {
      elements.adminIdentity.textContent = state.me ? `${state.me.nickname} · 管理员` : '后台账号';
    }
    if (elements.heroTodayUv) {
      elements.heroTodayUv.textContent = String(state.overview?.stats?.today_uv || 0);
    }
  }

  function syncTabs() {
    document.querySelectorAll('[data-admin-tab]').forEach((node) => {
      node.classList.toggle('is-active', node.dataset.adminTab === state.activeTab);
    });
  }

  function renderOverviewDashboard() {
    const wrap = el('div', 'admin-dashboard');
    wrap.append(renderOverviewStats());

    const grid = el('div', 'admin-dashboard-grid');
    grid.append(renderTrafficOverview(), renderTodoPanel(), renderQuickLinks());
    wrap.append(grid);
    return wrap;
  }

  function renderOverviewStats() {
    const stats = state.overview?.stats || {};
    const cards = el('div', 'admin-stat-grid');
    [
      ['今日 UV', stats.today_uv || 0, '全站按自然日去重'],
      ['今日注册', stats.today_users || 0, '新增用户数'],
      ['今日登录', stats.today_logins || 0, '去重登录用户'],
      ['待处理举报', stats.pending_reports_count || 0, '优先处理'],
      ['总用户', stats.total_users || 0, '不含管理员'],
    ].forEach(([label, value, caption]) => {
      const card = el('article', 'admin-stat-card');
      card.append(el('span', 'stat-label', label), el('strong', '', String(value)), el('small', '', caption));
      cards.append(card);
    });
    return cards;
  }

  function renderTrafficOverview() {
    const panel = workbenchPanel('7 日访问趋势', '只展示轻量趋势，不在首页加载完整增长漏斗');
    const body = panel.querySelector('.admin-workspace-body');
    const stats = state.overview?.stats || {};
    const trend = state.overview?.traffic_7d || [];
    const totalUv = trend.reduce((sum, item) => sum + Number(item.uv || 0), 0);
    const highestUv = Math.max(1, ...trend.map((item) => Number(item.uv || 0)));

    const overview = el('div', 'traffic-overview');
    overview.append(
      trafficMetric('今日 UV', stats.today_uv || 0, buildDeltaText(stats.today_uv || 0, stats.yesterday_uv || 0)),
      trafficMetric('昨日 UV', stats.yesterday_uv || 0, '上一自然日'),
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
    return panel;
  }

  function renderTodoPanel() {
    const panel = workbenchPanel('待办事项', '优先完成有风险和有反馈压力的任务');
    const body = panel.querySelector('.admin-workspace-body');
    const todos = state.overview?.todos || {};
    const list = el('div', 'admin-list compact');
    [
      ['待处理举报', `${todos.pending_reports_count || 0} 条`, '需要人工判断与处理'],
      ['已隐藏阵容', `${todos.hidden_lineups_count || 0} 条`, '可去阵容管理复核'],
      ['今日后台操作', `${todos.recent_audit_count || 0} 次`, '建议关注异常频繁操作'],
    ].forEach(([label, value, caption]) => {
      const card = el('article', 'admin-row-card');
      const info = el('div');
      info.append(el('strong', '', label), el('p', 'admin-meta', caption));
      card.append(info, el('span', 'admin-meta', value));
      list.append(card);
    });
    body.append(list);
    return panel;
  }

  function renderQuickLinks() {
    const panel = workbenchPanel('快捷入口', '按任务进入对应工作台');
    const body = panel.querySelector('.admin-workspace-body');
    const links = el('div', 'admin-quick-links');
    [
      ['去处理举报', '优先清理待处理问题', 'reports'],
      ['去查找阵容', '按阵容名、阵容码、作者查找', 'lineups'],
      ['去管理用户', '查找用户、改密、禁用', 'users'],
      ['查看增长分析', '查看转化漏斗与日期数据', 'analytics'],
      ['查看审计日志', '查看最近后台操作记录', 'audit'],
    ].forEach(([title, desc, tabKey]) => {
      const card = button(title, async () => {
        await activateTab(tabKey);
      }, 'admin-quick-link');
      const copy = el('span', 'admin-meta', desc);
      card.append(copy);
      links.append(card);
    });
    body.append(links);
    return panel;
  }

  function renderReportsWorkspace() {
    const panel = workbenchPanel('用户举报', '进入该工作台后再加载数据；支持分页切换');
    const body = panel.querySelector('.admin-workspace-body');
    body.append(renderReportStatusTabs());

    const list = el('div', 'admin-list');
    if (!state.reports.items.length) {
      list.append(empty(state.reports.status === 'pending' ? '暂无待处理举报' : '该状态下没有举报记录'));
    } else {
      state.reports.items.forEach((report) => list.append(reportCard(report)));
    }
    body.append(list, renderPagination('reports'));
    return panel;
  }

  function renderReportStatusTabs() {
    const wrap = el('div', 'admin-filter-pills');
    [
      ['pending', '待处理'],
      ['resolved', '已处理'],
      ['dismissed', '已驳回'],
    ].forEach(([value, label]) => {
      const node = button(label, async () => {
        state.reports.status = value;
        state.reports.page = 1;
        await loadReports({ force: true });
        render();
      }, `small-button ${state.reports.status === value ? 'is-active' : ''}`.trim());
      wrap.append(node);
    });
    return wrap;
  }

  function reportCard(report) {
    const card = el('article', 'admin-card is-alert');
    const head = el('div', 'admin-card-head');
    head.append(el('h3', '', `#${report.id} ${report.lineup_name || '阵容已删除'}`), pill(statusText[report.status] || report.status));
    const meta = el('p', 'admin-meta', `举报人：${report.reporter_nickname || '-'} · 作者：${report.owner_nickname || '-'} · 提交：${report.created_at}`);
    const reason = el('p', 'admin-reason', report.reason);
    const code = el('pre', 'admin-code', report.lineup_code || '无阵容码');
    card.append(head, meta, reason, code);
    if (report.status === 'pending') {
      const actions = el('div', 'card-actions');
      actions.append(
        button('处理并隐藏阵容', () => handleReport(report.id, 'resolved', true)),
        button('仅标记已处理', () => handleReport(report.id, 'resolved', false)),
        button('驳回举报', () => handleReport(report.id, 'dismissed', false), 'small-button danger-button'),
      );
      card.append(actions);
    }
    return card;
  }

  async function handleReport(id, status, hideLineup) {
    const actionText = hideLineup ? '处理举报并隐藏阵容' : (status === 'dismissed' ? '驳回举报' : '标记举报为已处理');
    if (!confirm(`确定要${actionText}吗？`)) return;
    await api(`/api/admin/reports/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ status, hide_lineup: hideLineup }),
    });
    await Promise.all([loadReports({ force: true }), loadOverview({ force: true })]);
    setNotice(hideLineup ? '举报已处理，阵容已隐藏' : '举报状态已更新');
  }

  function renderLineupsWorkspace() {
    const panel = workbenchPanel('阵容管理', '默认不加载列表，输入阵容名、阵容码、作者后开始查找');
    const body = panel.querySelector('.admin-workspace-body');
    body.append(lineupSearchControls());
    if (!state.lineups.searched) {
      body.append(empty('输入阵容名、阵容码、作者后开始查找', 'admin-empty-search'));
      return panel;
    }
    const list = el('div', 'admin-list compact');
    if (!state.lineups.items.length) {
      list.append(empty('没有找到阵容'));
    } else {
      state.lineups.items.forEach((lineup) => {
        const card = el('article', 'admin-row-card');
        const info = el('div');
        info.append(
          el('strong', '', lineup.name),
          el('p', 'admin-meta', `作者：${lineup.owner_nickname || '-'} · ${statusText[lineup.status] || lineup.status} · 赞 ${lineup.like_count} · 复制 ${lineup.copy_count} · 分 ${lineup.score}`),
        );
        const code = el('pre', 'admin-code', lineup.code || '无阵容码');
        info.append(code);
        const actions = el('div', 'card-actions');
        actions.append(
          button(lineup.status === 'hidden' ? '恢复' : '隐藏', async () => {
            await updateLineupStatus(lineup, lineup.status === 'hidden' ? 'normal' : 'hidden');
          }),
          button('调整分数', async () => {
            await adjustScore(lineup);
          }),
        );
        card.append(info, actions);
        list.append(card);
      });
    }
    body.append(list, renderPagination('lineups'));
    return panel;
  }

  function lineupSearchControls() {
    const wrap = el('form', 'admin-search');
    const input = el('input');
    input.type = 'search';
    input.placeholder = '搜索阵容名、阵容码、作者';
    input.value = state.lineups.query;
    const submit = el('button', 'small-button', '查找');
    submit.type = 'submit';
    const reset = button('清空', async () => {
      abortRequest('lineups');
      state.lineups = { ...state.lineups, items: [], total: 0, page: 1, total_pages: 1, query: '', searched: false, loadedAt: 0 };
      input.value = '';
      render();
    });
    const triggerSearch = debounce(async () => {
      const nextValue = input.value.trim();
      if (!nextValue) return;
      state.lineups.query = nextValue;
      state.lineups.page = 1;
      state.lineups.searched = true;
      await loadLineups({ force: true });
      render();
    }, 360);
    input.addEventListener('input', () => {
      if (!input.value.trim()) {
        abortRequest('lineups');
        state.lineups = { ...state.lineups, items: [], total: 0, page: 1, total_pages: 1, query: '', searched: false, loadedAt: 0 };
        render();
        return;
      }
      triggerSearch();
    });
    wrap.addEventListener('submit', async (event) => {
      event.preventDefault();
      const nextValue = input.value.trim();
      if (!nextValue) {
        render();
        return;
      }
      state.lineups.query = nextValue;
      state.lineups.page = 1;
      state.lineups.searched = true;
      await loadLineups({ force: true });
      render();
    });
    wrap.append(input, submit, reset);
    return wrap;
  }

  async function updateLineupStatus(lineup, status) {
    await api(`/api/admin/lineups/${lineup.id}`, { method: 'PUT', body: JSON.stringify({ status }) });
    await Promise.all([loadLineups({ force: true }), loadOverview({ force: true })]);
    setNotice(status === 'hidden' ? '阵容已隐藏' : '阵容已恢复');
  }

  async function adjustScore(lineup) {
    const likeValue = prompt('设置管理员点赞修正数', lineup.admin_like_adjustment || 0);
    if (likeValue === null) return;
    const copyValue = prompt('设置管理员复制修正数', lineup.admin_copy_adjustment || 0);
    if (copyValue === null) return;
    await api(`/api/admin/lineups/${lineup.id}/adjust-score`, {
      method: 'POST',
      body: JSON.stringify({ admin_like_adjustment: Number(likeValue), admin_copy_adjustment: Number(copyValue) }),
    });
    await loadLineups({ force: true });
    setNotice('热度修正已保存');
  }

  function renderUsersWorkspace() {
    const panel = workbenchPanel('用户管理', '默认不加载列表，搜索用户名、邮箱或昵称后开始查找');
    const body = panel.querySelector('.admin-workspace-body');
    body.append(userSearchControls());
    if (!state.users.searched) {
      body.append(empty('搜索用户名、邮箱或昵称后开始查找', 'admin-empty-search'));
      return panel;
    }
    const list = el('div', 'admin-list compact');
    if (!state.users.items.length) {
      list.append(empty('没有找到用户'));
    } else {
      state.users.items.forEach((user) => {
        const card = el('article', 'admin-row-card');
        const info = el('div');
        info.append(
          el('strong', '', `${user.nickname}（${user.username}）`),
          el('p', 'admin-meta', `${user.email} · ${user.role} · ${statusText[user.status] || user.status} · 注册 ${user.created_at}`),
        );
        const actions = el('div', 'card-actions');
        actions.append(button('修改密码', async () => {
          openPasswordDialog(user);
        }));
        if (user.status !== 'disabled') {
          actions.append(button('禁用', async () => {
            await disableUser(user.id);
          }, 'small-button danger-button'));
        }
        card.append(info, actions);
        list.append(card);
      });
    }
    body.append(list, renderPagination('users'));
    return panel;
  }

  function userSearchControls() {
    const wrap = el('form', 'admin-search');
    const input = el('input');
    input.type = 'search';
    input.placeholder = '搜索用户名、邮箱或昵称';
    input.value = state.users.query;
    const submit = el('button', 'small-button', '查找');
    submit.type = 'submit';
    const reset = button('清空', async () => {
      abortRequest('users');
      state.users = { ...state.users, items: [], total: 0, page: 1, total_pages: 1, query: '', searched: false, loadedAt: 0 };
      input.value = '';
      render();
    });
    const triggerSearch = debounce(async () => {
      const nextValue = input.value.trim();
      if (!nextValue) return;
      state.users.query = nextValue;
      state.users.page = 1;
      state.users.searched = true;
      await loadUsers({ force: true });
      render();
    }, 360);
    input.addEventListener('input', () => {
      if (!input.value.trim()) {
        abortRequest('users');
        state.users = { ...state.users, items: [], total: 0, page: 1, total_pages: 1, query: '', searched: false, loadedAt: 0 };
        render();
        return;
      }
      triggerSearch();
    });
    wrap.addEventListener('submit', async (event) => {
      event.preventDefault();
      const nextValue = input.value.trim();
      if (!nextValue) {
        render();
        return;
      }
      state.users.query = nextValue;
      state.users.page = 1;
      state.users.searched = true;
      await loadUsers({ force: true });
      render();
    });
    wrap.append(input, submit, reset);
    return wrap;
  }

  function renderAnalyticsWorkspace() {
    const panel = workbenchPanel('增长分析', '按自然日查询，不在首页默认加载', growthDateControl());
    const body = panel.querySelector('.admin-workspace-body');
    const growth = state.growth || {};
    const list = el('div', 'admin-list compact');
    [
      ['首页访问人数', growth.home_uv || 0],
      ['点击登录入口人数', growth.login_entry_visitors || 0],
      ['进入登录页面人数', growth.auth_page_visitors || 0],
      ['注册成功人数', growth.successful_registrations || 0],
      ['登录成功人数', growth.successful_logins || 0],
      ['游客尝试点赞人数', growth.guest_like_visitors || 0],
      ['游客尝试收藏人数', growth.guest_favorite_visitors || 0],
      ['登录后 10 分钟内完成点赞人数', growth.post_login_like_users || 0],
      ['登录后 10 分钟内完成收藏人数', growth.post_login_favorite_users || 0],
      ['登录后 10 分钟内上传阵容人数', growth.post_login_create_lineup_users || 0],
    ].forEach(([label, value]) => {
      const card = el('article', 'admin-row-card');
      card.append(el('strong', '', label), el('span', 'admin-meta', String(value)));
      list.append(card);
    });

    const rates = el('div', 'admin-list compact');
    [
      ['登录入口到登录页转化率', formatPercent(growth.conversion_rates?.entry_to_auth_page_pct)],
      ['登录页到注册/登录成功转化率', formatPercent(growth.conversion_rates?.auth_page_to_auth_success_pct)],
      ['登录后完成点赞转化率', formatPercent(growth.conversion_rates?.auth_success_to_like_pct)],
      ['登录后完成收藏转化率', formatPercent(growth.conversion_rates?.auth_success_to_favorite_pct)],
      ['登录后上传阵容转化率', formatPercent(growth.conversion_rates?.auth_success_to_create_lineup_pct)],
    ].forEach(([label, value]) => {
      const card = el('article', 'admin-row-card');
      card.append(el('strong', '', label), el('span', 'admin-meta', value));
      rates.append(card);
    });
    body.append(list, rates);
    return panel;
  }

  function growthDateControl() {
    const wrap = el('form', 'admin-search');
    const input = el('input');
    input.type = 'date';
    input.value = state.growthDate;
    const submit = el('button', 'small-button', '查询');
    submit.type = 'submit';
    const reset = button('今天', async () => {
      state.growthDate = todayInputValue();
      await loadGrowth({ force: true });
      render();
    });
    wrap.append(input, submit, reset);
    wrap.addEventListener('submit', async (event) => {
      event.preventDefault();
      state.growthDate = input.value || todayInputValue();
      await loadGrowth({ force: true });
      render();
    });
    return wrap;
  }

  function renderAuditWorkspace() {
    const panel = workbenchPanel('审计日志', '进入该工作台后再加载，支持分页查看最近后台操作');
    const body = panel.querySelector('.admin-workspace-body');
    const list = el('div', 'admin-log-list');
    if (!state.audit.items.length) {
      list.append(empty('暂无审计日志'));
    } else {
      state.audit.items.forEach((log) => {
        const item = el('div', 'admin-log-item');
        item.append(el('strong', '', log.action), el('span', '', `${log.target_type} #${log.target_id || '-'} · ${log.created_at}`));
        list.append(item);
      });
    }
    body.append(list, renderPagination('audit'));
    return panel;
  }

  function renderPagination(kind) {
    const source = state[kind];
    if (!source || (source.total_pages || 1) <= 1) return el('div');
    const wrap = el('div', 'admin-pagination');
    wrap.append(
      button('上一页', async () => {
        if (source.page <= 1) return;
        state[kind].page -= 1;
        await reloadKind(kind);
        render();
      }, 'small-button', source.page <= 1),
    );
    wrap.append(el('span', 'admin-meta', `第 ${source.page} / ${source.total_pages} 页 · 共 ${source.total} 条`));
    wrap.append(
      button('下一页', async () => {
        if (source.page >= source.total_pages) return;
        state[kind].page += 1;
        await reloadKind(kind);
        render();
      }, 'small-button', source.page >= source.total_pages),
    );
    return wrap;
  }

  async function reloadKind(kind) {
    if (kind === 'reports') await loadReports({ force: true });
    if (kind === 'lineups') await loadLineups({ force: true });
    if (kind === 'users') await loadUsers({ force: true });
    if (kind === 'audit') await loadAudit({ force: true });
  }

  function workbenchPanel(title, subtitle, controls = null) {
    const section = el('section', 'admin-workspace-panel');
    const header = el('div', 'admin-module-header');
    header.append(sectionTitle(title, subtitle));
    if (controls) header.append(controls);
    const body = el('div', 'admin-workspace-body');
    section.append(header, body);
    return section;
  }

  function trafficMetric(label, value, caption) {
    const card = el('article', 'traffic-metric');
    card.append(el('span', 'stat-label', label), el('strong', '', String(value)), el('small', '', caption));
    return card;
  }

  function sectionTitle(title, subtitle) {
    const wrap = el('div', 'admin-section-title');
    wrap.append(el('h2', '', title), el('p', '', subtitle));
    return wrap;
  }

  function pill(text) {
    return el('span', 'admin-pill', text);
  }

  function empty(text, className = '') {
    return el('div', ['empty-state', className].filter(Boolean).join(' '), text);
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
    titleWrap.append(title, el('p', 'admin-meta', `正在修改 ${state.passwordUser.nickname}（${state.passwordUser.username}）的登录密码`));
    header.append(titleWrap, button('取消', async () => closePasswordDialog()));

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
    if (state.users.searched) await loadUsers({ force: true });
    setNotice(`已更新 ${passwordUser.nickname} 的密码`);
  }

  function isValidPassword(password) {
    const value = String(password || '');
    return value.length > 5 && /[A-Za-z]/.test(value) && /\d/.test(value);
  }

  async function disableUser(id) {
    if (!confirm('确定禁用这个用户吗？')) return;
    await api(`/api/admin/users/${id}`, { method: 'DELETE' });
    if (state.users.searched) await loadUsers({ force: true });
    await loadOverview({ force: true });
    setNotice('用户已禁用');
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

  function formatPercent(value) {
    return `${Number(value || 0).toFixed(2)}%`;
  }

  function todayInputValue() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
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

  function debounce(callback, delay) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => callback(...args), delay);
    };
  }
})().catch((error) => {
  const root = document.querySelector('#adminApp');
  if (root) root.textContent = error.message || '后台加载失败';
});
