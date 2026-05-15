const state = {
  lineups: [],
  liveCompsSummary: null,
  liveCompsPage: null,
  query: '',
  sort: 'live',
  view: 'live-comps',
  user: null,
  csrfToken: '',
  page: 1,
  pageSize: 10,
  total: 0,
  totalPages: 1,
};

const LINEUP_PAGE_SIZE = 10;

const $ = (selector) => document.querySelector(selector);
const elements = {
  authStatus: $('#authStatus'),
  authLink: $('#authLink'),
  logoutButton: $('#logoutButton'),
  adminLink: $('#adminLink'),
  accountLink: $('#accountLink'),
  createLineupLink: $('#createLineupLink'),
  searchInput: $('#searchInput'),
  lineupList: $('#lineupList'),
  emptyState: $('#emptyState'),
  message: $('#message'),
  lineupCount: $('#lineupCount'),
  favoritesTab: $('#favoritesTab'),
  mineTab: $('#mineTab'),
  tabs: $('#tabs'),
  pagination: $('#pagination'),
  themeToggle: $('#themeToggle'),
  themeIcon: $('#themeIcon'),
  themeText: $('#themeText'),
  toast: $('#toast'),
  authPromptRoot: $('#authPromptRoot'),
  listTitle: $('#listTitle'),
};

setTheme(localStorage.getItem('theme') || 'light');
boot();

elements.themeToggle.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
elements.logoutButton.addEventListener('click', logout);
elements.authLink.addEventListener('click', () => {
  trackGrowth('click_login_entry', { source: 'header' });
});
elements.searchInput.addEventListener('input', debounce((event) => {
  if (state.view === 'live-comps') return;
  state.query = event.target.value.trim();
  state.page = 1;
  loadLineups();
}, 180));
elements.tabs.addEventListener('click', (event) => {
  const tab = event.target.closest('.tab');
  if (!tab) return;
  if (!state.user && tab.dataset.view === 'favorites') {
    requireAuthIntent({ type: 'open_view_favorites' }, '登录后可收藏阵容并随时找回');
    return;
  }
  if (!state.user && tab.dataset.view === 'mine') {
    requireAuthIntent({ type: 'open_view_mine' }, '登录后可查看和管理你发布的阵容');
    return;
  }
  setActiveTab(tab.dataset.sort, tab.dataset.view);
  loadCurrentView();
});
elements.pagination.addEventListener('click', (event) => {
  const button = event.target.closest('[data-page]');
  if (!button) return;
  const nextPage = Number(button.dataset.page);
  if (!nextPage || nextPage === state.page) return;
  state.page = nextPage;
  loadCurrentView();
});
elements.createLineupLink.addEventListener('click', (event) => {
  if (state.user) return;
  event.preventDefault();
  requireAuthIntent({ type: 'open_create_lineup' }, '登录后可发布和管理自己的阵容');
});

async function boot() {
  await loadMe();
  applySavedMessage();
  await consumePendingIntent();
  await loadCurrentView();
}

async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  if (state.csrfToken && ['POST', 'PUT', 'DELETE'].includes(options.method)) headers['X-CSRF-Token'] = state.csrfToken;
  const response = await fetch(url, { ...options, headers });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || '操作失败');
  return data;
}

async function trackGrowth(eventName, payload = {}) {
  if (!state.csrfToken) return;
  await fetch('/api/growth-events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrfToken },
    body: JSON.stringify({
      event_name: eventName,
      page_key: 'home',
      ref_lineup_id: payload.lineupId || null,
      payload,
    }),
  }).catch(() => {});
}

async function loadMe() {
  const data = await fetch('/api/me').then((response) => response.json());
  state.user = data.user;
  state.csrfToken = data.csrf_token;
  renderAuth();
}

