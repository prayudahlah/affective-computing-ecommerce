import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# Koneksi
DB_USER     = os.getenv("INFERENCE_DB_USER",     "postgres")
DB_PASSWORD = os.getenv("INFERENCE_DB_PASSWORD", "postgres")
DB_HOST     = os.getenv("INFERENCE_DB_HOST",     "postgres")
DB_NAME     = os.getenv("INFERENCE_DB_NAME",     "postgres")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DATABASE_URL)


# Helper
def _build_review_filter(filters: dict) -> tuple[str, dict]:
    conditions = []
    params = {}

    if filters.get("date_from"):
        conditions.append("create_time >= :date_from")
        params["date_from"] = filters["date_from"]

    if filters.get("date_to"):
        conditions.append("create_time < :date_to + INTERVAL '1 day'")
        params["date_to"] = filters["date_to"]

    if filters.get("product"):
        conditions.append("product_name = :product")
        params["product"] = filters["product"]

    if filters.get("sentiment"):
        conditions.append("sentiment = ANY(:sentiment)")
        params["sentiment"] = list(filters["sentiment"])

    clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return clause, params


def _build_alert_filter(filters: dict) -> tuple[str, dict]:
    conditions = []
    params = {}

    if filters.get("date_from"):
        conditions.append("triggered_at >= :date_from")
        params["date_from"] = filters["date_from"]

    if filters.get("date_to"):
        conditions.append("triggered_at < :date_to + INTERVAL '1 day'")
        params["date_to"] = filters["date_to"]

    clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return clause, params


# KPI Metrics
@st.cache_data(ttl=5)
def get_kpi_metrics(filters: dict) -> dict:
    where, params = _build_review_filter(filters)
    alert_where, alert_params = _build_alert_filter(filters)
    sql = f"""
        WITH filtered AS (
            SELECT rating_star, sentiment, create_time
            FROM reviews
            {where}
        ),
        today_window AS (
            SELECT rating_star, sentiment
            FROM filtered
            WHERE create_time::date = CURRENT_DATE
        ),
        yesterday_window AS (
            SELECT rating_star, sentiment
            FROM filtered
            WHERE create_time::date = CURRENT_DATE - 1
        ),
        last_10min AS (
            SELECT AVG(rating_star) AS avg_now
            FROM filtered
            WHERE create_time >= NOW() - INTERVAL '10 minutes'
        ),
        prev_10min AS (
            SELECT AVG(rating_star) AS avg_prev
            FROM filtered
            WHERE create_time >= NOW() - INTERVAL '20 minutes'
              AND create_time <  NOW() - INTERVAL '10 minutes'
        ),
        alerts_filtered AS (
            SELECT COUNT(*) AS cnt
            FROM alerts
            {alert_where}
        ),
        active_models AS (
            SELECT task_type, f1_score_macro
            FROM model_metadata
            WHERE is_active = TRUE
        )
        SELECT
            (SELECT COUNT(*) FROM today_window)                                        AS total_today,
            (SELECT COUNT(*) FROM yesterday_window)                                    AS total_yesterday,
            (SELECT COUNT(*) FROM today_window WHERE sentiment = 'Negatif')            AS neg_today,
            (SELECT COUNT(*) FROM yesterday_window WHERE sentiment = 'Negatif')        AS neg_yesterday,
            (SELECT avg_now  FROM last_10min)                                          AS avg_rating_now,
            (SELECT avg_prev FROM prev_10min)                                          AS avg_rating_prev,
            (SELECT cnt FROM alerts_filtered)                                          AS alert_count,
            (SELECT f1_score_macro FROM active_models WHERE task_type = 'sentiment')   AS f1_sentiment,
            (SELECT f1_score_macro FROM active_models WHERE task_type = 'emotion')     AS f1_emotion
    """
    with engine.connect() as conn:
        row = conn.execute(text(sql), {**params, **alert_params}).fetchone()

    total_today     = row[0] or 0
    total_yesterday = row[1] or 0
    neg_today       = row[2] or 0
    neg_yesterday   = row[3] or 0
    avg_now         = float(row[4]) if row[4] is not None else None
    avg_prev        = float(row[5]) if row[5] is not None else None
    alert_count     = row[6] or 0
    f1_sentiment    = float(row[7]) if row[7] is not None else None
    f1_emotion      = float(row[8]) if row[8] is not None else None

    pct_neg_today     = (neg_today     / total_today     * 100) if total_today     > 0 else 0.0
    pct_neg_yesterday = (neg_yesterday / total_yesterday * 100) if total_yesterday > 0 else 0.0

    return {
        "total_today":         total_today,
        "total_delta":         total_today - total_yesterday,
        "pct_negatif":         pct_neg_today,
        "pct_negatif_delta":   round(pct_neg_today - pct_neg_yesterday, 1),
        "avg_rating_now":      avg_now,
        "avg_rating_delta":    round(avg_now - avg_prev, 2) if avg_prev is not None else None,
        "alert_count":         alert_count,
        "f1_sentiment":        f1_sentiment,
        "f1_emotion":          f1_emotion,
    }


