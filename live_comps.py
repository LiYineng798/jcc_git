import json
import os
import shutil
import hashlib
import base64
import urllib.request
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from db import get_db, now_text
from lineup_code import extract_lineup_code

live_comps_bp = Blueprint('live_comps', __name__)

TIER_ORDER = ('S', 'A', 'B', 'C', 'D')
LIVE_COMP_ASSET_ROUTE = '/api/live-comps/assets'
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
CONTENT_TYPE_EXTENSIONS = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
}
DEFAULT_LIVE_COMPS_SEASON_ID = 'default'


def empty_live_comps_payload():
    return {'meta': {}, 'tiers': {tier: [] for tier in TIER_ORDER}}


def validate_live_comps_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('实时阵容数据必须是对象')
    tiers = payload.get('tiers')
    if not isinstance(tiers, dict):
        raise ValueError('实时阵容数据缺少 tiers')
    for tier in TIER_ORDER:
        items = tiers.get(tier, [])
        if not isinstance(items, list):
            raise ValueError(f'{tier} 段位必须是数组')
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('阵容项必须是对象')
            for field in ['id', 'title', 'tier', 'jccCode', 'mainAvatar', 'heroImages']:
                if not item.get(field):
                    raise ValueError(f'缺少字段 {field}')
            if not isinstance(item['heroImages'], list):
                raise ValueError('heroImages 必须是数组')
            if not extract_lineup_code(item.get('jccCode')):
                raise ValueError('jccCode 无法解析')


def normalize_live_comps_payload(payload):
    normalized = {
        'meta': dict(payload.get('meta') or {}),
        'tiers': {},
    }
    for tier in TIER_ORDER:
        normalized_items = []
        for item in payload.get('tiers', {}).get(tier, []):
            normalized_item = dict(item)
            normalized_item['jccCode'] = extract_lineup_code(item.get('jccCode'))
            normalized_items.append(normalized_item)
        normalized['tiers'][tier] = normalized_items
    return normalized


def empty_live_comps_manifest(default_season_id=None):
    season_id = str(default_season_id or current_app.config.get('LIVE_COMPS_DEFAULT_SEASON_ID') or DEFAULT_LIVE_COMPS_SEASON_ID)
    return {
        'default_season_id': season_id,
        'seasons': [
            {
                'id': season_id,
                'name': 'S17 · 星神',
                'status': 'active',
                'order': 1,
                'description': '当前赛季',
                'data_file': 'live-comps.json',
            }
        ],
    }


def manifest_path():
    return Path(current_app.config['LIVE_COMPS_SEASON_MANIFEST_PATH'])


def season_dir():
    return Path(current_app.config['LIVE_COMPS_SEASON_DIR'])


def season_data_filename(season_id):
    safe_id = str(season_id or '').strip() or DEFAULT_LIVE_COMPS_SEASON_ID
    return f'{safe_id}.json'


def season_data_path(season_id):
    safe_id = str(season_id or '').strip() or DEFAULT_LIVE_COMPS_SEASON_ID
    if safe_id == DEFAULT_LIVE_COMPS_SEASON_ID:
        return Path(current_app.config['LIVE_COMPS_DATA_PATH'])
    return season_dir() / season_data_filename(safe_id)


def public_live_comps_manifest(manifest):
    public_statuses = {'active', 'archived'}
    seasons = [season for season in manifest.get('seasons', []) if season.get('status') in public_statuses]
    default_season_id = manifest.get('default_season_id')
    if not any(season['id'] == default_season_id for season in seasons) and seasons:
        default_season_id = seasons[0]['id']
    return {
        'default_season_id': default_season_id,
        'seasons': seasons,
    }


def ensure_live_comps_season(season_id, name=None, status='active'):
    season_id = str(season_id or '').strip()
    if not season_id:
        return load_live_comps_manifest()
    manifest = load_live_comps_manifest()
    if any(season['id'] == season_id for season in manifest['seasons']):
        return manifest
    seasons = list(manifest['seasons'])
    seasons.append({
        'id': season_id,
        'name': name or season_id,
        'status': status,
        'order': max([int(season.get('order') or 0) for season in seasons] or [0]) + 1,
        'description': '',
        'data_file': season_data_filename(season_id),
    })
    return save_live_comps_manifest({
        'default_season_id': manifest.get('default_season_id') or season_id,
        'seasons': seasons,
    })