function renderAuth() {
  const loggedIn = Boolean(state.user);
  elements.authLink.classList.toggle('hidden', loggedIn);
  elements.logoutButton.classList.toggle('hidden', !loggedIn);
  elements.mineTab.classList.toggle('hidden', !loggedIn);
  elements.favoritesTab.classList.remove('hidden');
  elements.adminLink.classList.toggle('hidden', !(state.user && state.user.role === 'admin'));
  elements.accountLink.classList.toggle('hidden', !loggedIn);
  elements.authStatus.textContent = loggedIn ? `${state.user.nickname}` : '未登录';
  elements.createLineupLink.href = loggedIn ? '/lineup/new' : '/auth';
  elements.createLineupLink.textContent = loggedIn ? '新增阵容' : '登录后新增阵容';
  if (!loggedIn && (state.view === 'mine' || state.view === 'favorites')) {
    state.sort = 'live';
    state.view = 'live-comps';
    state.page = 1;
  }
  syncActiveTab();
}

async function logout() {
  await api('/api/logout', { method: 'POST' });
  state.user = null;
  state.sort = 'live';
  state.view = 'live-comps';
  state.page = 1;
  closeAuthPrompt(true);
  showMessage('已退出登录');
  renderAuth();
  await loadCurrentView();
}

async function loadLineups() {
  const params = new URLSearchParams({
    sort: state.sort,
    view: state.view,
    page: String(state.page),
    page_size: String(LINEUP_PAGE_SIZE),
  });
  if (state.query) params.set('q', state.query);
  const response = await fetch(`/api/lineups?${params}`).then((result) => result.json());
  state.lineups = response.items || [];
  state.total = response.total ?? state.lineups.length;
  state.page = response.page ?? 1;
  state.pageSize = response.page_size ?? state.pageSize;
  state.totalPages = response.total_pages ?? 1;
  renderLineups();
  renderPagination();
}

function syncSearchInputState(isLiveComps) {
  elements.searchInput.disabled = isLiveComps;
  elements.searchInput.placeholder = isLiveComps
    ? '实时阵容排行暂不支持搜索'
    : '搜索阵容名称，例如：九五、卡莎、斗士';
  elements.searchInput.value = isLiveComps ? '' : state.query;
}

async function loadCurrentView() {
  syncSearchInputState(state.view === 'live-comps');
  elements.listTitle.textContent = state.view === 'live-comps' ? '实时阵容排行' : '阵容列表';
  if (state.view === 'live-comps') {
    await loadLiveComps();
    return;
  }
  await loadLineups();
}

async function loadLiveComps() {
  const summary = await fetch('/api/live-comps/summary').then((response) => response.json());
  const pagePayload = await fetch(`/api/live-comps?page=${state.page}`).then((response) => response.json());
  state.liveCompsSummary = summary;
  state.liveCompsPage = pagePayload;
  state.total = pagePayload.total ?? 0;
  state.page = pagePayload.page ?? 1;
  state.pageSize = pagePayload.page_size ?? state.pageSize;
  state.totalPages = pagePayload.total_pages ?? 1;
  renderLiveComps();
  renderPagination();
}

function renderLineups() {
  elements.lineupList.replaceChildren();
  elements.lineupCount.textContent = state.total;
  elements.emptyState.classList.toggle('hidden', state.total > 0);
  renderEmptyState();
  state.lineups.forEach((lineup) => {
    const card = document.createElement('article');
    card.className = 'lineup-card';
    const title = document.createElement('h3');
    title.className = 'lineup-title';
    title.textContent = `${lineup.name} · ${lineup.rank_level}`;
    const meta = document.createElement('div');
    meta.className = 'card-time';
    meta.append('由 ');
    const authorLink = document.createElement('a');
    authorLink.className = 'author-link';
    authorLink.href = `/author/${encodeURIComponent(lineup.owner_username || '')}`;
    authorLink.textContent = lineup.owner_nickname;
    meta.append(authorLink, ` 上传 · 赞 ${lineup.like_count} · 复制 ${lineup.copy_count} · ${lineup.updated_at}`);
    const code = document.createElement('pre');
    code.className = 'code-preview';
    code.textContent = lineup.code;
    const actions = document.createElement('div');
    actions.className = 'card-actions';
    actions.append(button('复制阵容码', () => copyLineup(lineup)));
    actions.append(button('查看', () => openLineupDetail(lineup.id)));
    actions.append(button(lineup.is_liked_today ? '今日已赞' : '点赞', () => likeLineup(lineup), '', Boolean(state.user && lineup.is_liked_today)));
    actions.append(button(lineup.is_favorited ? '取消收藏' : '收藏', () => favoriteLineup(lineup)));
    actions.append(button('举报', () => reportLineup(lineup)));
    if (lineup.can_hide) actions.append(button('隐藏阵容', () => hideLineup(lineup), 'danger-button'));
    if (lineup.can_edit) actions.append(button('编辑', () => openEditor(lineup.id)));
    if (lineup.can_delete) actions.append(button('删除', () => deleteLineup(lineup), 'danger-button'));
    card.append(title, meta, code, actions);
    elements.lineupList.append(card);
  });
}

