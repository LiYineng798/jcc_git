import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app


@pytest.fixture()
def app():
    db_path = ROOT / 'test-lineups.sqlite3'
    live_comps_path = ROOT / 'test-live-comps.json'
    live_comps_backup_path = ROOT / 'test-live-comps.previous.json'
    live_comps_asset_dir = ROOT / 'test-live-comps-assets'
    for path in [db_path, live_comps_path, live_comps_backup_path]:
        if path.exists():
            path.unlink()
    if live_comps_asset_dir.exists():
        import shutil
        shutil.rmtree(live_comps_asset_dir)
    app = create_app({
        'TESTING': True,
        'DATABASE': str(db_path),
        'SECRET_KEY': 'test-secret',
        'WTF_CSRF_ENABLED': True,
        'ADMIN_USERNAME': 'adminxlx',
        'ADMIN_PASSWORD': 'Admin1234',
        'LIVE_COMPS_DATA_PATH': str(live_comps_path),
        'LIVE_COMPS_BACKUP_PATH': str(live_comps_backup_path),
        'LIVE_COMPS_PAGE_SIZE': 6,
        'LIVE_COMPS_UPLOAD_TOKEN': 'upload-secret',
        'LIVE_COMPS_ASSET_DIR': str(live_comps_asset_dir),
    })
    yield app
    for path in [db_path, live_comps_path, live_comps_backup_path]:
        if path.exists():
            path.unlink()
    if live_comps_asset_dir.exists():
        import shutil
        shutil.rmtree(live_comps_asset_dir)


@pytest.fixture()
def client(app):
    return app.test_client()