def normalize_live_comps_manifest(manifest):
    if not isinstance(manifest, dict):
        return empty_live_comps_manifest()
    seasons = manifest.get('seasons')
    if not isinstance(seasons, list) or not seasons:
        return empty_live_comps_manifest(manifest.get('default_season_id'))
    normalized_seasons = []
    for index, season in enumerate(seasons, start=1):
        if not isinstance(season, dict):
            continue
        season_id = str(season.get('id') or '').strip()
        if not season_id:
            continue
        normalized_seasons.append({
            'id': season_id,
            'name': str(season.get('name') or season_id),
            'status': str(season.get('status') or 'active'),
            'order': int(season.get('order') or index),
            'description': str(season.get('description') or ''),
            'data_file': str(season.get('data_file') or season_data_filename(season_id)),
        })
    default_season_id = str(manifest.get('default_season_id') or normalized_seasons[0]['id'])
    if not any(season['id'] == default_season_id for season in normalized_seasons):
        default_season_id = normalized_seasons[0]['id']
    return {
        'default_season_id': default_season_id,
        'seasons': sorted(normalized_seasons, key=lambda season: (season['order'], season['id'])),
    }


def load_live_comps_manifest():
    path = manifest_path()
    if not path.exists():
        return empty_live_comps_manifest()
    try:
        return normalize_live_comps_manifest(json.loads(path.read_text(encoding='utf-8')))
    except Exception:
        return empty_live_comps_manifest()


def save_live_comps_manifest(manifest):
    normalized = normalize_live_comps_manifest(manifest)
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding='utf-8')
    return normalized


def get_live_comps_season(season_id=None):
    manifest = load_live_comps_manifest()
    selected_id = str(season_id or '').strip() or manifest['default_season_id']
    season = next((item for item in manifest['seasons'] if item['id'] == selected_id), None)
    if season is None:
        selected_id = manifest['default_season_id']
        season = next((item for item in manifest['seasons'] if item['id'] == selected_id), None)
    if season is None:
        season = manifest['seasons'][0]
        selected_id = season['id']
    return manifest, season, selected_id


def default_season_file_exists():
    return Path(current_app.config['LIVE_COMPS_DATA_PATH']).exists()


def read_live_comps_payload_for_season(season_id=None):
    manifest = load_live_comps_manifest()
    selected_id = str(season_id or '').strip() or manifest['default_season_id']
    season = next((item for item in manifest['seasons'] if item['id'] == selected_id), None)
    if season is None:
        season = next((item for item in manifest['seasons'] if item['id'] == manifest['default_season_id']), None)
    if season is None:
        season = manifest['seasons'][0]
    data_path = season_data_path(season['id'])
    if not data_path.exists() and season['id'] == manifest['default_season_id']:
        data_path = Path(current_app.config['LIVE_COMPS_DATA_PATH'])
    if not data_path.exists():
        return empty_live_comps_payload(), None, False, manifest, season
    updated_at = datetime.fromtimestamp(data_path.stat().st_mtime).isoformat(timespec='seconds')
    try:
        payload = json.loads(data_path.read_text(encoding='utf-8'))
        validate_live_comps_payload(payload)
        return normalize_live_comps_payload(payload), updated_at, True, manifest, season
    except Exception:
        return empty_live_comps_payload(), updated_at, False, manifest, season


def read_live_comps_payload():
    payload, updated_at, is_valid, _, _ = read_live_comps_payload_for_season()
    return payload, updated_at, is_valid


def build_live_comps_summary(payload, updated_at, is_valid, season=None, manifest=None):
    season_info = season or {}
    manifest = manifest or load_live_comps_manifest()
    return {
        'tiers': [{'tier': tier, 'total': len(payload['tiers'].get(tier, []))} for tier in TIER_ORDER],
        'updated_at': updated_at,
        'season': {
            'id': season_info.get('id') or manifest.get('default_season_id'),
            'name': season_info.get('name') or 'S17 · 星神',
            'status': season_info.get('status') or 'active',
            'description': season_info.get('description') or '',
        },
        'source_meta': {
            **payload.get('meta', {}),
            'is_valid': is_valid,
        },
    }


def is_local_live_comp_asset_url(value):
    return isinstance(value, str) and value.startswith(f'{LIVE_COMP_ASSET_ROUTE}/')


def is_remote_image_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def image_extension_for_url(url, content_type=''):
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        return '.jpg' if suffix == '.jpeg' else suffix
    return CONTENT_TYPE_EXTENSIONS.get(str(content_type or '').split(';', 1)[0].lower(), '.jpg')


def live_comp_asset_filename(url, content_type=''):
    digest = hashlib.sha256(url.encode('utf-8')).hexdigest()
    return f'{digest}{image_extension_for_url(url, content_type)}'


def download_live_comp_image(url):
    request_obj = urllib.request.Request(url, headers={'User-Agent': 'JCC-Lineup-Manager/1.0'})
    with urllib.request.urlopen(request_obj, timeout=15) as response:
        content_type = response.headers.get('Content-Type', '')
        if not str(content_type).lower().startswith('image/'):
            raise ValueError('图片地址返回的不是图片')
        return response.read(), content_type


