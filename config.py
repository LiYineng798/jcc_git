import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def apply_config(app, test_config=None):
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, 'lineups.sqlite3'),
        SECRET_KEY=os.environ.get('JCC_SECRET_KEY', 'dev-secret-change-me'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=False,
        ADMIN_USERNAME=os.environ.get('JCC_ADMIN_USERNAME', 'adminxlx'),
        ADMIN_PASSWORD=os.environ.get('JCC_ADMIN_PASSWORD', 'Admin1234'),
    )
    if test_config:
        app.config.update(test_config)
