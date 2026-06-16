CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL UNIQUE,
    buyer_username VARCHAR(255),
    product_name VARCHAR(255),
    comment TEXT,
    rating_star INTEGER CHECK (rating_star >= 1 AND rating_star <= 5),
    create_time TIMESTAMP,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sentiment VARCHAR(20),
    emotion VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL CHECK (alert_type IN ('rating_drop', 'sentiment_negative')),
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    comment TEXT,
    rating_avg NUMERIC(3,2),
    review_id INTEGER REFERENCES reviews(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS model_metadata (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL,
    f1_score_macro NUMERIC(5,4),
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_reviews_comment_id ON reviews(comment_id);
CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(sentiment);
CREATE INDEX IF NOT EXISTS idx_reviews_rating_star ON reviews(rating_star);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);
CREATE INDEX IF NOT EXISTS idx_model_metadata_is_active ON model_metadata(is_active);
