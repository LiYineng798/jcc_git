from flask import Blueprint, jsonify, render_template, request
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

from analytics import growth_summary
from audit import write_audit
from auth import admin_required, validate_password
from db import get_db, now_text
from lineups import _lineup_row, _serialize
from scoring import score_map
from visits import daily_uv_count, last_7_days_uv, tracked_template_response

admin_bp = Blueprint('admin', __name__)


def _parse_page():
    try:
        value = int(request.args.get('page', 1))
    except (TypeError, ValueError):
        value = 1
    return value if value > 0 else 1


def _parse_page_size(default=20, maximum=100):
    try:
        value = int(request.args.get('page_size', default))
    except (TypeError, ValueError):
        value = default
    if value <= 0:
        value = default
    return min(value, maximum)


def _paginate_rows(base_sql, count_sql, params, serializer=dict, default_page_size=20):
    page = _parse_page()
    page_size = _parse_page_size(default=default_page_size)
    total = get_db().execute(count_sql, params).fetchone()['c']
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    offset = (page - 1) * page_size
    rows = get_db().execute(f'{base_sql} LIMIT ? OFFSET ?', [*params, page_size, offset]).fetchall()
    return {
        'items': [serializer(row) for row in rows],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
    }


@admin_bp.get('/admin')
def admin_page():
    admin, error = admin_required()
    if error:
        return error
    return tracked_template_response('admin.html', 'admin')


@admin_bp.get('/api/admin/users')
def admin_users():
    admin, error = admin_required()
    if error:
        return error
    q = request.args.get('q', '').strip()
    params = []
    from_sql = 'FROM users'
    if q:
        from_sql += ' WHERE username LIKE ? OR email LIKE ? OR nickname LIKE ?'
        params = [f'%{q}%', f'%{q}%', f'%{q}%']
    base_sql = 'SELECT id, username, email, nickname, role, status, created_at, updated_at, last_login_at ' + from_sql + ' ORDER BY id DESC'
    count_sql = 'SELECT COUNT(*) AS c ' + from_sql
    return jsonify(_paginate_rows(base_sql, count_sql, params, serializer=dict, default_page_size=20))