function renderEmptyState() {
  const title = elements.emptyState.querySelector('h3');
  const description = elements.emptyState.querySelector('p');
  if (state.total > 0 || !title || !description) return;
  if (state.view === 'live-comps') {
    title.textContent = '还没有实时阵容';
    description.textContent = '上传 `team_codes_by_tier.verify.json` 后，这里会直接展示实时阵容排行。';
    return;
  }
  if (state.view === 'favorites') {
    title.textContent = '还没有收藏阵容';
    description.textContent = state.user
      ? '你收藏的阵容会出现在这里，可随时回来查看和复制。'
      : '登录后可收藏阵容并随时找回，收藏内容会跟随账号同步。';
    return;
  }
  if (state.view === 'mine') {
    title.textContent = '还没有你的阵容';
    description.textContent = '登录后上传第一套阵容，管理和维护你自己的阵容库。';
    return;
  }
  title.textContent = '还没有阵容';
  description.textContent = '登录后上传第一套阵容，或切换到全部阵容查看公开内容。';
}

function renderPagination() {
  elements.pagination.replaceChildren();
  elements.pagination.classList.toggle('hidden', state.total <= state.pageSize);
  if (state.total <= state.pageSize) return;
  const fragment = document.createDocumentFragment();
  fragment.append(button('上一页', () => {}, 'small-button', state.page <= 1));
  fragment.lastChild.dataset.page = String(state.page - 1);
  buildPageList(state.page, state.totalPages).forEach((token) => {
    if (token === '...') {
      const ellipsis = document.createElement('span');
      ellipsis.className = 'pagination-ellipsis';
      ellipsis.textContent = '...';
      fragment.append(ellipsis);
      return;
    }
    const pageButton = button(String(token), () => {}, `small-button ${token === state.page ? 'is-active' : ''}`.trim(), token === state.page);
    pageButton.dataset.page = String(token);
    fragment.append(pageButton);
  });
  const nextButton = button('下一页', () => {}, 'small-button', state.page >= state.totalPages);
  nextButton.dataset.page = String(state.page + 1);
  fragment.append(nextButton);
  elements.pagination.append(fragment);
}

function renderLiveComps() {
  elements.lineupList.replaceChildren();
  elements.lineupCount.textContent = state.total;
  elements.emptyState.classList.toggle('hidden', state.total > 0);
  renderEmptyState();
  if (!state.total) return;

  const shell = document.createElement('div');
  shell.className = 'live-comps-shell';
  shell.append(renderLiveCompsSummaryHeader());
  shell.append(renderLiveCompsGrid());
  elements.lineupList.append(shell);
}

function renderLiveCompsSummaryHeader() {
  const header = document.createElement('section');
  header.className = 'live-comps-summary';

  const title = document.createElement('h3');
  title.className = 'live-comps-summary-title';
  title.textContent = '实时阵容排行';

  const meta = document.createElement('p');
  meta.className = 'live-comps-summary-meta';
  meta.textContent = state.liveCompsSummary?.updated_at
    ? `共 ${state.total} 套 · 最近更新：${state.liveCompsSummary.updated_at}`
    : '最近更新：暂无数据';

  header.append(title, meta);
  return header;
}

function renderLiveCompsGrid() {
  const grid = document.createElement('div');
  grid.className = 'live-comps-grid';
  (state.liveCompsPage?.items || []).forEach((item) => {
    grid.append(renderLiveCompCard(item));
  });
  return grid;
}

