from datetime import datetime, timedelta

from test_admin import login_admin
from test_auth import register_user


def test_home_page_sets_visitor_cookie_and_records_guest_uv(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'visitor_token=' in response.headers.get('Set-Cookie', '')

    with client.application.app_context():
        from db import get_db

        rows = get_db().execute('SELECT visitor_kind, page_key FROM visit_events').fetchall()
        assert len(rows) == 1
        assert rows[0]['visitor_kind'] == 'guest_token'
        assert rows[0]['page_key'] == 'home'


def test_guest_with_cookie_counts_once_per_day(client):
    client.get('/')
    client.get('/')

    with client.application.app_context():
        from db import get_db

        count = get_db().execute("SELECT COUNT(*) AS c FROM visit_events WHERE page_key = 'home'").fetchone()['c']
        assert count == 1


def test_api_requests_do_not_create_visit_rows(client):
    client.get('/api/lineups')

    with client.application.app_context():
        from db import get_db

        count = get_db().execute('SELECT COUNT(*) AS c FROM visit_events').fetchone()['c']
        assert count == 0


def test_logged_in_user_uses_user_identity_for_uv(client):
    register_user(client, username='uvuser', email='uvuser@example.com')
    client.get('/')

    with client.application.app_context():
        from db import get_db

        row = get_db().execute('SELECT visitor_kind, visitor_key FROM visit_events ORDER BY id DESC LIMIT 1').fetchone()
        assert row['visitor_kind'] == 'user'
        assert row['visitor_key'].startswith('user:')


def test_visit_identity_falls_back_to_ip_without_user_or_cookie():
    from visits import resolve_visitor_identity

    visitor_kind, visitor_key = resolve_visitor_identity(None, None, '1.2.3.4')
    assert visitor_kind == 'ip_fallback'
    assert visitor_key == 'ip:1.2.3.4'


def test_admin_stats_include_uv_metrics(client):
    client.get('/')
    register_user(client, username='trend', email='trend@example.com')
    client.get('/')

    with client.application.app_context():
        from db import get_db

        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        get_db().execute('UPDATE visit_events SET visit_date = ? WHERE id = (SELECT MIN(id) FROM visit_events)', (yesterday,))
        get_db().commit()

    headers = login_admin(client)
    data = client.get('/api/admin/stats', headers=headers).get_json()
    assert data['today_uv'] == 1
    assert data['yesterday_uv'] == 1
    assert len(data['last_7_days_uv']) == 7
    assert all('date' in item and 'uv' in item for item in data['last_7_days_uv'])


def test_admin_page_records_visit_for_admin(client):
    login_admin(client)
    response = client.get('/admin')
    assert response.status_code == 200

    with client.application.app_context():
        from db import get_db

        row = get_db().execute(
            'SELECT visitor_kind, page_key FROM visit_events ORDER BY id DESC LIMIT 1'
        ).fetchone()
        assert row['visitor_kind'] == 'user'
        assert row['page_key'] == 'admin'
