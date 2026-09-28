"""Admin-only aggregate stats from Postgres (no image payloads)."""
from __future__ import annotations

from sqlalchemy import text

from db.sync_session import get_sync_sessionmaker


def fetch_user_stats() -> dict:
    Session = get_sync_sessionmaker()
    sql = text(
        """
        SELECT
            u.telegram_id AS user_id,
            u.username,
            u.first_name,
            u.last_name,
            COUNT(i.image_id) FILTER (WHERE i.deleted_at IS NULL)::int AS live_photos,
            COUNT(i.image_id) FILTER (WHERE i.deleted_at IS NOT NULL)::int AS deleted_photos,
            MAX(i.created_at) FILTER (WHERE i.deleted_at IS NULL) AS last_upload
        FROM users u
        LEFT JOIN images i ON i.user_id = u.telegram_id
        GROUP BY u.telegram_id, u.username, u.first_name, u.last_name
        ORDER BY last_upload DESC NULLS LAST, u.telegram_id
        """
    )
    with Session() as session:
        rows = session.execute(sql).mappings().all()

    users = []
    total_live = 0
    total_deleted = 0
    for row in rows:
        live = int(row["live_photos"] or 0)
        deleted = int(row["deleted_photos"] or 0)
        total_live += live
        total_deleted += deleted
        last = row["last_upload"]
        users.append(
            {
                "user_id": int(row["user_id"]),
                "username": row["username"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "live_photos": live,
                "deleted_photos": deleted,
                "last_upload": last.isoformat() if last is not None else None,
            }
        )

    return {
        "users": users,
        "totals": {
            "users": len(users),
            "live_photos": total_live,
            "deleted_photos": total_deleted,
        },
    }