@admin_bp.post('/api/admin/users')
def admin_create_user():
    admin, error = admin_required()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    password = str(data.get('password') or '')
    if not validate_password(password):
        return jsonify({'error': '密码需大于5位且包含字母和数字'}), 400
    username = str(data.get('username', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    nickname = str(data.get('nickname') or username).strip()
    role = data.get('role') if data.get('role') in {'user', 'admin'} else 'user'
    now = now_text()
    try:
        cursor = get_db().execute(
            '''INSERT INTO users (username, email, nickname, password_hash, role, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?)''',
            (username, email, nickname, generate_password_hash(password), role, now, now),
        )
        write_audit(admin['id'], 'create_user', 'user', cursor.lastrowid, after={'username': username, 'email': email, 'role': role})
        get_db().commit()
    except Exception:
        get_db().rollback()
        return jsonify({'error': '用户名或邮箱已存在'}), 400
    return jsonify({'id': cursor.lastrowid}), 201


@admin_bp.put('/api/admin/users/<int:user_id>')
def admin_update_user(user_id):
    admin, error = admin_required()
    if error:
        return error
    db = get_db()
    before = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not before:
        return jsonify({'error': '用户不存在'}), 404
    data = request.get_json(silent=True) or {}
    fields = []
    params = []
    for key in ['username', 'email', 'nickname', 'role', 'status']:
        if key in data:
            fields.append(f'{key} = ?')
            params.append(str(data[key]).strip())
    if data.get('password'):
        if not validate_password(data['password']):
            return jsonify({'error': '密码需大于5位且包含字母和数字'}), 400
        fields.append('password_hash = ?')
        params.append(generate_password_hash(data['password']))
    if not fields:
        return jsonify({'error': '没有可更新字段'}), 400
    fields.append('updated_at = ?')
    params.extend([now_text(), user_id])
    try:
        db.execute(f'UPDATE users SET {", ".join(fields)} WHERE id = ?', params)
        write_audit(admin['id'], 'update_user', 'user', user_id, before=dict(before), after=data)
        db.commit()
    except Exception:
        db.rollback()
        return jsonify({'error': '用户名或邮箱已存在'}), 400
    return jsonify({'ok': True})


@admin_bp.delete('/api/admin/users/<int:user_id>')
def admin_disable_user(user_id):
    admin, error = admin_required()
    if error:
        return error
    get_db().execute("UPDATE users SET status = 'disabled', updated_at = ? WHERE id = ?", (now_text(), user_id))
    write_audit(admin['id'], 'disable_user', 'user', user_id)
    get_db().commit()
    return '', 204


@admin_bp.get('/api/admin/lineups')
def admin_lineups():
    admin, error = admin_required()
    if error:
        return error
    q = request.args.get('q', '').strip()
    params = []
    from_sql = '''FROM lineups
             LEFT JOIN users ON users.id = lineups.user_id
             WHERE lineups.status != 'deleted' '''
    if q:
        from_sql += ''' AND (
            lineups.name LIKE ? OR lineups.code LIKE ? OR users.username LIKE ? OR users.nickname LIKE ?
        )'''
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'])
    scores = score_map()
    base_sql = 'SELECT lineups.* ' + from_sql + ' ORDER BY lineups.id DESC'
    count_sql = 'SELECT COUNT(*) AS c ' + from_sql
    return jsonify(_paginate_rows(
        base_sql,
        count_sql,
        params,
        serializer=lambda row: _serialize(row, scores, user=admin, admin=True),
        default_page_size=20,
    ))


@admin_bp.put('/api/admin/lineups/<int:lineup_id>')
def admin_update_lineup(lineup_id):
    admin, error = admin_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not row:
        return jsonify({'error': '阵容不存在'}), 404
    data = request.get_json(silent=True) or {}
    fields = []
    params = []
    for key in ['name', 'code', 'status']:
        if key in data:
            fields.append(f'{key} = ?')
            params.append(str(data[key]).strip())
    if not fields:
        return jsonify({'error': '没有可更新字段'}), 400
    fields.append('updated_at = ?')
    fields.append('version = version + 1')
    params.extend([now_text(), lineup_id])
    get_db().execute(f'UPDATE lineups SET {", ".join(fields)} WHERE id = ?', params)
    write_audit(admin['id'], 'admin_update_lineup', 'lineup', lineup_id, before=dict(row), after=data)
    get_db().commit()
    return jsonify(_serialize(_lineup_row(lineup_id), score_map(), user=admin, admin=True))


@admin_bp.post('/api/admin/lineups/<int:lineup_id>/adjust-score')
def admin_adjust_score(lineup_id):
    admin, error = admin_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not row:
        return jsonify({'error': '阵容不存在'}), 404
    data = request.get_json(silent=True) or {}
    like_adjustment = int(data.get('admin_like_adjustment', row['admin_like_adjustment']))
    copy_adjustment = int(data.get('admin_copy_adjustment', row['admin_copy_adjustment']))
    get_db().execute(
        'UPDATE lineups SET admin_like_adjustment = ?, admin_copy_adjustment = ?, updated_at = ? WHERE id = ?',
        (like_adjustment, copy_adjustment, now_text(), lineup_id),
    )
    write_audit(admin['id'], 'adjust_score', 'lineup', lineup_id, before=dict(row), after={'admin_like_adjustment': like_adjustment, 'admin_copy_adjustment': copy_adjustment})
    get_db().commit()
    return jsonify(_serialize(_lineup_row(lineup_id), score_map(), user=admin, admin=True))


@admin_bp.get('/api/admin/stats')
def admin_stats():
    admin, error = admin_required()
    if error:
        return error
    db = get_db()
    today = now_text()[:10]
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    total = db.execute("SELECT COUNT(*) AS c FROM users WHERE role != 'admin'").fetchone()['c']
    today_users = db.execute("SELECT COUNT(*) AS c FROM users WHERE role != 'admin' AND created_at LIKE ?", (f'{today}%',)).fetchone()['c']
    today_logins = db.execute(
        '''
        SELECT COUNT(DISTINCT le.user_id) AS c
        FROM login_events le
        JOIN users u ON u.id = le.user_id
        WHERE le.success = 1
          AND le.created_at LIKE ?
          AND u.role != 'admin'
        ''',
        (f'{today}%',),
    ).fetchone()['c']
    hourly = db.execute("SELECT substr(created_at, 12, 2) AS hour, COUNT(*) AS count FROM users WHERE created_at LIKE ? GROUP BY hour", (f'{today}%',)).fetchall()
    return jsonify({
        'total_users': total,
        'today_users': today_users,
        'today_logins': today_logins,
        'today_uv': daily_uv_count(today),
        'yesterday_uv': daily_uv_count(yesterday),
        'last_7_days_uv': last_7_days_uv(),
        'hourly_registrations': [dict(row) for row in hourly],
    })


@admin_bp.get('/api/admin/overview')
def admin_overview():
    admin, error = admin_required()
    if error:
        return error
    db = get_db()
    today = now_text()[:10]
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    total_users = db.execute("SELECT COUNT(*) AS c FROM users WHERE role != 'admin'").fetchone()['c']
    today_users = db.execute("SELECT COUNT(*) AS c FROM users WHERE role != 'admin' AND created_at LIKE ?", (f'{today}%',)).fetchone()['c']
    today_logins = db.execute(
        '''
        SELECT COUNT(DISTINCT le.user_id) AS c
        FROM login_events le
        JOIN users u ON u.id = le.user_id
        WHERE le.success = 1
          AND le.created_at LIKE ?
          AND u.role != 'admin'
        ''',
        (f'{today}%',),
    ).fetchone()['c']
    pending_reports_count = db.execute("SELECT COUNT(*) AS c FROM reports WHERE status = 'pending'").fetchone()['c']
    hidden_lineups_count = db.execute("SELECT COUNT(*) AS c FROM lineups WHERE status = 'hidden'").fetchone()['c']
    recent_audit_count = db.execute("SELECT COUNT(*) AS c FROM audit_logs WHERE created_at LIKE ?", (f'{today}%',)).fetchone()['c']
    return jsonify({
        'stats': {
            'today_uv': daily_uv_count(today),
            'yesterday_uv': daily_uv_count(yesterday),
            'today_users': today_users,
            'today_logins': today_logins,
            'total_users': total_users,
            'pending_reports_count': pending_reports_count,
        },
        'traffic_7d': last_7_days_uv(),
        'todos': {
            'pending_reports_count': pending_reports_count,
            'hidden_lineups_count': hidden_lineups_count,
            'recent_audit_count': recent_audit_count,
        },
    })


@admin_bp.get('/api/admin/growth')
def admin_growth():
    admin, error = admin_required()
    if error:
        return error
    return jsonify(growth_summary(target_date=request.args.get('date')))


@admin_bp.get('/api/admin/audit-logs')
def admin_audit_logs():
    admin, error = admin_required()
    if error:
        return error
    base_sql = 'SELECT * FROM audit_logs ORDER BY id DESC'
    count_sql = 'SELECT COUNT(*) AS c FROM audit_logs'
    return jsonify(_paginate_rows(base_sql, count_sql, [], serializer=dict, default_page_size=30))


@admin_bp.get('/api/admin/reports')
def admin_reports():
    admin, error = admin_required()
    if error:
        return error
    status = request.args.get('status', 'pending').strip()
    params = []
    from_sql = '''FROM reports
             JOIN users AS reporter ON reporter.id = reports.reporter_user_id
             LEFT JOIN users AS handler ON handler.id = reports.handled_by
             JOIN lineups ON lineups.id = reports.lineup_id
             LEFT JOIN users AS owner ON owner.id = lineups.user_id'''
    if status in {'pending', 'resolved', 'dismissed'}:
        from_sql += ' WHERE reports.status = ?'
        params.append(status)
    base_sql = '''SELECT
                reports.*,
                reporter.username AS reporter_username,
                reporter.nickname AS reporter_nickname,
                handler.username AS handled_by_username,
                handler.nickname AS handled_by_nickname,
                lineups.name AS lineup_name,
                lineups.code AS lineup_code,
                lineups.status AS lineup_status,
                owner.username AS owner_username,
                owner.nickname AS owner_nickname
             ''' + from_sql + ' ORDER BY reports.id DESC'
    count_sql = 'SELECT COUNT(*) AS c ' + from_sql
    return jsonify(_paginate_rows(base_sql, count_sql, params, serializer=dict, default_page_size=20))


@admin_bp.post('/api/admin/reports/<int:report_id>/resolve')
def admin_resolve_report(report_id):
    admin, error = admin_required()
    if error:
        return error
    db = get_db()
    before = db.execute('SELECT * FROM reports WHERE id = ?', (report_id,)).fetchone()
    if not before:
        return jsonify({'error': '举报不存在'}), 404
    data = request.get_json(silent=True) or {}
    status = data.get('status') if data.get('status') in {'resolved', 'dismissed'} else 'resolved'
    hide_lineup = bool(data.get('hide_lineup'))
    now = now_text()
    db.execute('UPDATE reports SET status = ?, handled_at = ?, handled_by = ? WHERE id = ?', (status, now, admin['id'], report_id))
    if hide_lineup:
        db.execute("UPDATE lineups SET status = 'hidden', updated_at = ?, version = version + 1 WHERE id = ?", (now, before['lineup_id']))
    write_audit(admin['id'], 'handle_report', 'report', report_id, before=dict(before), after={'status': status, 'hide_lineup': hide_lineup})
    db.commit()
    return jsonify({'ok': True, 'id': report_id, 'status': status, 'hide_lineup': hide_lineup})
