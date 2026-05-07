const state = {
  lineups: [],
  query: '',
  sort: 'latest',
  view: 'all',
  user: null,
  csrfToken: '',
  page: 1,
  pageSize: 10,
  total: 0,
  totalPages: 1,
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  authStatus: $('#authStatus'),
  authLink: $('#authLink'),
  logoutButton: $('#logoutButton'),
  adminLink: $('#adminLink'),
  createLineupLink: $('#createLineupLink'),
  searchInput: $('#searchInput'),
  lineupList: $('#lineupList'),
  emptyState: $('#emptyState'),
  message: $('#message'),
  lineupCount: $('#lineupCount'),
  mineTab: $('#mineTab'),
  tabs: $('#tabs'),
  pagination: $('#pagination'),
  themeToggle: $('#themeToggle'),
  themeIcon: $('#themeIcon'),
  themeText: $('#themeText'),
};

setTheme(localStorage.getItem('theme') || 'light');
boot();

elements.themeToggle.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
elements.logoutButton.addEventListener('click', logout);
elements.searchInput.addEventListener('input', debounce((event) => {
  state.query = event.target.value.trim();
  state.page = 1;
  loadLineups();
}, 180));
elements.tabs.addEventListener('click', (event) => {
  const tab = event.target.closest('.tab');
  if (!tab) return;
  document.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
  tab.classList.add('active');
  state.sort = tab.dataset.sort;
  state.view = tab.dataset.view;
  state.page = 1;
  loadLineups();
});
elements.pagination.addEventListener('click', (event) => {
  const button = event.target.closest('[data-page]');
  if (!button) return;
  const nextPage = Number(button.dataset.page);
  if (!nextPage || nextPage === state.page) return;
  state.page = nextPage;
  loadLineups();
});

async function boot() {
  await loadMe();
  applySavedMessage();
  await loadLineups();
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
  elements.adminLink.classList.toggle('hidden', !(state.user && state.user.role === 'admin'));
  elements.authStatus.textContent = loggedIn ? `${state.user.nickname}` : '未登录';
  elements.createLineupLink.href = loggedIn ? '/lineup/new' : '/auth';
  elements.createLineupLink.textContent = loggedIn ? '新增阵容' : '登录后新增阵容';
  if (!loggedIn && state.view === 'mine') {
    state.view = 'all';
    document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item.dataset.view === 'all' && item.dataset.sort === 'latest'));
  }
}

async function logout() {
  await api('/api/logout', { method: 'POST' });
  state.user = null;
  state.view = 'all';
  state.page = 1;
  showMessage('已退出登录');
  renderAuth();
  loadLineups();
}

async function loadLineups() {
  const params = new URLSearchParams({
    sort: state.sort,
    view: state.view,
    page: String(state.page),
    page_size: String(state.pageSize),
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

function renderLineups() {
  elements.lineupList.replaceChildren();
  elements.lineupCount.textContent = state.total;
  elements.emptyState.classList.toggle('hidden', state.total > 0);
  state.lineups.forEach((lineup) => {
    const card = document.createElement('article');
    card.className = 'lineup-card';
    const title = document.createElement('h3');
    title.className = 'lineup-title';
    title.textContent = `${lineup.name} · ${lineup.rank_level}`;
    const meta = document.createElement('div');
    meta.className = 'card-time';
    meta.textContent = `由 ${lineup.owner_nickname} 上传 · 赞 ${lineup.like_count} · 复制 ${lineup.copy_count} · ${lineup.updated_at}`;
    const code = document.createElement('pre');
    code.className = 'code-preview';
    code.textContent = lineup.code;
    const actions = document.createElement('div');
    actions.className = 'card-actions';
    actions.append(button('复制阵容码', () => copyLineup(lineup)));
    if (state.user) {
      actions.append(button(lineup.is_liked_today ? '今日已赞' : '点赞', () => likeLineup(lineup), '', lineup.is_liked_today));
      actions.append(button(lineup.is_favorited ? '已收藏' : '收藏', () => favoriteLineup(lineup), '', lineup.is_favorited));
      actions.append(button('举报', () => reportLineup(lineup)));
    }
    if (lineup.can_edit) actions.append(button('编辑', () => openEditor(lineup.id)));
    if (lineup.can_delete) actions.append(button('删除', () => deleteLineup(lineup), 'danger-button'));
    card.append(title, meta, code, actions);
    elements.lineupList.append(card);
  });
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

function openEditor(lineupId) {
  window.location.href = `/lineup/${lineupId}/edit`;
}

async function copyLineup(lineup) {
  try {
    await navigator.clipboard.writeText(lineup.code);
  } catch (_) {
  }
  await api(`/api/lineups/${lineup.id}/copy`, { method: 'POST' });
  showMessage('已复制到剪贴板');
  loadLineups();
}

async function likeLineup(lineup) {
  try {
    await api(`/api/lineups/${lineup.id}/like`, { method: 'POST' });
    showMessage('点赞成功');
    loadLineups();
  } catch (error) {
    showMessage(error.message);
  }
}

async function favoriteLineup(lineup) {
  await api(`/api/lineups/${lineup.id}/favorite`, { method: 'POST' });
  showMessage('收藏成功');
  loadLineups();
}

async function reportLineup(lineup) {
  const reason = prompt('请输入举报原因');
  if (!reason) return;
  await api(`/api/lineups/${lineup.id}/report`, { method: 'POST', body: JSON.stringify({ reason }) });
  showMessage('举报已提交');
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

function showMessage(text) {
  elements.message.textContent = text;
  clearTimeout(showMessage.timer);
  showMessage.timer = setTimeout(() => {
    elements.message.textContent = '';
  }, 2600);
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
