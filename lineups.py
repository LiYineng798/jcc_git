from datetime import datetime

import re

from flask import Blueprint, jsonify, request

from analytics import record_growth_event, sanitize_growth_payload
from audit import write_audit
from auth import admin_required, current_user, get_client_ip, login_required
from db import get_db, now_text
from history import list_recent_copies, list_recent_views, record_recent_copy, record_recent_view, sync_recent_history
from recommendation import recommended_scores
from scoring import rising_map, score_map
from visits import ensure_visitor_token, maybe_set_visitor_cookie

lineups_bp = Blueprint('lineups', __name__)
LINEUP_CODE_MESSAGE = '阵容码无法解析，请改成以 # 开头的阵容码后再提交'
LINEUP_CODE_PATTERN = re.compile(r'[＃#]([A-Za-z0-9]+)')
LINEUP_VISIBLE_STATUSES = {'normal', 'hidden'}


def _bucket_start():
    now = datetime.now()
    minute = (now.minute // 10) * 10
    return now.replace(minute=minute, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')


def _normalize_lineup_status(raw_status, default='normal'):
    status = str(raw_status or default).strip().lower()
    return status if status in LINEUP_VISIBLE_STATUSES else None


def _validate_lineup(data, default_status='normal'):
    name = str(data.get('name', '')).strip()
    raw_code = str(data.get('code', '')).strip()
    status = _normalize_lineup_status(data.get('status'), default=default_status)
    if not name or len(name) > 80:
        return None, '请输入阵容名称'
    if not raw_code or len(raw_code) > 20000:
        return None, '请输入阵容码'
    if not status:
        return None, '阵容状态无效'
    code = _extract_lineup_code(raw_code)
    if not code:
        return None, LINEUP_CODE_MESSAGE
    return {'name': name, 'code': code, 'status': status}, None


def _extract_lineup_code(raw_code):
    matches = LINEUP_CODE_PATTERN.findall(str(raw_code or ''))
    if not matches:
        return None
    return f'#{max(matches, key=len)}'


def _lineup_row(lineup_id):
    return get_db().execute('SELECT * FROM lineups WHERE id = ?', (lineup_id,)).fetchone()


def _record_authenticated_growth_event(user, event_name, ref_lineup_id=None, payload=None, page_key=None):
    if not user or user['role'] == 'admin':
        return
    visitor_token, _ = ensure_visitor_token()
    record_growth_event(
        event_name=event_name,
        user_id=user['id'],
        visitor_token=visitor_token,
        ip_address=get_client_ip(),
        ref_lineup_id=ref_lineup_id,
        page_key=page_key,
        payload=payload or {},
    )


def _parse_positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _row_value(row, key, default=None):
    if hasattr(row, 'keys') and key in row.keys():
        return row[key]
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def _visibility_clause(user, alias='l'):
    if user and user['role'] == 'admin':
        return f"{alias}.status != 'deleted'", []
    if user:
        return f"({alias}.status = 'normal' OR ({alias}.status = 'hidden' AND {alias}.user_id = ?))", [user['id']]
    return f"{alias}.status = 'normal'", []


def _lineup_is_visible_to_user(row, user):
    if not row or row['status'] == 'deleted':
        return False
    if row['status'] == 'normal':
        return True
    return bool(user and (user['role'] == 'admin' or user['id'] == row['user_id']))


def _list_clauses(user, view, query):
    visibility_clause, visibility_params = _visibility_clause(user, alias='l')
    clauses = [visibility_clause]
    params = list(visibility_params)
    if view == 'mine':
        clauses = ["l.status != 'deleted'"]
        params = []
        clauses.append('l.user_id = ?')
        params.append(user['id'])
    if view == 'favorites':
        clauses.append('EXISTS (SELECT 1 FROM favorites f WHERE f.lineup_id = l.id AND f.user_id = ?)')
        params.append(user['id'])
    if query:
        clauses.append('l.name LIKE ?')
        params.append(f'%{query}%')
    return clauses, params


def _count_lineups(clauses, params):
    sql = 'SELECT COUNT(*) AS total FROM lineups l WHERE ' + ' AND '.join(clauses)
    return get_db().execute(sql, params).fetchone()['total']


def _matching_lineup_ids(clauses, params):
    sql = 'SELECT l.id FROM lineups l WHERE ' + ' AND '.join(clauses)
    rows = get_db().execute(sql, params).fetchall()
    return [row['id'] for row in rows]


def _order_by_ids_sql(lineup_ids):
    if not lineup_ids:
        return 'l.id ASC'
    cases = ' '.join(f'WHEN {int(lineup_id)} THEN {index}' for index, lineup_id in enumerate(lineup_ids))
    return f'CASE l.id {cases} ELSE {len(lineup_ids)} END'


def _fetch_lineup_rows(clauses, params, user=None, order_by='l.updated_at DESC, l.id DESC', limit=None, offset=None, lineup_ids=None):
    joins = ['JOIN users owner ON owner.id = l.user_id']
    select_fields = [
        'l.*',
        'owner.username AS owner_username',
        'owner.nickname AS owner_nickname_raw',
        'owner.role AS owner_role',
    ]
    join_params = []
    if user:
        today = datetime.now().strftime('%Y-%m-%d')
        joins.append('LEFT JOIN likes liked ON liked.lineup_id = l.id AND liked.user_id = ? AND liked.like_date = ?')
        joins.append('LEFT JOIN favorites favored ON favored.lineup_id = l.id AND favored.user_id = ?')
        join_params.extend([user['id'], today, user['id']])
        select_fields.extend([
            'CASE WHEN liked.id IS NULL THEN 0 ELSE 1 END AS is_liked_today',
            'CASE WHEN favored.id IS NULL THEN 0 ELSE 1 END AS is_favorited',
        ])
    else:
        select_fields.extend(['0 AS is_liked_today', '0 AS is_favorited'])

    where_clauses = list(clauses)
    where_params = list(params)
    if lineup_ids is not None:
        if not lineup_ids:
            return []
        placeholders = ','.join('?' for _ in lineup_ids)
        where_clauses.append(f'l.id IN ({placeholders})')
        where_params.extend(lineup_ids)

    sql = 'SELECT ' + ', '.join(select_fields) + ' FROM lineups l ' + ' '.join(joins)
    sql += ' WHERE ' + ' AND '.join(where_clauses)
    sql += f' ORDER BY {order_by}'

    query_params = join_params + where_params
    if limit is not None:
        sql += ' LIMIT ?'
        query_params.append(limit)
    if offset is not None:
        sql += ' OFFSET ?'
        query_params.append(offset)
    return get_db().execute(sql, query_params).fetchall()


def _serialize(row, scores, user=None, admin=False):
    score = scores.get(row['id'], {'rank_level': 'B', 'like_count': 0, 'copy_count': 0, 'score': 0})
    owner_role = _row_value(row, 'owner_role')
    owner_username = _row_value(row, 'owner_username')
    owner_nickname = _row_value(row, 'owner_nickname_raw')
    if owner_role is None and owner_nickname is None and owner_username is None:
        owner = get_db().execute('SELECT id, username, nickname, role FROM users WHERE id = ?', (row['user_id'],)).fetchone()
        owner_role = owner['role'] if owner else None
        owner_username = owner['username'] if owner else None
        owner_nickname = owner['nickname'] if owner else None
    owner_name = '系统' if owner_role == 'admin' else (owner_nickname or '未知用户')
    is_owner = bool(user and user['id'] == row['user_id'])
    is_admin = bool(user and user['role'] == 'admin')
    liked = _row_value(row, 'is_liked_today')
    favored = _row_value(row, 'is_favorited')
    if liked is None:
        liked = False
    else:
        liked = bool(liked)
    if favored is None:
        favored = False
    else:
        favored = bool(favored)
    if user and _row_value(row, 'is_liked_today') is None:
        today = datetime.now().strftime('%Y-%m-%d')
        liked = bool(get_db().execute(
            'SELECT id FROM likes WHERE user_id = ? AND lineup_id = ? AND like_date = ?',
            (user['id'], row['id'], today),
        ).fetchone())
    if user and _row_value(row, 'is_favorited') is None:
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
        'owner_username': owner_username,
        'rank_level': score['rank_level'],
        'like_count': score['like_count'],
        'copy_count': score['copy_count'],
        'is_liked_today': liked,
        'is_favorited': favored,
        'can_edit': is_owner or is_admin,
        'can_delete': is_owner or is_admin,
        'can_hide': row['status'] == 'normal' and (is_owner or is_admin),
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
    if view in {'mine', 'favorites'}:
        if not user:
            if 'page' in request.args or 'page_size' in request.args:
                page_size = _parse_positive_int(request.args.get('page_size'), 10)
                return jsonify({'items': [], 'total': 0, 'page': 1, 'page_size': page_size, 'total_pages': 1})
            return jsonify([])
    clauses, params = _list_clauses(user, view, query)
    scores = score_map()
    wants_page = 'page' in request.args or 'page_size' in request.args
    if wants_page:
        page_size = _parse_positive_int(request.args.get('page_size'), 10)
        page = _parse_positive_int(request.args.get('page'), 1)
    if sort in {'hot', 'ss', 'rising', 'recommended'}:
        lineup_ids = _matching_lineup_ids(clauses, params)
        if sort == 'ss':
            lineup_ids = [lineup_id for lineup_id in lineup_ids if scores.get(lineup_id, {}).get('rank_level') == 'SS']
            lineup_ids.sort(key=lambda lineup_id: (-scores.get(lineup_id, {}).get('score', 0), lineup_id))
        elif sort == 'rising':
            trend_scores = rising_map()
            lineup_ids.sort(key=lambda lineup_id: (-trend_scores.get(lineup_id, 0), -scores.get(lineup_id, {}).get('score', 0), lineup_id))
        elif sort == 'recommended':
            rec_scores = recommended_scores(user=user)
            lineup_ids.sort(key=lambda lineup_id: (-rec_scores.get(lineup_id, 0), -scores.get(lineup_id, {}).get('score', 0), lineup_id))
        else:
            lineup_ids.sort(key=lambda lineup_id: (-scores.get(lineup_id, {}).get('score', 0), lineup_id))
        total = len(lineup_ids)
        if wants_page:
            total_pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, total_pages)
            start = (page - 1) * page_size
            end = start + page_size
            page_ids = lineup_ids[start:end]
        else:
            page_ids = lineup_ids
        rows = _fetch_lineup_rows(
            clauses,
            params,
            user=user,
            order_by=_order_by_ids_sql(page_ids),
            lineup_ids=page_ids,
        )
        rows_by_id = {row['id']: row for row in rows}
        payload = [_serialize(rows_by_id[lineup_id], scores, user=user) for lineup_id in page_ids if lineup_id in rows_by_id]
        if wants_page:
            return jsonify({
                'items': payload,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
            })
        return jsonify(payload)

    if wants_page:
        total = _count_lineups(clauses, params)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        start = (page - 1) * page_size
        end = start + page_size
        rows = _fetch_lineup_rows(
            clauses,
            params,
            user=user,
            limit=page_size,
            offset=start,
        )
        payload = [_serialize(row, scores, user=user) for row in rows]
        return jsonify({
            'items': payload,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        })
    rows = _fetch_lineup_rows(clauses, params, user=user)
    payload = [_serialize(row, scores, user=user) for row in rows]
    return jsonify(payload)


@lineups_bp.get('/api/lineups/<int:lineup_id>')
def get_lineup(lineup_id):
    user = current_user()
    row = _lineup_row(lineup_id)
    if not _lineup_is_visible_to_user(row, user):
        return jsonify({'error': '阵容不存在'}), 404
    return jsonify(_serialize(row, score_map(), user=user, admin=bool(user and user['role'] == 'admin')))


@lineups_bp.get('/api/authors/<username>')
def author_profile(username):
    viewer = current_user()
    author = get_db().execute(
        "SELECT id, username, nickname, role, created_at FROM users WHERE username = ? AND role != 'admin'",
        (username,),
    ).fetchone()
    if not author:
        return jsonify({'error': '作者不存在'}), 404

    rows = get_db().execute(
        '''
        SELECT
            l.*,
            users.username AS owner_username,
            users.nickname AS owner_nickname_raw,
            users.role AS owner_role
        FROM lineups l
        JOIN users ON users.id = l.user_id
        WHERE l.user_id = ? AND l.status = 'normal'
        ORDER BY l.updated_at DESC, l.id DESC
        ''',
        (author['id'],),
    ).fetchall()
    scores = score_map()
    lineups = [_serialize(row, scores, user=viewer) for row in rows]
    return jsonify({
        'profile': {
            'username': author['username'],
            'nickname': author['nickname'],
            'created_at': author['created_at'],
        },
        'summary': {
            'published_lineups': len(lineups),
            'total_likes': sum(item['like_count'] for item in lineups),
            'total_copies': sum(item['copy_count'] for item in lineups),
        },
        'lineups': lineups,
    })


@lineups_bp.post('/api/lineups/<int:lineup_id>/view')
def record_lineup_view(lineup_id):
    user, error = login_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not _lineup_is_visible_to_user(row, user):
        return jsonify({'error': '阵容不存在'}), 404
    record_recent_view(user['id'], lineup_id)
    return jsonify({'ok': True}), 201


@lineups_bp.get('/api/me/recent-views')
def my_recent_views():
    user, error = login_required()
    if error:
        return error
    return jsonify(list_recent_views(user['id'], limit=20, user=user))


@lineups_bp.get('/api/me/recent-copies')
def my_recent_copies():
    user, error = login_required()
    if error:
        return error
    return jsonify(list_recent_copies(user['id'], limit=20, user=user))


@lineups_bp.post('/api/me/history/sync')
def sync_my_history():
    user, error = login_required()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    sync_recent_history(user['id'], payload.get('views', []), payload.get('copies', []))
    return jsonify({'ok': True})


@lineups_bp.get('/api/me/dashboard')
def my_dashboard():
    user, error = login_required()
    if error:
        return error
    db = get_db()
    published_lineups = db.execute(
        "SELECT COUNT(*) AS c FROM lineups WHERE user_id = ? AND status != 'deleted'",
        (user['id'],),
    ).fetchone()['c']
    hidden_lineups = db.execute(
        "SELECT COUNT(*) AS c FROM lineups WHERE user_id = ? AND status = 'hidden'",
        (user['id'],),
    ).fetchone()['c']
    received_likes = db.execute(
        '''
        SELECT COUNT(*) AS c
        FROM likes
        JOIN lineups ON lineups.id = likes.lineup_id
        WHERE lineups.user_id = ?
        ''',
        (user['id'],),
    ).fetchone()['c']
    received_favorites = db.execute(
        '''
        SELECT COUNT(*) AS c
        FROM favorites
        JOIN lineups ON lineups.id = favorites.lineup_id
        WHERE lineups.user_id = ?
        ''',
        (user['id'],),
    ).fetchone()['c']
    received_copies = db.execute(
        '''
        SELECT COUNT(*) AS c
        FROM copy_events
        JOIN lineups ON lineups.id = copy_events.lineup_id
        WHERE lineups.user_id = ? AND copy_events.counted = 1
        ''',
        (user['id'],),
    ).fetchone()['c']
    submitted_reports = db.execute(
        'SELECT COUNT(*) AS c FROM reports WHERE reporter_user_id = ?',
        (user['id'],),
    ).fetchone()['c']
    pending_reports_on_my_lineups = db.execute(
        '''
        SELECT COUNT(*) AS c
        FROM reports
        JOIN lineups ON lineups.id = reports.lineup_id
        WHERE lineups.user_id = ? AND reports.status = 'pending'
        ''',
        (user['id'],),
    ).fetchone()['c']
    return jsonify({
        'published_lineups': published_lineups,
        'hidden_lineups': hidden_lineups,
        'received_likes': received_likes,
        'received_favorites': received_favorites,
        'received_copies': received_copies,
        'submitted_reports': submitted_reports,
        'pending_reports_on_my_lineups': pending_reports_on_my_lineups,
    })


@lineups_bp.get('/api/me/reports')
def my_reports():
    user, error = login_required()
    if error:
        return error
    rows = get_db().execute(
        '''
        SELECT
            reports.id,
            reports.reason,
            reports.status,
            reports.created_at,
            reports.handled_at,
            lineups.id AS lineup_id,
            lineups.name AS lineup_name,
            lineups.status AS lineup_status
        FROM reports
        JOIN lineups ON lineups.id = reports.lineup_id
        WHERE reports.reporter_user_id = ?
        ORDER BY reports.id DESC
        ''',
        (user['id'],),
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@lineups_bp.post('/api/growth-events')
def ingest_growth_event():
    payload, error = sanitize_growth_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify({'error': error}), 400
    user = current_user()
    visitor_token, created = ensure_visitor_token()
    if not (user and user['role'] == 'admin'):
        record_growth_event(
            event_name=payload['event_name'],
            user_id=user['id'] if user else None,
            visitor_token=visitor_token,
            ip_address=get_client_ip(),
            ref_lineup_id=payload['ref_lineup_id'],
            page_key=payload['page_key'],
            payload=payload['payload'],
        )
    response = jsonify({'ok': True})
    return maybe_set_visitor_cookie(response, visitor_token, created), 201


@lineups_bp.post('/api/lineups')
def create_lineup():
    user, error = login_required()
    if error:
        return error
    payload, validation_error = _validate_lineup(request.get_json(silent=True) or {}, default_status='normal')
    if validation_error:
        return jsonify({'error': validation_error}), 400
    now = now_text()
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO lineups (user_id, name, code, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (user['id'], payload['name'], payload['code'], payload['status'], now, now),
    )
    write_audit(user['id'], 'create_lineup', 'lineup', cursor.lastrowid, after=payload)
    db.commit()
    _record_authenticated_growth_event(user, 'post_login_create_lineup', ref_lineup_id=cursor.lastrowid, payload={'status': payload['status']})
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
    payload, validation_error = _validate_lineup(data, default_status=row['status'])
    if validation_error:
        return jsonify({'error': validation_error}), 400
    now = now_text()
    get_db().execute(
        'UPDATE lineups SET name = ?, code = ?, status = ?, updated_at = ?, version = version + 1 WHERE id = ?',
        (payload['name'], payload['code'], payload['status'], now, lineup_id),
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
    user, error = login_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not row or row['status'] == 'deleted':
        return jsonify({'error': '阵容不存在'}), 404
    if row['user_id'] != user['id'] and user['role'] != 'admin':
        return jsonify({'error': '无权隐藏该阵容'}), 403
    if row['status'] != 'hidden':
        get_db().execute("UPDATE lineups SET status = 'hidden', updated_at = ? WHERE id = ?", (now_text(), lineup_id))
        write_audit(user['id'], 'hide_lineup', 'lineup', lineup_id, before=dict(row), after={'status': 'hidden'})
        get_db().commit()
    return jsonify({'ok': True})


@lineups_bp.post('/api/lineups/<int:lineup_id>/like')
def like_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not _lineup_is_visible_to_user(row, user):
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
    _record_authenticated_growth_event(user, 'post_login_like', ref_lineup_id=lineup_id)
    return jsonify({'ok': True, 'lineup': _serialize(_lineup_row(lineup_id), score_map(), user=user)}), 201


@lineups_bp.post('/api/lineups/<int:lineup_id>/copy')
def copy_lineup(lineup_id):
    user = current_user()
    row = _lineup_row(lineup_id)
    if not _lineup_is_visible_to_user(row, user):
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
    if user:
        record_recent_copy(user['id'], lineup_id)
        _record_authenticated_growth_event(user, 'post_login_copy', ref_lineup_id=lineup_id, payload={'counted': counted})
    return jsonify({'ok': True, 'counted': counted})


@lineups_bp.post('/api/lineups/<int:lineup_id>/favorite')
def favorite_lineup(lineup_id):
    user, error = login_required()
    if error:
        return error
    row = _lineup_row(lineup_id)
    if not _lineup_is_visible_to_user(row, user):
        return jsonify({'error': '阵容不存在'}), 404
    db = get_db()
    cursor = db.execute(
        'INSERT OR IGNORE INTO favorites (user_id, lineup_id, created_at) VALUES (?, ?, ?)',
        (user['id'], lineup_id, now_text()),
    )
    db.commit()
    if cursor.rowcount:
        _record_authenticated_growth_event(user, 'post_login_favorite', ref_lineup_id=lineup_id)
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
    row = _lineup_row(lineup_id)
    if not _lineup_is_visible_to_user(row, user):
        return jsonify({'error': '阵容不存在'}), 404
    cursor = get_db().execute(
        'INSERT INTO reports (reporter_user_id, lineup_id, reason, status, created_at) VALUES (?, ?, ?, ?, ?)',
        (user['id'], lineup_id, reason, 'pending', now_text()),
    )
    get_db().commit()
    return jsonify({'id': cursor.lastrowid, 'status': 'pending'}), 201
