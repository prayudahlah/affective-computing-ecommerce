-- Schema database PostgreSQL untuk dashboard Streamlit

-- TABEL reviews
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL UNIQUE,
    buyer_username VARCHAR(255),
    product_name VARCHAR(255),
    comment TEXT,
    rating_star INT CHECK (rating_star BETWEEN 1 AND 5),
    create_time TIMESTAMP,
    processed_at TIMESTAMP DEFAULT NOW(),
    sentiment VARCHAR(10) CHECK (sentiment IS NULL OR sentiment IN ('Positive', 'Negative')),
    emotion VARCHAR(20)
);

-- TABEL alerts
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(20) CHECK (alert_type IN ('rating_drop', 'sentiment_negative')),
    triggered_at TIMESTAMP DEFAULT NOW(),
    comment TEXT,
    rating_avg DECIMAL(3,2),
    review_id INT REFERENCES reviews(id) ON DELETE SET NULL
);

-- TABEL model_metadata
CREATE TABLE IF NOT EXISTS model_metadata (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100),
    f1_score_macro DECIMAL(5,4),
    trained_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT FALSE,
    task_type VARCHAR(20) NOT NULL DEFAULT 'sentiment'
);

CREATE INDEX IF NOT EXISTS idx_reviews_comment_id ON reviews(comment_id);
CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(sentiment);
CREATE INDEX IF NOT EXISTS idx_reviews_rating_star ON reviews(rating_star);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);
CREATE INDEX IF NOT EXISTS idx_model_metadata_is_active ON model_metadata(is_active);

INSERT INTO model_metadata (model_name, f1_score_macro, trained_at, is_active, task_type)
VALUES
    ('sentiment_v1', 0.9249, '2026-06-20', TRUE, 'sentiment'),
    ('emotion_v1',   0.67,   '2026-06-20', TRUE, 'emotion')
ON CONFLICT DO NOTHING;

-- Fungsi PL/Python untuk forward alert ke Telegram
-- Dipanggil oleh trigger trg_forward_alert di tabel alerts
CREATE EXTENSION IF NOT EXISTS plpython3u;

CREATE OR REPLACE FUNCTION forward_alert_to_telegram()
RETURNS TRIGGER AS $$

import json
import urllib.request

# ==== KONFIGURASI (dibaca dari custom_params via ALTER SYSTEM) ====
TOKEN = plpy.execute("SELECT current_setting('telegram.bot_token')")[0]['current_setting']
CHAT_ID = plpy.execute("SELECT current_setting('telegram.chat_id')")[0]['current_setting']
# ================================================================

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

DROP TRIGGER IF EXISTS trg_forward_alert ON alerts;
CREATE TRIGGER trg_forward_alert
    AFTER INSERT ON alerts
    FOR EACH ROW
    EXECUTE FUNCTION forward_alert_to_telegram();
