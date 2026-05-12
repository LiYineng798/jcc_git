from datetime import datetime, timedelta

from db import get_db
from scoring import score_map


def recommended_scores(user=None):
    db = get_db()
    scores = score_map()
    fresh_cutoff = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    rows = db.execute(
        '''
        SELECT id, user_id, created_at, updated_at
        FROM lineups
        WHERE status = 'normal'
        '''
    ).fetchall()
    data = {}
    for row in rows:
        base = scores.get(row['id'], {}).get('score', 0)
        freshness_bonus = 12 if row['updated_at'] >= fresh_cutoff else 0
        own_penalty = -20 if user and row['user_id'] == user['id'] else 0
        data[row['id']] = base + freshness_bonus + own_penalty
    return data
