from __future__ import annotations

import time
from datetime import datetime, timezone

from app.adapters.epic_games import EpicGamesAdapter
from app.database.connection import connect
from app.database.schema import initialize_database


def _normalized_title(title: str) -> str:
    return " ".join(title.casefold().split())


def run_epic_crawler(max_items: int | None = None) -> dict:
    initialize_database()
    started = time.monotonic()
    offers = EpicGamesAdapter().fetch(max_items=max_items)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = connect()
    saved = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM stores WHERE slug='epic-games' AND enabled=1")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Loja Epic Games não encontrada ou desabilitada na tabela stores.")
        store_id = int(row[0])
        cur.execute("SELECT id FROM platforms WHERE slug='pc'")
        platform_row = cur.fetchone()
        platform_id = int(platform_row[0]) if platform_row else None
        cur.execute("INSERT INTO crawler_runs (store_id,status,started_at) VALUES (%s,'running',%s)",
                    (store_id, now))
        run_id = cur.lastrowid

        for offer in offers:
            canonical_key = f"epic:{offer['external_id']}"
            cur.execute(
                """INSERT INTO games (canonical_key,title,normalized_title,cover_image_url)
                   VALUES (%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE title=VALUES(title), normalized_title=VALUES(normalized_title),
                     cover_image_url=COALESCE(VALUES(cover_image_url),cover_image_url)""",
                (canonical_key, offer["title"], _normalized_title(offer["title"]), offer["banner_img"]),
            )
            cur.execute("SELECT id FROM games WHERE canonical_key=%s", (canonical_key,))
            game_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO free_games (store_id,game_id,external_id,title,banner_img,platform_id,
                     starts_at,ends_at,is_on_banner,status,product_url,last_checked_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE game_id=VALUES(game_id),title=VALUES(title),
                     banner_img=COALESCE(VALUES(banner_img),banner_img),platform_id=VALUES(platform_id),
                     ends_at=VALUES(ends_at),is_on_banner=VALUES(is_on_banner),status=VALUES(status),
                     product_url=VALUES(product_url),last_checked_at=VALUES(last_checked_at)""",
                (store_id, game_id, offer["external_id"], offer["title"], offer["banner_img"], platform_id,
                 offer["starts_at"], offer["ends_at"], int(offer["is_on_banner"]), offer["status"],
                 offer["product_url"], now),
            )
            saved += 1

        duration_ms = int((time.monotonic() - started) * 1000)
        cur.execute(
            """UPDATE crawler_runs SET status='success',items_seen=%s,items_saved=%s,
               duration_ms=%s,finished_at=%s WHERE id=%s""",
            (len(offers), saved, duration_ms, datetime.now(timezone.utc).replace(tzinfo=None), run_id),
        )
        conn.commit()
        return {"seen": len(offers), "saved_or_updated": saved, "duration_ms": duration_ms}
    except Exception as exc:
        conn.rollback()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM stores WHERE slug='epic-games'")
            row = cur.fetchone()
            if row:
                cur.execute(
                    """INSERT INTO crawler_runs (store_id,status,error_message,started_at,finished_at)
                       VALUES (%s,'failed',%s,%s,%s)""",
                    (int(row[0]), str(exc)[:60000], now, datetime.now(timezone.utc).replace(tzinfo=None)),
                )
                conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()
