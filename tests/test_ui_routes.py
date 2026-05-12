def test_index_uses_top_right_auth_link(client):
    html = client.get('/').get_data(as_text=True)
    assert 'href="/auth"' in html
    assert 'id="loginForm"' not in html
    assert 'id="registerForm"' not in html
    assert 'id="lineupForm"' not in html
    assert 'id="createLineupLink"' in html
    assert 'id="toast"' in html


def test_auth_page_contains_login_and_register_forms(client):
    response = client.get('/auth')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="loginForm"' in html
    assert 'id="registerForm"' in html
    assert 'id="captchaImage"' in html


def test_lineup_editor_pages_exist(client):
    create_response = client.get('/lineup/new')
    edit_response = client.get('/lineup/1/edit')
    assert create_response.status_code == 200
    assert edit_response.status_code == 200
    assert 'id="editorForm"' in create_response.get_data(as_text=True)
    assert 'id="editorForm"' in edit_response.get_data(as_text=True)
    assert 'id="statusToggle"' in create_response.get_data(as_text=True)
    assert '直接展示' in create_response.get_data(as_text=True)
    assert '直接隐藏' in create_response.get_data(as_text=True)
    assert '默认直接展示；开启后会直接隐藏，仅你自己可见' in create_response.get_data(as_text=True)


def test_pages_include_favicon_and_favicon_route_exists(client):
    for path in ['/', '/auth', '/lineup/new', '/lineup/1/edit']:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'rel="icon"' in html
        assert 'href="/static/favicon.png"' in html

    login_response = client.post('/api/login', json={'account': 'adminxlx', 'password': 'Admin1234'})
    assert login_response.status_code == 200
    admin_response = client.get('/admin')
    assert admin_response.status_code == 200
    admin_html = admin_response.get_data(as_text=True)
    assert 'rel="icon"' in admin_html
    assert 'href="/static/favicon.png"' in admin_html
    assert 'id="adminDialogRoot"' in admin_html

    favicon_response = client.get('/favicon.ico')
    assert favicon_response.status_code == 200
    assert favicon_response.mimetype == 'image/vnd.microsoft.icon'


def test_admin_mobile_styles_do_not_force_fixed_height_on_wide_traffic_module():
    with open(r'D:\1\codex\jcc\claude_project\static\styles.css', 'r', encoding='utf-8') as file:
        css = file.read()

    assert '.admin-module:not(.admin-module-wide)' in css


def test_index_page_contains_account_value_copy_and_favorites_tab(client):
    html = client.get('/').get_data(as_text=True)
    assert 'id="favoritesTab"' in html
    assert '登录后可收藏阵容并跨设备同步' in html
    assert '登录后可查看我的收藏和我的阵容' in html


def test_auth_page_contains_account_benefits_copy(client):
    html = client.get('/auth').get_data(as_text=True)
    assert '登录后可收藏阵容并跨设备同步' in html
    assert '登录后可发布和管理自己的阵容' in html
    assert '登录后可查看我的收藏、我的阵容和个人记录' in html


def test_index_and_auth_pages_include_auth_intent_script(client):
    index_html = client.get('/').get_data(as_text=True)
    auth_html = client.get('/auth').get_data(as_text=True)

    assert 'auth-intent.js' in index_html
    assert 'auth-intent.js' in auth_html


def test_index_page_contains_rising_recommended_and_author_link_shell(client):
    html = client.get('/').get_data(as_text=True)
    assert 'data-sort="rising"' in html
    assert 'data-sort="recommended"' in html
    assert 'author-link' in html


def test_index_page_contains_guest_action_prompt_shell(client):
    html = client.get('/').get_data(as_text=True)
    assert 'id="authPromptRoot"' in html


def test_index_page_contains_favorites_empty_state_copy(client):
    html = client.get('/').get_data(as_text=True)
    assert '登录后可收藏阵容并随时找回' in html


