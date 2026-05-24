from lineup_read_service import build_lineup_detail_payload, build_lineups_list_payload
from test_auth import register_user
from test_lineup_permissions import create_lineup


def test_build_lineups_list_payload_returns_paginated_latest_items(client):
    register_user(client, username='a', email='a@example.com')
    for index in range(3):
        create_lineup(client, name=f'阵容{index}', code=f'#CODE{index}')
    user = client.get('/api/me').get_json()['user']

    with client.application.app_context():
        payload = build_lineups_list_payload(
            user=user,
            view='all',
            sort='latest',
            query='',
            season_id=None,
            wants_page=True,
            page=1,
            page_size=2,
        )

    assert payload['total'] == 3
    assert payload['page'] == 1
    assert payload['page_size'] == 2
    assert len(payload['items']) == 2
    assert payload['items'][0]['name'] == '阵容2'


def test_build_lineups_list_payload_returns_empty_favorites_for_anonymous(client):
    with client.application.app_context():
        payload = build_lineups_list_payload(
            user=None,
            view='favorites',
            sort='latest',
            query='',
            season_id=None,
            wants_page=True,
            page=1,
            page_size=10,
        )

    assert payload == {'items': [], 'total': 0, 'page': 1, 'page_size': 10, 'total_pages': 1}


def test_build_lineup_detail_payload_rejects_hidden_lineup_for_other_user(client):
    register_user(client, username='owner', email='owner@example.com')
    lineup = create_lineup(client, name='隐藏阵容', code='#HIDDEN01', status='hidden').get_json()
    client.post('/api/logout')
    register_user(client, username='viewer', email='viewer@example.com')
    viewer = client.get('/api/me').get_json()['user']

    with client.application.app_context():
        payload, error, status_code = build_lineup_detail_payload(lineup['id'], viewer)

    assert payload is None
    assert status_code == 404
    assert error == '阵容不存在'
