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

CREATE OR REPLACE FUNCTION notify_alert_inserted()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('alert_inserted', row_to_json(NEW)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_alert_notify ON alerts;
CREATE TRIGGER trg_alert_notify
    AFTER INSERT ON alerts
    FOR EACH ROW
    EXECUTE FUNCTION notify_alert_inserted();