function renderLiveCompCard(item) {
  const card = document.createElement('article');
  card.className = `live-comp-card tier-${String(item.tier || '').toLowerCase()}`;

  const header = document.createElement('div');
  header.className = 'live-comp-header';

  const avatarWrap = document.createElement('div');
  avatarWrap.className = 'live-comp-avatar-wrap';
  const avatar = document.createElement('img');
  avatar.className = 'live-comp-avatar';
  avatar.src = item.mainAvatar;
  avatar.alt = item.title;
  avatar.loading = 'lazy';
  const badge = document.createElement('span');
  badge.className = 'live-comp-avatar-badge';
  badge.textContent = item.tier;
  avatarWrap.append(avatar, badge);

  const body = document.createElement('div');
  body.className = 'live-comp-body';

  const name = document.createElement('h3');
  name.className = 'live-comp-name';
  name.textContent = item.title;

  const heroes = document.createElement('div');
  heroes.className = 'live-comp-hero-strip';
  (item.heroImages || []).forEach((src, index) => {
    const hero = document.createElement('img');
    hero.className = 'live-comp-hero';
    hero.src = src;
    hero.alt = `${item.title}-${index + 1}`;
    hero.loading = 'lazy';
    heroes.append(hero);
  });

  const actions = document.createElement('div');
  actions.className = 'live-comp-actions';
  actions.append(button('复制阵容码', () => copyLiveCompCode(item)));

  body.append(name, heroes);
  header.append(avatarWrap, body);
  card.append(header, actions);
  return card;
}

async function copyLiveCompCode(item) {
  const copied = await writeClipboard(item.jccCode);
  if (!copied) {
    showMessage('复制失败，请长按阵容码手动复制');
    return;
  }
  try {
    await api(`/api/live-comps/${encodeURIComponent(item.id)}/copy`, { method: 'POST' });
  } catch (_) {
    showMessage('阵容码已复制，但次数统计失败');
    return;
  }
  showToast('阵容码已复制');
}

function buildPageList(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const pages = new Set([1, total, current, current - 1, current + 1]);
  return Array.from(pages)
    .filter((value) => value >= 1 && value <= total)
    .sort((left, right) => left - right)
    .flatMap((value, index, array) => {
      if (index === 0) return [value];
      return value - array[index - 1] > 1 ? ['...', value] : [value];
    });
}

function button(label, handler, extraClass = '', disabled = false) {
  const element = document.createElement('button');
  element.type = 'button';
  element.className = `small-button ${extraClass}`.trim();
  element.textContent = label;
  element.disabled = disabled;
  element.addEventListener('click', () => handler(element));
  return element;
}

function setActiveTab(sort, view) {
  state.sort = sort;
  state.view = view;
  state.page = 1;
  syncActiveTab();
}

function syncActiveTab() {
  document.querySelectorAll('.tab').forEach((item) => {
    item.classList.toggle('active', item.dataset.sort === state.sort && item.dataset.view === state.view);
  });
}

function openEditor(lineupId) {
  window.location.href = `/lineup/${lineupId}/edit`;
}

function openLineupDetail(lineupId) {
  window.location.href = `/lineup/${lineupId}`;
}

async function copyLineup(lineup) {
  const copied = await writeClipboard(lineup.code);
  if (!copied) {
    showMessage('复制失败，请长按阵容码手动复制');
    return;
  }
  await api(`/api/lineups/${lineup.id}/copy`, { method: 'POST' });
  if (!state.user) {
    window.jccHistoryStore?.pushLocalCopy(lineup);
  }
  showToast('复制成功！祝你把把吃鸡！');
  loadLineups();
}

async function writeClipboard(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'readonly');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  textarea.style.pointerEvents = 'none';
  document.body.append(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  const copied = document.execCommand('copy');
  textarea.remove();
  return copied;
}

function requireAuthIntent(intent, message) {
  if (state.user) return false;
  window.jccAuthIntent?.save(intent);
  showAuthPrompt(message);
  return true;
}

