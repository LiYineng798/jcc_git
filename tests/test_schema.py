def test_schema_creates_required_tables(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.get_json()['ok'] is True

    table_names = client.application.get_table_names()
    assert 'users' in table_names
    assert 'lineups' in table_names
    assert 'likes' in table_names
    assert 'copy_events' in table_names
    assert 'audit_logs' in table_names
