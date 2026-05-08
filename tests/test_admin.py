from test_auth import register_user
from test_lineup_permissions import auth_headers, create_lineup


def login_admin(client):
    client.post('/api/login', json={'account': 'adminxlx', 'password': 'Admin1234'})
    return auth_headers(client)


def test_admin_page_requires_admin_login(client):
    assert client.get('/admin').status_code == 401
    register_user(client)
    assert client.get('/admin').status_code == 403
    client.post('/api/logout')
    login_admin(client)
    assert client.get('/admin').status_code == 200


def test_admin_can_query_users_by_username_or_email(client):
    register_user(client, username='alice', email='alice@example.com')
    client.post('/api/logout')
    headers = login_admin(client)
    data = client.get('/api/admin/users?q=alice', headers=headers).get_json()
    assert data[0]['username'] == 'alice'


def test_admin_can_create_update_disable_delete_users_with_validation(client):
    headers = login_admin(client)
    created = client.post('/api/admin/users', json={'username': 'bob', 'email': 'bob@example.com', 'password': 'abc123', 'nickname': 'Bob'}, headers=headers)
    assert created.status_code == 201
    user_id = created.get_json()['id']
    assert client.put(f'/api/admin/users/{user_id}', json={'nickname': 'Bobby'}, headers=headers).status_code == 200
    assert client.delete(f'/api/admin/users/{user_id}', headers=headers).status_code == 204


def test_admin_can_reset_user_password_and_new_password_takes_effect(client):
    register_user(client, username='alice', email='alice@example.com', password='abc123')
    client.post('/api/logout')

    headers = login_admin(client)
    users = client.get('/api/admin/users?q=alice', headers=headers).get_json()
    user_id = users[0]['id']
    response = client.put(
        f'/api/admin/users/{user_id}',
        json={'password': 'newabc123'},
        headers=headers,
    )
    assert response.status_code == 200

    client.post('/api/logout')
    assert client.post('/api/login', json={'account': 'alice', 'password': 'abc123'}).status_code == 400
    assert client.post('/api/login', json={'account': 'alice', 'password': 'newabc123'}).status_code == 200


def test_admin_can_edit_hide_delete_any_lineup(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    client.post('/api/logout')
    headers = login_admin(client)
    assert client.put(f"/api/admin/lineups/{lineup['id']}", json={'name': 'new'}, headers=headers).status_code == 200
    assert client.put(f"/api/admin/lineups/{lineup['id']}", json={'status': 'hidden'}, headers=headers).status_code == 200


def test_admin_can_adjust_like_and_copy_counts_and_recalculate_score(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    client.post('/api/logout')
    headers = login_admin(client)
    data = client.post(f"/api/admin/lineups/{lineup['id']}/adjust-score", json={'admin_like_adjustment': 1, 'admin_copy_adjustment': 2}, headers=headers).get_json()
    assert data['like_count'] == 1
    assert data['copy_count'] == 2
    assert data['score'] == 7


def test_admin_stats_include_total_users_today_users_today_logins_hourly(client):
    register_user(client)
    client.post('/api/logout')
    headers = login_admin(client)
    data = client.get('/api/admin/stats', headers=headers).get_json()
    assert data['total_users'] == 1
    assert data['today_users'] == 1
    assert 'today_logins' in data
    assert 'hourly_registrations' in data


def test_admin_actions_write_audit_logs(client):
    headers = login_admin(client)
    client.post('/api/admin/users', json={'username': 'eve', 'email': 'eve@example.com', 'password': 'abc123'}, headers=headers)
    logs = client.get('/api/admin/audit-logs', headers=headers).get_json()
    assert logs[0]['action'] == 'create_user'


def test_admin_can_view_report_details_and_resolve_with_hidden_lineup(client):
    register_user(client, username='owner', email='owner@example.com', nickname='作者')
    lineup = create_lineup(client, name='违规阵容', code='#BADCODE').get_json()
    client.post('/api/logout')

    register_user(client, username='reporter', email='reporter@example.com', nickname='举报人')
    report = client.post(
        f"/api/lineups/{lineup['id']}/report",
        json={'reason': '阵容码无效'},
        headers=auth_headers(client),
    )
    assert report.status_code == 201
    report_id = report.get_json()['id']
    client.post('/api/logout')

    headers = login_admin(client)
    reports = client.get('/api/admin/reports', headers=headers).get_json()
    assert reports[0]['id'] == report_id
    assert reports[0]['reason'] == '阵容码无效'
    assert reports[0]['reporter_nickname'] == '举报人'
    assert reports[0]['lineup_name'] == '违规阵容'
    assert reports[0]['lineup_code'] == '#BADCODE'
    assert reports[0]['owner_nickname'] == '作者'

    resolved = client.post(
        f'/api/admin/reports/{report_id}/resolve',
        json={'status': 'resolved', 'hide_lineup': True},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.get_json()['status'] == 'resolved'

    assert client.get('/api/admin/reports', headers=headers).get_json() == []
    updated_report = client.get('/api/admin/reports?status=resolved', headers=headers).get_json()[0]
    assert updated_report['status'] == 'resolved'
    assert updated_report['lineup_status'] == 'hidden'


def test_admin_can_dismiss_report_without_hiding_lineup(client):
    register_user(client, username='owner', email='owner@example.com')
    lineup = create_lineup(client).get_json()
    report = client.post(
        f"/api/lineups/{lineup['id']}/report",
        json={'reason': '误报'},
        headers=auth_headers(client),
    ).get_json()
    client.post('/api/logout')

    headers = login_admin(client)
    response = client.post(
        f"/api/admin/reports/{report['id']}/resolve",
        json={'status': 'dismissed', 'hide_lineup': False},
        headers=headers,
    )
    assert response.status_code == 200
    assert client.get('/api/admin/reports', headers=headers).get_json() == []
    updated_report = client.get('/api/admin/reports?status=dismissed', headers=headers).get_json()[0]
    assert updated_report['status'] == 'dismissed'
    assert updated_report['lineup_status'] == 'normal'


def test_admin_lineup_search_matches_name_code_and_owner(client):
    register_user(client, username='owner', email='owner@example.com', nickname='阵容作者')
    create_lineup(client, name='法师九五', code='#MAGECODE')
    create_lineup(client, name='斗士阵容', code='#FIGHTERCODE')
    client.post('/api/logout')

    headers = login_admin(client)
    by_name = client.get('/api/admin/lineups?q=法师', headers=headers).get_json()
    by_code = client.get('/api/admin/lineups?q=FIGHTER', headers=headers).get_json()
    by_owner = client.get('/api/admin/lineups?q=阵容作者', headers=headers).get_json()

    assert [item['name'] for item in by_name] == ['法师九五']
    assert [item['name'] for item in by_code] == ['斗士阵容']
    assert {item['name'] for item in by_owner} == {'法师九五', '斗士阵容'}


def test_admin_user_search_matches_username_email_and_nickname(client):
    register_user(client, username='alice', email='alice@example.com', nickname='小爱')
    client.post('/api/logout')

    headers = login_admin(client)
    assert client.get('/api/admin/users?q=alice', headers=headers).get_json()[0]['username'] == 'alice'
    assert client.get('/api/admin/users?q=example.com', headers=headers).get_json()[0]['email'] == 'alice@example.com'
    assert client.get('/api/admin/users?q=小爱', headers=headers).get_json()[0]['nickname'] == '小爱'