function showAuthPrompt(message) {
  closeAuthPrompt(false);
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) closeAuthPrompt(true);
  });

  const card = document.createElement('section');
  card.className = 'modal-card';

  const header = document.createElement('div');
  header.className = 'modal-header';
  const headerCopy = document.createElement('div');
  const title = document.createElement('h2');
  title.textContent = '登录后继续';
  const desc = document.createElement('p');
  desc.className = 'auth-prompt-copy';
  desc.textContent = message;
  headerCopy.append(title, desc);
  const closeButton = button('关闭', () => closeAuthPrompt(true));
  header.append(headerCopy, closeButton);

  const hint = document.createElement('p');
  hint.className = 'field-hint';
  hint.textContent = '登录后可收藏阵容、查看我的收藏。';

  const actions = document.createElement('div');
  actions.className = 'auth-prompt-actions';
  const cancelButton = button('稍后', () => closeAuthPrompt(true));
  const loginButton = document.createElement('button');
  loginButton.type = 'button';
  loginButton.className = 'primary-button auth-prompt-confirm';
  loginButton.textContent = '去登录';
  loginButton.addEventListener('click', () => {
    closeAuthPrompt(false);
    window.location.href = '/auth';
  });
  actions.append(cancelButton, loginButton);

  card.append(header, hint, actions);
  backdrop.append(card);
  elements.authPromptRoot.append(backdrop);
}

function closeAuthPrompt(clearIntent = false) {
  elements.authPromptRoot.replaceChildren();
  if (clearIntent) window.jccAuthIntent?.clear();
}

function closeReportDialog() {
  elements.authPromptRoot.replaceChildren();
}

async function likeLineup(lineup) {
  if (!state.user) trackGrowth('guest_click_like', { source: 'lineup-card', lineupId: lineup.id });
  if (requireAuthIntent({ type: 'like_lineup', lineupId: lineup.id }, '登录后可点赞并保留个人记录')) return;
  try {
    await api(`/api/lineups/${lineup.id}/like`, { method: 'POST' });
    showMessage('点赞成功');
    await loadLineups();
  } catch (error) {
    showMessage(error.message);
  }
}

async function favoriteLineup(lineup) {
  if (!state.user) trackGrowth('guest_click_favorite', { source: 'lineup-card', lineupId: lineup.id });
  if (requireAuthIntent({ type: 'favorite_lineup', lineupId: lineup.id }, '登录后可收藏阵容并跨设备同步')) return;
  try {
    if (lineup.is_favorited) {
      await api(`/api/lineups/${lineup.id}/favorite`, { method: 'DELETE' });
      showMessage('已取消收藏');
    } else {
      await api(`/api/lineups/${lineup.id}/favorite`, { method: 'POST' });
      showMessage('收藏成功');
    }
    await loadLineups();
  } catch (error) {
    showMessage(error.message);
  }
}

async function reportLineup(lineup) {
  if (!state.user) trackGrowth('guest_click_report', { source: 'lineup-card', lineupId: lineup.id });
  if (requireAuthIntent({ type: 'report_lineup', lineupId: lineup.id }, '登录后可举报问题阵容并保留处理记录')) return;
  showReportDialog(lineup);
}

function showReportDialog(lineup) {
  closeReportDialog();
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) closeReportDialog();
  });

  const card = document.createElement('section');
  card.className = 'modal-card';

  const header = document.createElement('div');
  header.className = 'modal-header';
  const headerCopy = document.createElement('div');
  const title = document.createElement('h2');
  title.textContent = '举报阵容';
  const desc = document.createElement('p');
  desc.className = 'auth-prompt-copy';
  desc.textContent = `请填写举报原因，管理员会处理「${lineup.name}」。`;
  headerCopy.append(title, desc);
  const closeButton = button('关闭', () => closeReportDialog());
  header.append(headerCopy, closeButton);

  const form = document.createElement('form');
  form.className = 'modal-form';
  const field = document.createElement('label');
  field.className = 'field';
  const label = document.createElement('span');
  label.textContent = '举报原因';
  const textarea = document.createElement('textarea');
  textarea.rows = 5;
  textarea.maxLength = 300;
  textarea.placeholder = '请简要说明问题，例如：阵容码无效、内容不实、违规信息等';
  field.append(label, textarea);

  const inlineMessage = document.createElement('div');
  inlineMessage.className = 'message';

  const actions = document.createElement('div');
  actions.className = 'auth-prompt-actions';
  const cancelButton = button('取消', () => closeReportDialog());
  const submitButton = document.createElement('button');
  submitButton.type = 'submit';
  submitButton.className = 'primary-button auth-prompt-confirm';
  submitButton.textContent = '提交举报';
  actions.append(cancelButton, submitButton);
  form.append(field, inlineMessage, actions);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const reason = textarea.value.trim();
    if (!reason) {
      inlineMessage.textContent = '请输入举报原因';
      return;
    }
    submitButton.disabled = true;
    inlineMessage.textContent = '';
    try {
      await api(`/api/lineups/${lineup.id}/report`, { method: 'POST', body: JSON.stringify({ reason }) });
      closeReportDialog();
      showMessage('举报已提交');
    } catch (error) {
      inlineMessage.textContent = error.message;
    } finally {
      submitButton.disabled = false;
    }
  });

  card.append(header, form);
  backdrop.append(card);
  elements.authPromptRoot.append(backdrop);
  textarea.focus();
}

