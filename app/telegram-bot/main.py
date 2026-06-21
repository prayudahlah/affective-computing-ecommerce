import asyncio
import os
from datetime import datetime, timezone

import asyncpg
import httpx

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

DB_CONFIG = {
    "host": os.environ.get("INFERENCE_DB_HOST", "postgres"),
    "port": int(os.environ.get("INFERENCE_DB_PORT", "5432")),
    "user": os.environ.get("INFERENCE_DB_USER", "postgres"),
    "password": os.environ.get("INFERENCE_DB_PASSWORD", "postgres"),
    "database": os.environ.get("INFERENCE_DB_NAME", "postgres"),
}

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "10"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", str(WINDOW_MINUTES * 60)))


async def fetch_window_alerts(conn):
    rows = await conn.fetch("""
        SELECT
            a.id,
            a.alert_type,
            a.triggered_at,
            a.comment,
            a.rating_avg,
            a.review_id,
            r.product_name,
            r.buyer_username,
            r.rating_star,
            r.sentiment,
            r.emotion
        FROM alerts a
        LEFT JOIN reviews r ON a.review_id = r.id
        WHERE a.triggered_at >= NOW() - INTERVAL '10 minutes'
        ORDER BY a.triggered_at
    """)
    return rows


def format_summary(rows, now):
    if not rows:
        return None

    total = len(rows)
    rating_drops = [r for r in rows if r["alert_type"] == "rating_drop"]
    sentiment_neg = [r for r in rows if r["alert_type"] == "sentiment_negative"]

    by_review = {}
    for r in rows:
        rid = r["review_id"]
        if rid not in by_review:
            by_review[rid] = {
                "product_name": r["product_name"] or "Unknown",
                "rating_star": r["rating_star"],
                "comment": r["comment"] or "",
                "sentiment": r["sentiment"] or "Unknown",
                "alert_types": [],
            }
        by_review[rid]["alert_types"].append(r["alert_type"])

    both = [r for r in by_review.values() if len(r["alert_types"]) > 1]

    ratings = [r["rating_star"] for r in by_review.values() if r["rating_star"] is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0

    window_end = now
    window_start = now.replace(minute=((now.minute // WINDOW_MINUTES) * WINDOW_MINUTES), second=0, microsecond=0)

    lines = []
    lines.append(f"\U0001f6a8 *Ringkasan Alert* [{window_start.strftime('%H:%M')} - {window_end.strftime('%H:%M')}]")
    lines.append("\u2501" * 28)
    lines.append(f"\u2b50 *Rating Drop (< 4):* {len(rating_drops)} alert")
    lines.append(f"\U0001f4a2 *Sentimen Negatif:* {len(sentiment_neg)} alert")
    if both:
        lines.append(f"\u26a1 *Keduanya:* {len(both)} review")
    lines.append(f"Rerata rating: \u2b50{avg_rating:.1f}")
    lines.append("")

    for i, (rid, detail) in enumerate(by_review.items(), 1):
        badges = []
        if "rating_drop" in detail["alert_types"]:
            badges.append("\u26a0\ufe0fRating Drop")
        if "sentiment_negative" in detail["alert_types"]:
            badges.append("\u26a0\ufe0fSentimen Negatif")

        line = f"{i}. *{detail['product_name']}* \u2014 \u2b50{detail['rating_star']} {' '.join(badges)}"
        lines.append(line)
        if detail["comment"]:
            preview = detail["comment"][:120].replace("\n", " ")
            if len(detail["comment"]) > 120:
                preview += "..."
            lines.append(f'   \U0001f4ac "{preview}"')
        lines.append(f"   Sentimen: {detail['sentiment']}")
        lines.append("")

    lines.append(f"*Total:* {total} alert dari {len(by_review)} review")

    return "\n".join(lines)


async def send_telegram(message):
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            TELEGRAM_API_URL,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            },
        )
        resp.raise_for_status()


async def process_window():
    now = datetime.now(timezone.utc)
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        rows = await fetch_window_alerts(conn)
        message = format_summary(rows, now)
        if message:
            print(f"[{now.isoformat()}] Sending alert summary ({len(rows)} alerts)")
            await send_telegram(message)
        else:
            print(f"[{now.isoformat()}] No alerts in window")
    except Exception as e:
        print(f"[Telegram Bot] Error: {e}")
    finally:
        await conn.close()


async def main():
    print(f"[Telegram Bot] Starting \u2014 windowing every {WINDOW_MINUTES} minutes")
    while True:
        await process_window()
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
