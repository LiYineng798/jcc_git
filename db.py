import sqlite3
from datetime import datetime

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    nickname TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS lineups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    season_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'normal',
    admin_like_adjustment INTEGER NOT NULL DEFAULT 0,
    admin_copy_adjustment INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    lineup_id INTEGER NOT NULL,
    like_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, lineup_id, like_date),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(lineup_id) REFERENCES lineups(id)
);

CREATE TABLE IF NOT EXISTS copy_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lineup_id INTEGER NOT NULL,
    user_id INTEGER,
    ip_address TEXT,
    copy_key TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    counted INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(lineup_id, copy_key, bucket_start),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(lineup_id) REFERENCES lineups(id)
);

CREATE TABLE IF NOT EXISTS live_comp_global_stats (
    stats_key TEXT PRIMARY KEY,
    total_copy_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_comp_global_daily_stats (
    copy_date TEXT PRIMARY KEY,
    copy_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    lineup_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, lineup_id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(lineup_id) REFERENCES lineups(id)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_user_id INTEGER NOT NULL,
    lineup_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    handled_at TEXT,
    handled_by INTEGER,
    FOREIGN KEY(reporter_user_id) REFERENCES users(id),
    FOREIGN KEY(lineup_id) REFERENCES lineups(id)
);

CREATE TABLE IF NOT EXISTS recent_lineup_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    lineup_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, lineup_id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(lineup_id) REFERENCES lineups(id)
);

CREATE TABLE IF NOT EXISTS recent_lineup_copies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    lineup_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, lineup_id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(lineup_id) REFERENCES lineups(id)
);

CREATE TABLE IF NOT EXISTS login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    ip_address TEXT NOT NULL,
    success INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_date TEXT NOT NULL,
    visitor_key TEXT NOT NULL,
    visitor_kind TEXT NOT NULL,
    user_id INTEGER,
    visitor_token TEXT,
    ip_address TEXT,
    page_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(visit_date, page_key, visitor_key),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    window_start TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    UNIQUE(scope, key, window_start)
);

CREATE TABLE IF NOT EXISTS growth_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    user_id INTEGER,
    visitor_token TEXT,
    ip_address TEXT,
    ref_lineup_id INTEGER,
    page_key TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(ref_lineup_id) REFERENCES lineups(id)
);

CREATE INDEX IF NOT EXISTS idx_growth_events_name_created_at
ON growth_events (event_name, created_at);

CREATE INDEX IF NOT EXISTS idx_growth_events_user_created_at
ON growth_events (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_growth_events_visitor_created_at
ON growth_events (visitor_token, created_at);

CREATE INDEX IF NOT EXISTS idx_likes_lineup_created_at
ON likes (lineup_id, created_at);

CREATE INDEX IF NOT EXISTS idx_copy_events_lineup_created_at
ON copy_events (lineup_id, created_at);
'''


def now_text():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_db():
    if 'db' not in g:
        db = sqlite3.connect(current_app.config['DATABASE'])
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA journal_mode = WAL')
        db.execute('PRAGMA busy_timeout = 5000')
        g.db = db
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    admin_id = bootstrap_admin(db)
    migrate_schema(db, admin_id)
    ensure_indexes(db)
    db.commit()


def bootstrap_admin(db):
    username = current_app.config['ADMIN_USERNAME']
    password = current_app.config['ADMIN_PASSWORD']
    existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        return existing['id']
    now = now_text()
    cursor = db.execute(
        '''INSERT INTO users (username, email, nickname, password_hash, role, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'admin', 'active', ?, ?)''',
        (username, f'{username}@local.admin', '系统', generate_password_hash(password), now, now),
    )
    return cursor.lastrowid


def migrate_schema(db, admin_id):
    migrate_lineups_table(db, admin_id)
    migrate_legacy_live_comp_stats(db)


def migrate_legacy_live_comp_stats(db):
    columns = table_columns(db, 'live_comp_stats')
    if not columns:
        return
    if 'total_copy_count' not in columns:
        db.execute('ALTER TABLE live_comp_stats ADD COLUMN total_copy_count INTEGER NOT NULL DEFAULT 0')
        if 'copy_count' in columns:
            db.execute('UPDATE live_comp_stats SET total_copy_count = copy_count WHERE total_copy_count = 0')
    total_row = db.execute('SELECT COALESCE(SUM(total_copy_count), 0) AS total FROM live_comp_stats').fetchone()
    existing_global = db.execute("SELECT total_copy_count FROM live_comp_global_stats WHERE stats_key = 'global'").fetchone()
    if total_row and total_row['total'] and not existing_global:
        now = now_text()
        db.execute(
            '''INSERT INTO live_comp_global_stats (stats_key, total_copy_count, created_at, updated_at)
               VALUES ('global', ?, ?, ?)''',
            (int(total_row['total']), now, now),
        )


def migrate_lineups_table(db, admin_id):
    columns = table_columns(db, 'lineups')
    if not columns:
        return

    migrations = {
        'user_id': 'ALTER TABLE lineups ADD COLUMN user_id INTEGER',
        'status': "ALTER TABLE lineups ADD COLUMN status TEXT NOT NULL DEFAULT 'normal'",
        'admin_like_adjustment': 'ALTER TABLE lineups ADD COLUMN admin_like_adjustment INTEGER NOT NULL DEFAULT 0',
        'admin_copy_adjustment': 'ALTER TABLE lineups ADD COLUMN admin_copy_adjustment INTEGER NOT NULL DEFAULT 0',
        'version': 'ALTER TABLE lineups ADD COLUMN version INTEGER NOT NULL DEFAULT 1',
        'season_id': "ALTER TABLE lineups ADD COLUMN season_id TEXT NOT NULL DEFAULT 's17-star-god'",
    }

    for column_name, statement in migrations.items():
        if column_name not in columns:
            db.execute(statement)

    db.execute('UPDATE lineups SET user_id = ? WHERE user_id IS NULL', (admin_id,))
    db.execute("UPDATE lineups SET season_id = 's17-star-god' WHERE season_id IS NULL OR season_id = ''")
    db.execute("UPDATE lineups SET season_id = 's16-legends' WHERE season_id = 's16-archive'")


def ensure_indexes(db):
    db.execute('CREATE INDEX IF NOT EXISTS idx_lineups_user_status_updated_at ON lineups (user_id, status, updated_at)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_lineups_season_status_updated_at ON lineups (season_id, status, updated_at)')


def table_columns(db, table_name):
    rows = db.execute(f'PRAGMA table_info({table_name})').fetchall()
    return {row['name'] for row in rows}


def table_names():
    rows = get_db().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row['name'] for row in rows}
