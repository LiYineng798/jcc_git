const root = document.querySelector('.editor-page-shell');
const mode = root?.dataset.pageMode || 'create';
const lineupId = root?.dataset.lineupId || '';
const $ = (selector) => document.querySelector(selector);
const elements = {
  form: $('#editorForm'),
  message: $('#editorMessage'),
  lineupId: $('#lineupId'),
  lineupVersion: $('#lineupVersion'),
  nameInput: $('#nameInput'),
  codeInput: $('#codeInput'),
  submitButton: $('#submitButton'),
  title: $('#editorTitle'),
  description: $('#editorDescription'),
  themeToggle: $('#themeToggle'),
  themeIcon: $('#themeIcon'),
  themeText: $('#themeText'),
};

const state = { user: null, csrfToken: '' };

setTheme(localStorage.getItem('theme') || 'light');
boot();

elements.themeToggle.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
elements.form.addEventListener('submit', saveLineup);

async function boot() {
  await loadMe();
  if (!state.user) {
    showMessage('请先登录后再新增或编辑阵容');
    elements.submitButton.disabled = true;
    return;
  }
  if (mode === 'edit' && lineupId) await loadLineup();
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
}

async function loadLineup() {
  try {
    const lineup = await fetch(`/api/lineups/${lineupId}`).then(async (response) => {
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.error || '加载阵容失败');
      return data;
    });
    if (!lineup.can_edit) throw new Error('你无权编辑该阵容');
    elements.lineupId.value = lineup.id;
    elements.lineupVersion.value = lineup.version;
    elements.nameInput.value = lineup.name;
    elements.codeInput.value = lineup.code;
    elements.title.textContent = '编辑阵容';
    elements.description.textContent = `正在修改「${lineup.name}」，保存后返回阵容列表。`;
  } catch (error) {
    elements.submitButton.disabled = true;
    showMessage(error.message);
  }
}

async function saveLineup(event) {
  event.preventDefault();
  if (!state.user) return;
  const normalizedCode = extractLineupCode(elements.codeInput.value);
  if (!normalizedCode) {
    showMessage('阵容码无法解析，请改成以 # 开头的阵容码后再提交');
    return;
  }
  elements.codeInput.value = normalizedCode;
  const body = {
    name: elements.nameInput.value.trim(),
    code: normalizedCode,
  };
  const isEdit = mode === 'edit' && elements.lineupId.value;
  if (elements.lineupVersion.value) body.version = Number(elements.lineupVersion.value);
  try {
    await api(isEdit ? `/api/lineups/${elements.lineupId.value}` : '/api/lineups', {
      method: isEdit ? 'PUT' : 'POST',
      body: JSON.stringify(body),
    });
    window.location.href = `/?saved=${isEdit ? 'edit' : 'create'}`;
  } catch (error) {
    showMessage(error.message);
  }
}

function showMessage(text) {
  elements.message.textContent = text;
}

function extractLineupCode(rawCode) {
  const matches = Array.from(String(rawCode || '').matchAll(/[＃#]([A-Za-z0-9]+)/g)).map((item) => item[1]);
  if (!matches.length) return '';
  return `#${matches.sort((left, right) => right.length - left.length)[0]}`;
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('theme', theme);
  elements.themeIcon.textContent = theme === 'dark' ? '☼' : '☾';
  elements.themeText.textContent = theme === 'dark' ? '白天模式' : '夜间模式';
}
