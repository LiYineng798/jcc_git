def test_index_uses_top_right_auth_link(client):
    html = client.get('/').get_data(as_text=True)
    assert 'href="/auth"' in html
    assert 'id="loginForm"' not in html
    assert 'id="registerForm"' not in html
    assert 'id="lineupForm"' not in html
    assert 'id="createLineupLink"' in html


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
