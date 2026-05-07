from test_auth import register_user
from test_lineup_permissions import auth_headers, create_lineup


def test_user_can_like_five_lineups_per_day_and_cannot_unlike(client):
    register_user(client)
    ids = [create_lineup(client, name=f'阵容{i}', code='C').get_json()['id'] for i in range(6)]
    headers = auth_headers(client)
    for lineup_id in ids[:5]:
        assert client.post(f'/api/lineups/{lineup_id}/like', headers=headers).status_code == 201
    assert client.post(f'/api/lineups/{ids[5]}/like', headers=headers).status_code == 429
    assert client.delete(f'/api/lineups/{ids[0]}/like', headers=headers).status_code in {404, 405}


def test_user_can_like_own_lineup(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    data = client.post(f"/api/lineups/{lineup['id']}/like", headers=auth_headers(client)).get_json()
    assert data['lineup']['like_count'] == 1


def test_same_user_same_lineup_like_once_per_day(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    headers = auth_headers(client)
    assert client.post(f"/api/lineups/{lineup['id']}/like", headers=headers).status_code == 201
    assert client.post(f"/api/lineups/{lineup['id']}/like", headers=headers).status_code == 409


def test_anonymous_copy_counts_by_ip_once_per_ten_minutes(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    client.post('/api/logout')
    headers = {'X-Forwarded-For': '1.2.3.4'}
    assert client.post(f"/api/lineups/{lineup['id']}/copy", headers=headers).get_json()['counted'] is True
    assert client.post(f"/api/lineups/{lineup['id']}/copy", headers=headers).get_json()['counted'] is False


def test_logged_in_copy_counts_by_user_once_per_ten_minutes(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    assert client.post(f"/api/lineups/{lineup['id']}/copy", headers=auth_headers(client)).get_json()['counted'] is True
    assert client.post(f"/api/lineups/{lineup['id']}/copy", headers=auth_headers(client)).get_json()['counted'] is False


def test_favorite_does_not_change_score(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    headers = auth_headers(client)
    before = client.get('/api/lineups').get_json()[0]['copy_count'] + client.get('/api/lineups').get_json()[0]['like_count']
    assert client.post(f"/api/lineups/{lineup['id']}/favorite", headers=headers).status_code == 200
    after_payload = client.get('/api/lineups').get_json()[0]
    assert after_payload['is_favorited'] is True
    assert after_payload['copy_count'] + after_payload['like_count'] == before


def test_report_creates_pending_admin_item(client):
    register_user(client)
    lineup = create_lineup(client).get_json()
    response = client.post(f"/api/lineups/{lineup['id']}/report", json={'reason': '无效阵容'}, headers=auth_headers(client))
    assert response.status_code == 201
    client.post('/api/logout')
    client.post('/api/login', json={'account': 'adminxlx', 'password': 'Admin1234'})
    reports = client.get('/api/admin/reports').get_json()
    assert reports[0]['status'] == 'pending'
