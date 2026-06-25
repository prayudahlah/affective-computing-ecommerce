-- =====================================================
-- Fungsi PL/Python untuk forward alert ke Telegram
-- Dipanggil oleh trigger di tabel alerts
--
-- Cara pakai (oleh Satria):
-- 1. Pastikan plpython3u terinstall:
--    CREATE EXTENSION IF NOT EXISTS plpython3u;
--
-- 2. Jalankan fungsi ini di PostgreSQL laptop 3
--
-- 3. Buat trigger yang manggil fungsi ini:
--    CREATE TRIGGER trg_forward_alert
--        AFTER INSERT ON alerts
--        FOR EACH ROW
--        EXECUTE FUNCTION forward_alert_to_telegram();
--
-- 4. Ganti TOKEN & CHAT_ID di bawah dengan milikmu
--    atau pakai ALTER SYSTEM SET telegram.bot_token = '...'
-- =====================================================

CREATE OR REPLACE FUNCTION forward_alert_to_telegram()
RETURNS TRIGGER AS $$

import json
import urllib.request

# ==== KONFIGURASI ====
TOKEN = "8825916813:AAGEcVG4ySqVfHO8K5ahHa-6OST087iN1Hw"
CHAT_ID = "5519545800"
# =====================

# 1. Ambil data dari TD["new"]
alert_type = TD['new']['alert_type']
comment = (TD['new']['comment'] or '')[:200]
rating_avg = TD['new']['rating_avg']
review_id = TD['new']['review_id']

# 2. JOIN ke tabel reviews ambil info produk
plan = plpy.prepare("""
    SELECT product_name, buyer_username, rating_star, sentiment
    FROM reviews
    WHERE id = $1
""", ["int"])
rows = plpy.execute(plan, [review_id])

if not rows:
    plpy.warning(f"Review {review_id} tidak ditemukan, alert skipped")
    return "OK"

r = rows[0]
product = r['product_name'] or 'Tidak diketahui'
username = r['buyer_username'] or '-'
rating_star = r['rating_star'] or '-'
sentiment = r['sentiment'] or '-'

# 3. Format pesan
msg = None

if alert_type == 'rating_drop':
    msg = (
        f"\U0001f6a8 Rating Drop\n"
        f"Produk: {product}\n"
        f"User: {username}\n"
        f"Rating: \u2b50{rating_star} (avg: {rating_avg})\n"
        f"Sentimen: {sentiment}\n"
        f'\U0001f4ac "{comment}"'
    )

elif alert_type == 'sentiment_negative':
    msg = (
        f"\U0001f6a8 Sentimen Negatif\n"
        f"Produk: {product}\n"
        f"User: {username}\n"
        f"Rating: \u2b50{rating_star}\n"
        f"Sentimen: {sentiment}\n"
        f'\U0001f4ac "{comment}"'
    )

if msg is None:
    plpy.warning(f"Unknown alert_type: {alert_type}")
    return "OK"

# 4. Kirim ke Telegram
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
body = json.dumps({
    "chat_id": CHAT_ID,
    "text": msg
}).encode()

try:
    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': 'application/json'
    })
    resp = urllib.request.urlopen(req, timeout=10)
    plpy.notice(f"Alert sent: {alert_type} for review {review_id}")
except Exception as e:
    plpy.warning(f"Gagal kirim Telegram: {e}")

return "OK"

$$ LANGUAGE plpython3u;
