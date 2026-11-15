from __future__ import annotations

import time
from datetime import datetime, timezone

from app.adapters.steam import SteamAdapter
from app.database.connection import connect
from app.database.schema import initialize_database


def _normalized_title(title: str) -> str:
    return " ".join(title.casefold().split())


def run_steam_crawler(max_items: int | None = None) -> dict:
    initialize_database()
    started = time.monotonic()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    adapter = SteamAdapter()
    deals = adapter.fetch(max_items=max_items)
    conn = connect()
    saved = 0
    store_id = None
    run_id = None
    collection_complete = max_items is None and bool(deals)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM stores WHERE slug='steam' AND enabled=1")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Loja Steam não encontrada ou desabilitada na tabela stores.")
        store_id = int(row[0])
        cur.execute(
            "INSERT INTO crawler_runs (store_id,status,started_at) VALUES (%s,'running',%s)",
            (store_id, now),
        )
        run_id = cur.lastrowid

        collected_ids: list[str] = []
        for deal in deals:
            app_id = deal["external_id"]
            collected_ids.append(app_id)
            canonical_key = f"steam:{app_id}"
            cur.execute(
                """INSERT INTO games (canonical_key,title,normalized_title,steam_app_id,cover_image_url)
                   VALUES (%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE title=VALUES(title), normalized_title=VALUES(normalized_title),
                     steam_app_id=VALUES(steam_app_id), cover_image_url=COALESCE(VALUES(cover_image_url),cover_image_url)""",
                (canonical_key, deal["title"], _normalized_title(deal["title"]), deal["steam_app_id"], deal["image_url"]),
            )
            cur.execute("SELECT id FROM games WHERE canonical_key=%s", (canonical_key,))
            game_id = int(cur.fetchone()[0])

            cur.execute(
                """SELECT id,current_price,original_price,currency,discount_percent
                   FROM deals WHERE store_id=%s AND external_id=%s""",
                (store_id, app_id),
            )
            previous = cur.fetchone()
            cur.execute(
                """INSERT INTO deals (store_id,game_id,external_id,title,product_url,image_url,
                     current_price,original_price,currency,discount_percent,region,activation_platform,
                     available,last_checked_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)
                   ON DUPLICATE KEY UPDATE game_id=VALUES(game_id),title=VALUES(title),
                     product_url=VALUES(product_url),image_url=COALESCE(VALUES(image_url),image_url),
                     current_price=VALUES(current_price),original_price=VALUES(original_price),
                     currency=VALUES(currency),discount_percent=VALUES(discount_percent),region=VALUES(region),
                     activation_platform=VALUES(activation_platform),available=1,last_checked_at=VALUES(last_checked_at)""",
                (store_id, game_id, app_id, deal["title"], deal["url"], deal["image_url"],
                 deal["current_price"], deal["original_price"], deal["currency"], deal["discount_percent"],
                 deal["region"], deal["activation_platform"], now),
            )
            cur.execute("SELECT id FROM deals WHERE store_id=%s AND external_id=%s", (store_id, app_id))
            deal_id = int(cur.fetchone()[0])

            changed = previous is None or (
                previous[1] != deal["current_price"] or previous[2] != deal["original_price"]
                or previous[3] != deal["currency"] or previous[4] != deal["discount_percent"]
            )
            if changed:
                cur.execute(
                    """INSERT INTO price_history (deal_id,price,original_price,currency,discount_percent,collected_at)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (deal_id, deal["current_price"], deal["original_price"], deal["currency"], deal["discount_percent"], now),
                )
            saved += 1

        # Only mark missing deals unavailable after a full successful crawl, never after a limited/test run.
        if collection_complete:
            if collected_ids:
                placeholders = ",".join(["%s"] * len(collected_ids))
                cur.execute(
                    f"UPDATE deals SET available=0,last_checked_at=%s WHERE store_id=%s AND available=1 AND external_id NOT IN ({placeholders})",
                    (now, store_id, *collected_ids),
                )
            else:
                cur.execute("UPDATE deals SET available=0,last_checked_at=%s WHERE store_id=%s", (now, store_id))

        duration_ms = int((time.monotonic() - started) * 1000)
        cur.execute(
            "UPDATE crawler_runs SET status='success',items_seen=%s,items_saved=%s,duration_ms=%s,finished_at=%s WHERE id=%s",
            (len(deals), saved, duration_ms, datetime.now(timezone.utc).replace(tzinfo=None), run_id),
        )
        conn.commit()
        return {"seen": len(deals), "saved_or_updated": saved, "duration_ms": duration_ms}
    except Exception as exc:
        conn.rollback()
        # Record failure separately where possible.
        if store_id is not None:
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO crawler_runs (store_id,status,error_message,started_at,finished_at) VALUES (%s,'failed',%s,%s,%s)",
                    (store_id, str(exc)[:60000], now, datetime.now(timezone.utc).replace(tzinfo=None)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
        raise
    finally:
        conn.close()
