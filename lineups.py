from datetime import datetime

from flask import Blueprint, jsonify, request

from audit import write_audit
from auth import admin_required, current_user, get_client_ip, login_required
from db import get_db, now_text
from scoring import score_map

lineups_bp = Blueprint('lineups', __name__)


def _bucket_start():
    now = datetime.now()
    minute = (now.minute // 10) * 10
    return now.replace(minute=minute, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')


def _validate_lineup(data):
    name = str(data.get('name', '')).strip()
    code = str(data.get('code', '')).strip()
    if not name or len(name) > 80:
        return None, '请输入阵容名称'
    if not code or len(code) > 20000:
        return None, '请输入阵容码'
    return {'name': name, 'code': code}, None


def _lineup_row(lineup_id):
    return get_db().execute('SELECT * FROM lineups WHERE id = ?', (lineup_id,)).fetchone()


def _parse_positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _serialize(row, scores, user=None, admin=False):
    score = scores.get(row['id'], {'rank_level': 'B', 'like_count': 0, 'copy_count': 0, 'score': 0})
    owner = get_db().execute('SELECT id, nickname, role FROM users WHERE id = ?', (row['user_id'],)).fetchone()
    owner_name = '系统' if owner and owner['role'] == 'admin' else (owner['nickname'] if owner else '未知用户')
    is_owner = bool(user and user['id'] == row['user_id'])
    is_admin = bool(user and user['role'] == 'admin')
    liked = False
    favored = False
    if user:
        today = datetime.now().strftime('%Y-%m-%d')
        liked = bool(get_db().execute(
            'SELECT id FROM likes WHERE user_id = ? AND lineup_id = ? AND like_date = ?',
            (user['id'], row['id'], today),
        ).fetchone())
        favored = bool(get_db().execute(
            'SELECT id FROM favorites WHERE user_id = ? AND lineup_id = ?',
            (user['id'], row['id']),
        ).fetchone())
    data = {
        'id': row['id'],
        'name': row['name'],
        'code': row['code'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'version': row['version'],
        'status': row['status'],
        'owner_nickname': owner_name,
        'rank_level': score['rank_level'],
        'like_count': score['like_count'],
        'copy_count': score['copy_count'],
        'is_liked_today': liked,
        'is_favorited': favored,
        'can_edit': is_owner or is_admin,
        'can_delete': is_owner or is_admin,
        'can_hide': is_admin,
    }
    if admin:
        data['score'] = score['score']
        data['user_id'] = row['user_id']
        data['admin_like_adjustment'] = row['admin_like_adjustment']
        data['admin_copy_adjustment'] = row['admin_copy_adjustment']
    return data


@lineups_bp.get('/api/lineups')
def list_lineups():
    user = current_user()
    view = request.args.get('view', 'all')
    sort = request.args.get('sort', 'latest')
    query = request.args.get('q', '').strip()
    db = get_db()
    clauses = ["l.status = 'normal'"]
    params = []
    if view == 'mine':
        if not user:
            if 'page' in request.args or 'page_size' in request.args:
                page_size = _parse_positive_int(request.args.get('page_size'), 10)
                return jsonify({'items': [], 'total': 0, 'page': 1, 'page_size': page_size, 'total_pages': 1})
            return jsonify([])
        clauses.append('l.user_id = ?')
        params.append(user['id'])
    if query:
        clauses.append('l.name LIKE ?')
        params.append(f'%{query}%')
    sql = 'SELECT l.* FROM lineups l WHERE ' + ' AND '.join(clauses)
    rows = db.execute(sql, params).fetchall()
    scores = score_map()
    payload = [_serialize(row, scores, user=user) for row in rows]
    if sort == 'hot':
        payload.sort(key=lambda item: (-scores.get(item['id'], {}).get('score', 0), item['id']))
    elif sort == 'ss':
        payload = [item for item in payload if item['rank_level'] == 'SS']
        payload.sort(key=lambda item: (-scores.get(item['id'], {}).get('score', 0), item['id']))
    else:
        payload.sort(key=lambda item: (item['updated_at'], item['id']), reverse=True)
    if 'page' in request.args or 'page_size' in request.args:
        page_size = _parse_positive_int(request.args.get('page_size'), 10)
        page = _parse_positive_int(request.args.get('page'), 1)
        total = len(payload)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        start = (page - 1) * page_size
        end = start + page_size
        return jsonify({
            'items': payload[start:end],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        })
    return jsonify(payload)


@lineups_bp.get('/api/lineups/<int:lineup_id>')
def get_lineup(lineup_id):
    user = current_user()
    row = _lineup_row(lineup_id)
    if not row or row['status'] == 'deleted':
        return jsonify({'error': '阵容不存在'}), 404
    if row['status'] != 'normal' and not (user and (user['id'] == row['user_id'] or user['role'] == 'admin')):
        return jsonify({'error': '阵容不存在'}), 404
    return jsonify(_serialize(row, score_map(), user=user, admin=bool(user and user['role'] == 'admin')))


@lineups_bp.post('/api/lineups')
def create_lineup():
    user, error = login_required()
    if error:
        return error
    payload, validation_error = _validate_lineup(request.get_json(silent=True) or {})
    if validation_error:
        return jsonify({'error': validation_error}), 400
    now = now_text()
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO lineups (user_id, name, code, status, created_at, updated_at)
           VALUES (?, ?, ?, 'normal', ?, ?)''',
        (user['id'], payload['name'], payload['code'], now, now),
    )
    write_audit(user['id'], 'create_lineup', 'lineup', cursor.lastrowid, after=payload)
    db.commit()
    return jsonify(_serialize(_lineup_row(cursor.lastrowid), score_map(), user=user)), 201


@lineups_bp.put('/api/lineups/<int:lineup_id>')
def update_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not row or row['status'] == 'deleted':
        return jsonify({'error': '阵容不存在'}), 404
    if row['user_id'] != user['id'] and user['role'] != 'admin':
        return jsonify({'error': '无权修改该阵容'}), 403
    data = request.get_json(silent=True) or {}
    if 'version' in data and int(data['version']) != row['version']:
        return jsonify({'error': '阵容已被更新，请刷新后重试'}), 409
    payload, validation_error = _validate_lineup(data)
    if validation_error:
        return jsonify({'error': validation_error}), 400
    now = now_text()
    get_db().execute(
        'UPDATE lineups SET name = ?, code = ?, updated_at = ?, version = version + 1 WHERE id = ?',
        (payload['name'], payload['code'], now, lineup_id),
    )
    write_audit(user['id'], 'update_lineup', 'lineup', lineup_id, before=dict(row), after=payload)
    get_db().commit()
    return jsonify(_serialize(_lineup_row(lineup_id), score_map(), user=user, admin=user['role'] == 'admin'))


@lineups_bp.delete('/api/lineups/<int:lineup_id>')
def delete_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not row:
        return jsonify({'error': '阵容不存在'}), 404
    if row['user_id'] != user['id'] and user['role'] != 'admin':
        return jsonify({'error': '无权删除该阵容'}), 403
    get_db().execute("UPDATE lineups SET status = 'deleted', updated_at = ? WHERE id = ?", (now_text(), lineup_id))
    write_audit(user['id'], 'delete_lineup', 'lineup', lineup_id, before=dict(row))
    get_db().commit()
    return '', 204


@lineups_bp.post('/api/lineups/<int:lineup_id>/hide')
def hide_lineup(lineup_id):
    admin, error = admin_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not row:
        return jsonify({'error': '阵容不存在'}), 404
    get_db().execute("UPDATE lineups SET status = 'hidden', updated_at = ? WHERE id = ?", (now_text(), lineup_id))
    write_audit(admin['id'], 'hide_lineup', 'lineup', lineup_id, before=dict(row), after={'status': 'hidden'})
    get_db().commit()
    return jsonify({'ok': True})


@lineups_bp.post('/api/lineups/<int:lineup_id>/like')
def like_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    if not _lineup_row(lineup_id):
        return jsonify({'error': '阵容不存在'}), 404
    today = datetime.now().strftime('%Y-%m-%d')
    db = get_db()
    count = db.execute('SELECT COUNT(*) AS c FROM likes WHERE user_id = ? AND like_date = ?', (user['id'], today)).fetchone()['c']
    if count >= 5:
        return jsonify({'error': '今天点赞次数已用完'}), 429
    try:
        db.execute(
            'INSERT INTO likes (user_id, lineup_id, like_date, created_at) VALUES (?, ?, ?, ?)',
            (user['id'], lineup_id, today, now_text()),
        )
        db.commit()
    except Exception:
        db.rollback()
        return jsonify({'error': '今天已经点赞过该阵容'}), 409
    return jsonify({'ok': True, 'lineup': _serialize(_lineup_row(lineup_id), score_map(), user=user)}), 201


@lineups_bp.post('/api/lineups/<int:lineup_id>/copy')
def copy_lineup(lineup_id):
    user = current_user()
    if not _lineup_row(lineup_id):
        return jsonify({'error': '阵容不存在'}), 404
    ip = get_client_ip()
    copy_key = f'user:{user["id"]}' if user else f'ip:{ip}'
    bucket = _bucket_start()
    db = get_db()
    counted = True
    try:
        db.execute(
            '''INSERT INTO copy_events (lineup_id, user_id, ip_address, copy_key, bucket_start, counted, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?)''',
            (lineup_id, user['id'] if user else None, ip, copy_key, bucket, now_text()),
        )
        db.commit()
    except Exception:
        db.rollback()
        counted = False
    return jsonify({'ok': True, 'counted': counted})


@lineups_bp.post('/api/lineups/<int:lineup_id>/favorite')
def favorite_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    if not _lineup_row(lineup_id):
        return jsonify({'error': '阵容不存在'}), 404
    db = get_db()
    db.execute(
        'INSERT OR IGNORE INTO favorites (user_id, lineup_id, created_at) VALUES (?, ?, ?)',
        (user['id'], lineup_id, now_text()),
    )
    db.commit()
    return jsonify({'ok': True})


@lineups_bp.delete('/api/lineups/<int:lineup_id>/favorite')
def unfavorite_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    get_db().execute('DELETE FROM favorites WHERE user_id = ? AND lineup_id = ?', (user['id'], lineup_id))
    get_db().commit()
    return jsonify({'ok': True})


@lineups_bp.post('/api/lineups/<int:lineup_id>/report')
def report_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    reason = str((request.get_json(silent=True) or {}).get('reason', '')).strip()
    if not reason or len(reason) > 300:
        return jsonify({'error': '请输入 1-300 字举报原因'}), 400
    if not _lineup_row(lineup_id):
        return jsonify({'error': '阵容不存在'}), 404
    cursor = get_db().execute(
        'INSERT INTO reports (reporter_user_id, lineup_id, reason, status, created_at) VALUES (?, ?, ?, ?, ?)',
        (user['id'], lineup_id, reason, 'pending', now_text()),
    )
    get_db().commit()
    return jsonify({'id': cursor.lastrowid, 'status': 'pending'}), 201
