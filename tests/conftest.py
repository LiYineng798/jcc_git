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
    if db_path.exists():
        db_path.unlink()
    app = create_app({
        'TESTING': True,
        'DATABASE': str(db_path),
        'SECRET_KEY': 'test-secret',
        'WTF_CSRF_ENABLED': True,
        'ADMIN_USERNAME': 'adminxlx',
        'ADMIN_PASSWORD': 'Admin1234',
    })
    yield app
    if db_path.exists():
        db_path.unlink()


@pytest.fixture()
def client(app):
    return app.test_client()
