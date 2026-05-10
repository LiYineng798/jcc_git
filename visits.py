import secrets
from datetime import datetime, timedelta

from flask import current_app, make_response, render_template, request

from auth import current_user, get_client_ip
from db import get_db, now_text

VISITOR_COOKIE_NAME = 'visitor_token'
VISITOR_COOKIE_MAX_AGE = 180 * 24 * 60 * 60


def resolve_visitor_identity(user, visitor_token, ip_address):
    if user:
        return 'user', f'user:{user["id"]}'
    if visitor_token:
        return 'guest_token', f'guest:{visitor_token}'
    return 'ip_fallback', f'ip:{ip_address or "0.0.0.0"}'


def ensure_visitor_token():
    token = request.cookies.get(VISITOR_COOKIE_NAME, '').strip()
    if token:
        return token, False
    return secrets.token_urlsafe(18), True


def record_page_visit(page_key, user=None, visitor_token=None, ip_address=None):
    user = user or current_user()
    ip_address = ip_address or get_client_ip()
    visitor_kind, visitor_key = resolve_visitor_identity(user, visitor_token, ip_address)
    visit_date = datetime.now().strftime('%Y-%m-%d')
    get_db().execute(
        '''INSERT OR IGNORE INTO visit_events (
               visit_date, visitor_key, visitor_kind, user_id, visitor_token, ip_address, page_key, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            visit_date,
            visitor_key,
            visitor_kind,
            user['id'] if user else None,
            visitor_token,
            ip_address,
            page_key,
            now_text(),
        ),
    )
    get_db().commit()


def tracked_template_response(template_name, page_key, **context):
    user = current_user()
    visitor_token, created = ensure_visitor_token()
    record_page_visit(page_key, user=user, visitor_token=visitor_token, ip_address=get_client_ip())
    response = make_response(render_template(template_name, **context))
    if created:
        response.set_cookie(
            VISITOR_COOKIE_NAME,
            visitor_token,
            max_age=VISITOR_COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
            secure=not current_app.config.get('TESTING', False),
            path='/',
        )
    return response


def daily_uv_count(target_date):
    row = get_db().execute(
        'SELECT COUNT(DISTINCT visitor_key) AS c FROM visit_events WHERE visit_date = ?',
        (target_date,),
    ).fetchone()
    return row['c'] if row else 0


def last_7_days_uv():
    today = datetime.now().date()
    values = []
    for offset in range(6, -1, -1):
        date_value = (today - timedelta(days=offset)).strftime('%Y-%m-%d')
        values.append({'date': date_value, 'uv': daily_uv_count(date_value)})
    return values