def cache_live_comp_image(url):
    if is_local_live_comp_asset_url(url) or not is_remote_image_url(url):
        return url
    data, content_type = download_live_comp_image(url)
    filename = live_comp_asset_filename(url, content_type)
    asset_dir = Path(current_app.config['LIVE_COMPS_ASSET_DIR'])
    asset_dir.mkdir(parents=True, exist_ok=True)
    target_path = asset_dir / filename
    if not target_path.exists():
        target_path.write_bytes(data)
    return f'{LIVE_COMP_ASSET_ROUTE}/{filename}'


def validate_live_comp_asset_filename(filename):
    filename = str(filename or '')
    if not filename or Path(filename).name != filename:
        raise ValueError('图片文件名无效')
    if Path(filename).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('图片格式不支持')
    return filename


def write_live_comp_asset(filename, data):
    filename = validate_live_comp_asset_filename(filename)
    asset_dir = Path(current_app.config['LIVE_COMPS_ASSET_DIR'])
    asset_dir.mkdir(parents=True, exist_ok=True)
    target_path = asset_dir / filename
    if not target_path.exists():
        target_path.write_bytes(data)
    return f'{LIVE_COMP_ASSET_ROUTE}/{filename}'


def cache_live_comps_payload_images(payload):
    payload = normalize_live_comps_payload(payload)
    for tier in TIER_ORDER:
        for item in payload['tiers'].get(tier, []):
            item['mainAvatar'] = cache_live_comp_image(item.get('mainAvatar'))
            item['heroImages'] = [cache_live_comp_image(src) for src in item.get('heroImages', [])]
    return payload


def get_live_comps_page(payload, tier, page, page_size):
    items = payload['tiers'].get(tier, [])
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * page_size
    end = start + page_size
    return {
        'tier': tier,
        'items': items[start:end],
        'total': total,
        'page': safe_page,
        'page_size': page_size,
        'total_pages': total_pages,
    }


def flatten_live_comps(payload):
    items = []
    for tier in TIER_ORDER:
        items.extend(payload['tiers'].get(tier, []))
    return items


def find_live_comp(payload, live_comp_id):
    for item in flatten_live_comps(payload):
        if str(item.get('id')) == str(live_comp_id):
            return item
    return None


def load_live_comp_global_stats():
    today = now_text()[:10]
    total_row = get_db().execute(
        '''SELECT total_copy_count, created_at, updated_at
           FROM live_comp_global_stats
           WHERE stats_key = 'global' ''',
    ).fetchone()
    daily_row = get_db().execute(
        '''SELECT copy_count, updated_at
           FROM live_comp_global_daily_stats
           WHERE copy_date = ?''',
        (today,),
    ).fetchone()
    return {
        'today_copy_count': int(daily_row['copy_count']) if daily_row else 0,
        'total_copy_count': int(total_row['total_copy_count']) if total_row else 0,
        'copy_updated_at': (daily_row['updated_at'] if daily_row else None) or (total_row['updated_at'] if total_row else None),
    }


def increment_live_comp_global_copy_count():
    db = get_db()
    now = now_text()
    today = now[:10]
    db.execute(
        '''
        INSERT INTO live_comp_global_stats (stats_key, total_copy_count, created_at, updated_at)
        VALUES ('global', 1, ?, ?)
        ON CONFLICT(stats_key)
        DO UPDATE SET
            total_copy_count = live_comp_global_stats.total_copy_count + 1,
            updated_at = excluded.updated_at
        ''',
        (now, now),
    )
    db.execute(
        '''
        INSERT INTO live_comp_global_daily_stats (copy_date, copy_count, created_at, updated_at)
        VALUES (?, 1, ?, ?)
        ON CONFLICT(copy_date)
        DO UPDATE SET
            copy_count = live_comp_global_daily_stats.copy_count + 1,
            updated_at = excluded.updated_at
        ''',
        (today, now, now),
    )
    db.commit()
    return load_live_comp_global_stats()


def build_admin_live_comp_stats_payload(payload, updated_at, is_valid):
    return {
        'items': [],
        'total': 0,
        'page': 1,
        'page_size': 20,
        'total_pages': 1,
        'updated_at': updated_at,
        'source_meta': {
            **payload.get('meta', {}),
            'is_valid': is_valid,
        },
        **load_live_comp_global_stats(),
    }


def get_combined_live_comps_page(payload, page, page_size):
    items = flatten_live_comps(payload)
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * page_size
    end = start + page_size
    return {
        'items': items[start:end],
        'total': total,
        'page': safe_page,
        'page_size': page_size,
        'total_pages': total_pages,
    }


