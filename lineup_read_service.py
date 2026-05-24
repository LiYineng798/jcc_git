from db import get_db
from lineups_query import (
    build_list_clauses,
    count_lineups,
    fetch_lineup_rows,
    matching_lineup_ids,
    order_by_ids_sql,
)
from lineups_serialization import serialize_lineup_row
from lineups_utils import (
    DEFAULT_LINEUP_SEASON_ID,
    canonical_lineup_season_id,
    lineup_is_visible_to_user,
    lineup_row,
    lineup_season_manifest,
)
from recommendation import recommended_scores
from scoring import rising_map, score_map


def build_lineups_list_payload(user, view, sort, query, season_id, wants_page, page=None, page_size=None):
    if view in {'mine', 'favorites'} and not user:
        if wants_page:
            return {'items': [], 'total': 0, 'page': 1, 'page_size': page_size, 'total_pages': 1}
        return []

    season_id = canonical_lineup_season_id(season_id)
    default_season_id = lineup_season_manifest().get('default_season_id', DEFAULT_LINEUP_SEASON_ID)
    clauses, params = build_list_clauses(user, view, query, season_id, default_season_id)
    scores = score_map()

    if sort in {'hot', 'ss', 'rising', 'recommended'}:
        lineup_ids = matching_lineup_ids(get_db(), clauses, params)
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
        rows = fetch_lineup_rows(
            get_db(),
            clauses,
            params,
            user=user,
            order_by=order_by_ids_sql(page_ids),
            lineup_ids=page_ids,
        )
        rows_by_id = {row['id']: row for row in rows}
        payload = [serialize_lineup_row(rows_by_id[lineup_id], scores, user=user) for lineup_id in page_ids if lineup_id in rows_by_id]
        if wants_page:
            return {
                'items': payload,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
            }
        return payload

    if wants_page:
        total = count_lineups(get_db(), clauses, params)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        start = (page - 1) * page_size
        rows = fetch_lineup_rows(
            get_db(),
            clauses,
            params,
            user=user,
            limit=page_size,
            offset=start,
        )
        payload = [serialize_lineup_row(row, scores, user=user) for row in rows]
        return {
            'items': payload,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        }

    rows = fetch_lineup_rows(get_db(), clauses, params, user=user)
    return [serialize_lineup_row(row, scores, user=user) for row in rows]


def build_lineup_detail_payload(lineup_id, user):
    row = lineup_row(lineup_id)
    if not lineup_is_visible_to_user(row, user):
        return None, '阵容不存在', 404
    return serialize_lineup_row(row, score_map(), user=user, admin=bool(user and user['role'] == 'admin')), None, 200
