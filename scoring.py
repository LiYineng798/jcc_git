from datetime import datetime, timedelta
from math import ceil

from db import get_db


def _cutoff(now=None):
    now = now or datetime.now()
    return (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')


def compute_lineup_scores(db=None, now=None):
    db = db or get_db()
    cutoff = _cutoff(now)
    rows = db.execute(
        '''
        SELECT l.id AS lineup_id,
               COALESCE(l.admin_like_adjustment, 0) AS admin_like_adjustment,
               COALESCE(l.admin_copy_adjustment, 0) AS admin_copy_adjustment,
               (SELECT COUNT(*) FROM likes lk WHERE lk.lineup_id = l.id AND lk.created_at >= ?) AS like_count,
               (SELECT COUNT(*) FROM copy_events ce WHERE ce.lineup_id = l.id AND ce.counted = 1 AND ce.created_at >= ?) AS copy_count
        FROM lineups l
        WHERE l.status != 'deleted'
        ''',
        (cutoff, cutoff),
    ).fetchall()
    result = []
    for row in rows:
        likes = row['like_count'] + row['admin_like_adjustment']
        copies = row['copy_count'] + row['admin_copy_adjustment']
        score = max(0, likes) * 5 + max(0, copies)
        result.append({
            'lineup_id': row['lineup_id'],
            'score': score,
            'like_count': max(0, likes),
            'copy_count': max(0, copies),
        })
    return result


def assign_levels(scores):
    positive = sorted([item for item in scores if item['score'] > 0], key=lambda item: (-item['score'], item['lineup_id']))
    levels = {item['lineup_id']: 'B' for item in scores}
    total = len(positive)
    if total == 0:
        return levels
    ss_limit = max(1, ceil(total * 0.05))
    s_limit = max(ss_limit, ceil(total * 0.20))
    a_limit = max(s_limit, ceil(total * 0.50))
    for index, item in enumerate(positive, start=1):
        if index <= ss_limit:
            level = 'SS'
        elif index <= s_limit:
            level = 'S'
        elif index <= a_limit:
            level = 'A'
        else:
            level = 'B'
        levels[item['lineup_id']] = level
    return levels


def score_map(include_counts=True):
    scores = compute_lineup_scores()
    levels = assign_levels(scores)
    data = {}
    for item in scores:
        data[item['lineup_id']] = {
            'score': item['score'],
            'rank_level': levels[item['lineup_id']],
            'like_count': item['like_count'],
            'copy_count': item['copy_count'],
        }
    return data
