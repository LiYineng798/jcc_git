from test_auth import register_user


def csrf(client):
    return client.get('/api/me').get_json()['csrf_token']


def auth_headers(client):
    return {'X-CSRF-Token': csrf(client)}


def create_lineup(client, name='阵容A', code='CODE'):
    return client.post('/api/lineups', json={'name': name, 'code': code}, headers=auth_headers(client))


def test_anonymous_can_list_search_and_copy_but_cannot_create_update_delete(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    client.post('/api/logout')
    assert client.get('/api/lineups?q=阵容').status_code == 200
    assert client.post(f"/api/lineups/{lineup['id']}/copy").status_code == 200
    assert client.post('/api/lineups', json={'name': 'x', 'code': 'y'}).status_code == 401
    assert client.put(f"/api/lineups/{lineup['id']}", json={'name': 'x', 'code': 'y'}).status_code == 401
    assert client.delete(f"/api/lineups/{lineup['id']}").status_code == 401


def test_logged_in_user_can_create_lineup_with_owner_id(client):
    register_user(client, nickname='小明')
    response = create_lineup(client)
    data = response.get_json()
    assert response.status_code == 201
    assert data['owner_nickname'] == '小明'
    assert data['can_edit'] is True


def test_user_cannot_edit_or_delete_other_users_lineup(client):
    register_user(client, username='a', email='a@example.com')
    lineup = create_lineup(client).get_json()
    client.post('/api/logout')
    register_user(client, username='b', email='b@example.com')
    assert client.put(f"/api/lineups/{lineup['id']}", json={'name': '改', 'code': 'NEW'}, headers=auth_headers(client)).status_code == 403
    assert client.delete(f"/api/lineups/{lineup['id']}", headers=auth_headers(client)).status_code == 403


def test_admin_can_edit_delete_hide_any_lineup(client):
    register_user(client, username='a', email='a@example.com')
    lineup = create_lineup(client).get_json()
    client.post('/api/logout')
    assert client.post('/api/login', json={'account': 'adminxlx', 'password': 'Admin1234'}).status_code == 200
    headers = auth_headers(client)
    assert client.put(f"/api/lineups/{lineup['id']}", json={'name': '管理员改', 'code': 'ADMIN'}, headers=headers).status_code == 200
    assert client.post(f"/api/lineups/{lineup['id']}/hide", headers=headers).status_code == 200


def test_hidden_lineups_are_not_visible_to_public(client):
    register_user(client, username='a', email='a@example.com')
    lineup = create_lineup(client).get_json()
    client.post('/api/logout')
    client.post('/api/login', json={'account': 'adminxlx', 'password': 'Admin1234'})
    client.post(f"/api/lineups/{lineup['id']}/hide", headers=auth_headers(client))
    client.post('/api/logout')
    assert client.get('/api/lineups').get_json() == []


def test_lineups_endpoint_supports_item_fetch_for_editor(client):
    register_user(client, username='a', email='a@example.com', nickname='作者')
    lineup = create_lineup(client, name='可编辑阵容', code='EDIT-CODE').get_json()
    data = client.get(f"/api/lineups/{lineup['id']}").get_json()
    assert data['id'] == lineup['id']
    assert data['name'] == '可编辑阵容'
    assert data['owner_nickname'] == '作者'


def test_lineups_endpoint_supports_pagination(client):
    register_user(client, username='a', email='a@example.com')
    for index in range(15):
        create_lineup(client, name=f'阵容{index:02d}', code=f'CODE-{index:02d}')
    page_one = client.get('/api/lineups?page=1&page_size=10').get_json()
    page_two = client.get('/api/lineups?page=2&page_size=10').get_json()
    assert page_one['total'] == 15
    assert page_one['page'] == 1
    assert page_one['page_size'] == 10
    assert page_one['total_pages'] == 2
    assert len(page_one['items']) == 10
    assert len(page_two['items']) == 5
    assert page_one['items'][0]['name'] == '阵容14'


def test_lineups_pagination_applies_after_search_filter(client):
    register_user(client, username='a', email='a@example.com')
    for index in range(12):
        create_lineup(client, name=f'法师阵容{index:02d}', code=f'MAGE-{index:02d}')
    create_lineup(client, name='斗士阵容', code='FIGHT')
    page = client.get('/api/lineups?q=法师&page=1&page_size=10').get_json()
    assert page['total'] == 12
    assert page['total_pages'] == 2
    assert len(page['items']) == 10


def test_paginated_logged_in_list_avoids_n_plus_one_queries(client, monkeypatch):
    import db

    register_user(client, username='a', email='a@example.com')
    lineup_ids = []
    for index in range(15):
        lineup_ids.append(create_lineup(client, name=f'阵容{index:02d}', code=f'CODE-{index:02d}').get_json()['id'])

    headers = auth_headers(client)
    for lineup_id in lineup_ids[:3]:
        assert client.post(f'/api/lineups/{lineup_id}/like', headers=headers).status_code == 201
        assert client.post(f'/api/lineups/{lineup_id}/favorite', headers=headers).status_code == 200

    statements = []
    original_connect = db.sqlite3.connect

    def traced_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(db.sqlite3, 'connect', traced_connect)

    response = client.get('/api/lineups?page=1&page_size=10')
    assert response.status_code == 200
    data = response.get_json()
    assert data['total'] == 15
    assert len(data['items']) == 10

    select_statements = [sql for sql in statements if sql.lstrip().upper().startswith('SELECT')]
    assert len(select_statements) <= 6