# Time Series Rating per 10 menit
@st.cache_data(ttl=5)
def get_time_series_rating(filters: dict) -> pd.DataFrame:
    where, params = _build_review_filter(filters)
    sql = f"""
        SELECT
            date_bin('10 minutes', create_time, TIMESTAMP 'epoch') AS bucket,
            ROUND(AVG(rating_star)::numeric, 2)                    AS avg_rating,
            COUNT(*)                                               AS review_count
        FROM reviews
        {where}
        GROUP BY bucket
        ORDER BY bucket ASC
    """
    with engine.connect() as conn:
        df = pd.DataFrame(
            conn.execute(text(sql), params).fetchall(),
            columns=["bucket", "avg_rating", "review_count"],
        )
    df["avg_rating"] = df["avg_rating"].astype(float)
    return df


# Distribusi Sentimen
@st.cache_data(ttl=5)
def get_sentiment_distribution(filters: dict) -> pd.DataFrame:
    where, params = _build_review_filter(filters)
    sql = f"""
        SELECT sentiment, COUNT(*) AS count
        FROM reviews
        {where}
        GROUP BY sentiment
    """
    with engine.connect() as conn:
        df = pd.DataFrame(
            conn.execute(text(sql), params).fetchall(),
            columns=["sentiment", "count"],
        )
    return df


# Distribusi Emosi
@st.cache_data(ttl=5)
def get_emotion_distribution(filters: dict) -> pd.DataFrame:
    where, params = _build_review_filter(filters)
    sql = f"""
        SELECT emotion, COUNT(*) AS count
        FROM reviews
        {where}
        GROUP BY emotion
        ORDER BY count DESC
    """
    with engine.connect() as conn:
        df = pd.DataFrame(
            conn.execute(text(sql), params).fetchall(),
            columns=["emotion", "count"],
        )
    return df


# Top 5 produk rating terendah
@st.cache_data(ttl=5)
def get_top_products_by_rating(filters: dict, limit: int = 5) -> pd.DataFrame:
    where, params = _build_review_filter(filters)
    sql = f"""
        SELECT
            product_name,
            ROUND(AVG(rating_star)::numeric, 2) AS avg_rating,
            COUNT(*)                             AS total_reviews,
            COUNT(*) FILTER (WHERE sentiment = 'Negatif') AS neg_count
        FROM reviews
        {where}
        GROUP BY product_name
        ORDER BY avg_rating ASC
        LIMIT :limit
    """
    params["limit"] = limit
    with engine.connect() as conn:
        df = pd.DataFrame(
            conn.execute(text(sql), params).fetchall(),
            columns=["product_name", "avg_rating", "total_reviews", "neg_count"],
        )
    df["avg_rating"] = df["avg_rating"].astype(float)
    return df


# Tabel Ulasan (paginasi)
def get_reviews_page(filters: dict, limit: int = 5, offset: int = 0) -> pd.DataFrame:
    where, params = _build_review_filter(filters)
    params["limit"]  = limit
    params["offset"] = offset
    sql = f"""
        SELECT create_time, product_name, comment, rating_star, sentiment, emotion
        FROM reviews
        {where}
        ORDER BY create_time DESC
        LIMIT :limit OFFSET :offset
    """
    with engine.connect() as conn:
        df = pd.DataFrame(
            conn.execute(text(sql), params).fetchall(),
            columns=["create_time", "product_name", "comment", "rating_star", "sentiment", "emotion"],
        )
    return df


def get_total_reviews_count(filters: dict) -> int:
    where, params = _build_review_filter(filters)
    sql = f"SELECT COUNT(*) FROM reviews {where}"
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar() or 0


# Tabel Alert (paginasi)
def get_alerts_page(filters: dict, limit: int = 5, offset: int = 0) -> pd.DataFrame:
    where, params = _build_alert_filter(filters)
    params["limit"]  = limit
    params["offset"] = offset
    sql = f"""
        SELECT triggered_at, alert_type, comment, rating_avg
        FROM alerts
        {where}
        ORDER BY triggered_at DESC
        LIMIT :limit OFFSET :offset
    """
    with engine.connect() as conn:
        df = pd.DataFrame(
            conn.execute(text(sql), params).fetchall(),
            columns=["triggered_at", "alert_type", "comment", "rating_avg"],
        )
    return df


def get_total_alerts_count(filters: dict) -> int:
    where, params = _build_alert_filter(filters)
    sql = f"SELECT COUNT(*) FROM alerts {where}"
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar() or 0


def get_products() -> list[str]:
    sql = "SELECT DISTINCT product_name FROM reviews ORDER BY product_name"
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [row[0] for row in rows]