async function hideLineup(lineup) {
  if (!confirm(`确定隐藏“${lineup.name}”吗？`)) return;
  await api(`/api/lineups/${lineup.id}/hide`, { method: 'POST' });
  showMessage('阵容已隐藏');
  await loadLineups();
}

async function consumePendingIntent() {
  stripResumeIntentFlag();
  if (!state.user) return;
  const intent = window.jccAuthIntent?.read();
  if (!intent) return;
  window.jccAuthIntent.clear();
  if (intent.type === 'open_view_favorites') {
    setActiveTab('latest', 'favorites');
    showMessage('已进入我的收藏');
    return;
  }
  if (intent.type === 'open_view_mine') {
    setActiveTab('latest', 'mine');
    showMessage('已进入我的阵容');
    return;
  }
  if (intent.type === 'favorite_lineup') {
    try {
      await api(`/api/lineups/${intent.lineupId}/favorite`, { method: 'POST' });
      showMessage('已自动完成收藏');
    } catch (error) {
      showMessage(error.message);
    }
    return;
  }
  if (intent.type === 'like_lineup') {
    try {
      await api(`/api/lineups/${intent.lineupId}/like`, { method: 'POST' });
      showMessage('已自动完成点赞');
    } catch (error) {
      showMessage(error.message);
    }
    return;
  }
  if (intent.type === 'report_lineup') {
    try {
      const response = await fetch(`/api/lineups/${intent.lineupId}`);
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.error || '阵容不存在');
      showReportDialog(data);
    } catch (error) {
      showMessage(error.message);
    }
  }
}

async function deleteLineup(lineup) {
  if (!confirm('确定删除这个阵容吗？')) return;
  await api(`/api/lineups/${lineup.id}`, { method: 'DELETE' });
  showMessage('删除成功');
  if (state.page > 1 && state.lineups.length === 1) state.page -= 1;
  loadLineups();
}

function applySavedMessage() {
  const params = new URLSearchParams(window.location.search);
  const saved = params.get('saved');
  if (!saved) return;
  showMessage(saved === 'edit' ? '阵容已更新' : '阵容已新增');
  params.delete('saved');
  const nextQuery = params.toString();
  history.replaceState({}, '', `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}`);
}

function stripResumeIntentFlag() {
  const params = new URLSearchParams(window.location.search);
  if (!params.has('resume_intent')) return;
  params.delete('resume_intent');
  const nextQuery = params.toString();
  history.replaceState({}, '', `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}`);
}

function showMessage(text) {
  elements.message.textContent = text;
  clearTimeout(showMessage.timer);
  showMessage.timer = setTimeout(() => {
    elements.message.textContent = '';
  }, 2600);
}

function showToast(text) {
  if (!elements.toast) {
    showMessage(text);
    return;
  }
  elements.toast.textContent = text;
  elements.toast.classList.add('is-visible');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    elements.toast.classList.remove('is-visible');
  }, 2200);
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('theme', theme);
  elements.themeIcon.textContent = theme === 'dark' ? '☼' : '☾';
  elements.themeText.textContent = theme === 'dark' ? '白天模式' : '夜间模式';
}

function debounce(callback, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), delay);
  };
}