def parse_positive_int(raw_value, default=1):
    try:
        return max(int(raw_value or default), 1)
    except (TypeError, ValueError):
        return default


def require_live_comps_upload_token():
    expected = current_app.config.get('LIVE_COMPS_UPLOAD_TOKEN', '')
    provided = request.headers.get('X-Upload-Token', '')
    if not expected or provided != expected:
        return jsonify({'error': '上传令牌无效'}), 401
    return None


def write_live_comps_payload(payload):
    write_live_comps_payload_for_season(DEFAULT_LIVE_COMPS_SEASON_ID, payload)


def write_live_comps_payload_for_season(season_id, payload):
    validate_live_comps_payload(payload)
    payload = cache_live_comps_payload_images(payload)
    ensure_live_comps_season(season_id)
    data_path = season_data_path(season_id)
    backup_path = Path(current_app.config['LIVE_COMPS_BACKUP_PATH'])
    data_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = data_path.with_suffix('.tmp')
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    json.loads(temp_path.read_text(encoding='utf-8'))
    if data_path.exists():
        shutil.copyfile(data_path, backup_path)
    os.replace(temp_path, data_path)


@live_comps_bp.get(f'{LIVE_COMP_ASSET_ROUTE}/<path:filename>')
def live_comp_asset(filename):
    return send_from_directory(current_app.config['LIVE_COMPS_ASSET_DIR'], filename)


@live_comps_bp.post('/api/live-comps/assets/upload')
def upload_live_comp_asset():
    auth_error = require_live_comps_upload_token()
    if auth_error:
        return auth_error
    data = request.get_json(silent=True) or {}
    try:
        filename = validate_live_comp_asset_filename(data.get('filename'))
        raw_data = base64.b64decode(str(data.get('content_base64') or ''), validate=True)
        if not raw_data:
            return jsonify({'error': '图片内容为空'}), 400
        url = write_live_comp_asset(filename, raw_data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'url': url, 'filename': filename})


@live_comps_bp.get('/api/live-comps/seasons')
def live_comps_seasons():
    manifest = load_live_comps_manifest()
    return jsonify(public_live_comps_manifest(manifest))


@live_comps_bp.get('/api/live-comps/summary')
def live_comps_summary():
    season_id = request.args.get('season')
    payload, updated_at, is_valid, manifest, season = read_live_comps_payload_for_season(season_id)
    return jsonify(build_live_comps_summary(payload, updated_at, is_valid, season=season, manifest=manifest))


@live_comps_bp.get('/api/live-comps')
def live_comps_list():
    page = parse_positive_int(request.args.get('page'), 1)
    page_size = int(current_app.config['LIVE_COMPS_PAGE_SIZE'])
    season_id = request.args.get('season')
    payload, _, _, _, _ = read_live_comps_payload_for_season(season_id)
    tier = request.args.get('tier')
    if tier:
        tier = tier.upper()
        if tier not in TIER_ORDER:
            return jsonify({'error': '无效段位'}), 400
        return jsonify(get_live_comps_page(payload, tier, page, page_size))
    return jsonify(get_combined_live_comps_page(payload, page, page_size))


@live_comps_bp.post('/api/live-comps/<live_comp_id>/copy')
def copy_live_comp(live_comp_id):
    season_id = request.args.get('season')
    payload, _, _, _, _ = read_live_comps_payload_for_season(season_id)
    if not find_live_comp(payload, live_comp_id):
        return jsonify({'error': '实时阵容不存在'}), 404
    stat = increment_live_comp_global_copy_count()
    return jsonify({
        'ok': True,
        'live_comp_id': str(live_comp_id),
        'today_copy_count': int(stat.get('today_copy_count') or 0),
        'total_copy_count': int(stat.get('total_copy_count') or 0),
    })


@live_comps_bp.post('/api/live-comps/upload')
def upload_live_comps():
    auth_error = require_live_comps_upload_token()
    if auth_error:
        return auth_error
    raw_body = request.get_data(cache=True)
    if len(raw_body) > int(current_app.config['LIVE_COMPS_MAX_UPLOAD_BYTES']):
        return jsonify({'error': '上传文件过大'}), 413
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'error': '请求体必须是 JSON'}), 400
    try:
        season_id = request.args.get('season') or (payload.get('season') if isinstance(payload, dict) else None)
        if season_id:
            write_live_comps_payload_for_season(season_id, payload)
        else:
            write_live_comps_payload(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    counts = {tier: len(payload['tiers'].get(tier, [])) for tier in TIER_ORDER}
    return jsonify({'ok': True, 'tiers': counts, 'total': sum(counts.values())})