def test_app_js_supports_favorite_toggle():
    with open(r'D:\1\codex\jcc\claude_project\static\app.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert '取消收藏' in js
    assert "await api(`/api/lineups/${lineup.id}/favorite`, { method: 'DELETE' });" in js
    assert 'trackGrowth' in js
    assert 'guest_click_like' in js
    assert 'guest_click_favorite' in js


def test_app_js_auth_prompt_copy_is_trimmed():
    with open(r'D:\1\codex\jcc\claude_project\static\app.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert '登录后可收藏阵容、查看我的收藏。' in js
    assert '并自动续上刚才的操作' not in js


def test_lineup_detail_page_exists(client):
    from test_auth import register_user
    from test_lineup_permissions import create_lineup

    register_user(client, username='owner', email='owner@example.com')
    lineup = create_lineup(client, name='详情页阵容', code='#DETAIL001').get_json()
    response = client.get(f"/lineup/{lineup['id']}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="lineupDetailApp"' in html
    assert 'lineup-detail.js' in html


def test_account_page_requires_login_and_contains_shell(client):
    from test_auth import register_user

    assert client.get('/me').status_code == 401
    register_user(client, username='alice', email='alice@example.com')
    response = client.get('/me')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="accountApp"' in html
    assert 'account.js' in html
    assert '我的数据' in html


def test_account_js_contains_dashboard_and_history_sections():
    with open(r'D:\1\codex\jcc\claude_project\static\account.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert '最近浏览' in js
    assert '最近复制' in js
    assert '我的举报' in js
    assert '我的阵容' in js


def test_account_js_contains_report_and_lineup_status_mappings():
    with open(r'D:\1\codex\jcc\claude_project\static\account.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert "pending: '待处理'" in js
    assert "resolved: '已处理'" in js
    assert "dismissed: '已驳回'" in js
    assert "hidden: '已隐藏'" in js


def test_account_js_contains_copy_action_for_recent_history():
    with open(r'D:\1\codex\jcc\claude_project\static\account.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert '复制阵容码' in js
    assert 'copyLineupCode' in js
    assert 'account-list is-scrollable-history' in js


def test_app_js_contains_hide_action_for_admin_lineups():
    with open(r'D:\1\\codex\\jcc\\claude_project\\static\\app.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert 'lineup.can_hide' in js
    assert '隐藏阵容' in js
    assert js.index("actions.append(button('复制阵容码'") < js.index("actions.append(button('查看'")
    assert 'showReportDialog' in js
    assert 'prompt(' not in js


def test_lineup_editor_js_submits_status_field():
    with open(r'D:\1\codex\jcc\claude_project\static\lineup-editor.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert 'statusToggle' in js
    assert "status: elements.statusToggle.checked ? 'hidden' : 'normal'" in js


def test_auth_js_tracks_auth_page_open_growth_event():
    with open(r'D:\1\codex\jcc\claude_project\static\auth.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert 'open_auth_page' in js
    assert '/api/growth-events' in js


def test_author_js_contains_copy_view_like_favorite_and_report_actions():
    with open(r'D:\1\codex\jcc\claude_project\static\author.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert '复制阵容码' in js
    assert '查看' in js
    assert '点赞' in js
    assert '收藏' in js
    assert '举报' in js
    assert 'showAuthPrompt' in js
    assert 'showReportDialog' in js


def test_admin_js_supports_daily_growth_filter_and_clear_labels():
    with open(r'D:\1\codex\jcc\claude_project\static\admin.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert 'growthDate' in js
    assert '/api/admin/growth?date=' in js
    assert '首页访问人数' in js
    assert '点击登录入口人数' in js
    assert '登录后 10 分钟内完成点赞人数' in js


def test_styles_support_history_scroll_and_visibility_toggle():
    with open(r'D:\1\codex\jcc\claude_project\static\styles.css', 'r', encoding='utf-8') as file:
        css = file.read()

    assert '.account-list.is-scrollable-history' in css
    assert '.visibility-toggle' in css


def test_admin_js_renders_lineup_code_in_lineup_management():
    with open(r'D:\1\codex\jcc\claude_project\static\admin.js', 'r', encoding='utf-8') as file:
        js = file.read()

    assert 'lineup.code' in js
