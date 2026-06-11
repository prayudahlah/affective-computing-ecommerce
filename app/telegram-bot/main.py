import asyncio
import json
import os

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


def format_alert(payload: dict) -> str:
    alert_type = payload.get("alert_type", "unknown")
    triggered_at = payload.get("triggered_at", "")
    comment = payload.get("comment", "")
    rating_avg = payload.get("rating_avg")
    review_id = payload.get("review_id")

    msg = f"🚨 *Alert: {alert_type}*\n"

    if alert_type == "sentiment_negative" and comment:
        msg += f"💬 *Comment:* {comment}\n"
    if alert_type == "rating_drop" and rating_avg is not None:
        msg += f"⭐ *Avg Rating:* {rating_avg}\n"
    if review_id:
        msg += f"🔗 *Review ID:* {review_id}\n"

    msg += f"🕐 *Time:* {triggered_at}"

    return msg


async def send_telegram(message: str):
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            TELEGRAM_API_URL,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            },
        )


async def handle_notification(payload: str):
    try:
        data = json.loads(payload)
        message = format_alert(data)
        await send_telegram(message)
    except Exception as e:
        print(f"Error handling notification: {e}")


def make_callback():
    loop = asyncio.get_event_loop()

    def callback(connection, pid, channel, payload):
        loop.create_task(handle_notification(payload))

    return callback


async def listen():
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.add_listener("alert_inserted", make_callback())
    print("Listening on channel 'alert_inserted' ...")
    try:
        await asyncio.Event().wait()
    finally:
        await conn.close()


async def main():
    while True:
        try:
            await listen()
        except Exception as e:
            print(f"Connection lost ({e}), reconnecting in 5s ...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
