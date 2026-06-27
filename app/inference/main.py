import os
import sys
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MLInference")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "cdc.mongodb.ecommerce.reviews")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "ml-inference-group")
SPARK_MASTER_URL = os.getenv("SPARK_MASTER_URL", "spark://spark-master:7077")
SPARK_DRIVER_HOST = os.getenv("SPARK_DRIVER_HOST", "127.0.0.1")
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/app/data/checkpoint")
MODEL_DIR = os.getenv("MODEL_DIR", "/app/models")
POSTGRES_HOST = os.getenv("INFERENCE_DB_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("INFERENCE_DB_HOST_PORT", "5432"))
POSTGRES_DB = os.getenv("INFERENCE_DB_NAME", "postgres")
POSTGRES_JDBC_URL = os.getenv("POSTGRES_JDBC_URL", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
POSTGRES_USER = os.getenv("INFERENCE_DB_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("INFERENCE_DB_PASSWORD", "postgres")

SENTIMENT_MODEL_PATH = os.path.join(MODEL_DIR, "sentiment_inference.joblib")
EMOTION_MODEL_PATH = os.path.join(MODEL_DIR, "emotion_inference.joblib")


def main():
    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql.functions import from_json, col, udf, from_unixtime, coalesce, get_json_object, window, avg, expr
    from pyspark.sql.types import (
        StructType, StructField, StringType, IntegerType,
        FloatType, ArrayType, LongType, TimestampType,
    )
    import joblib

    logger.info("=" * 60)
    logger.info("Spark Structured Streaming — ML Inference")
    logger.info("Kafka:        %s / %s", KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC)
    logger.info("Spark master: %s", SPARK_MASTER_URL)
    logger.info("PostgreSQL:   %s", POSTGRES_JDBC_URL)
    logger.info("Checkpoint:   %s", CHECKPOINT_DIR)
    logger.info("=" * 60)

    spark = (
        SparkSession.builder.appName("StreamMLInference")
        .master(SPARK_MASTER_URL)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.cores.max", "4")
        .config("spark.driver.bindAddress", "0.0.0.0")
        .config("spark.driver.host", SPARK_DRIVER_HOST)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    logger.info("[SPARK] Session created")

    # ── Load models ────────────────────────────────────────────────

    if not os.path.exists(SENTIMENT_MODEL_PATH):
        logger.error("Sentiment model not found at %s", SENTIMENT_MODEL_PATH)
        sys.exit(1)
    if not os.path.exists(EMOTION_MODEL_PATH):
        logger.error("Emotion model not found at %s", EMOTION_MODEL_PATH)
        sys.exit(1)

    sentiment_model = joblib.load(SENTIMENT_MODEL_PATH)
    emotion_model = joblib.load(EMOTION_MODEL_PATH)
    logger.info("[MODEL] Sentiment: %s", type(sentiment_model).__name__)
    logger.info("[MODEL] Emotion: %s", type(emotion_model).__name__)

    sentiment_bc = spark.sparkContext.broadcast(sentiment_model)
    emotion_bc = spark.sparkContext.broadcast(emotion_model)

    # ── Schemas ────────────────────────────────────────────────────

    # Schema for the MongoDB document inside payload.after
    # Note: struct fields from Spark are stored as arrays in MongoDB
    # due to pandas serialization. emotion_features_basic = [n_exc, n_q, n_allcaps, n_el,
    # max_repeat, n_demands, n_unc, n_swear, n_attach, n_repurch, n_trans]
    after_schema = StructType([
        StructField("_id", StringType(), True),
        StructField("nama pengguna", StringType(), True),
        StructField("produk", StringType(), True),
        StructField("review", StringType(), True),
        StructField("rating", IntegerType(), True),
        StructField("ctime", IntegerType(), True),
        StructField("sentiment_vectorized", ArrayType(ArrayType(FloatType())), True),
        StructField("emotion_vectorized", ArrayType(ArrayType(FloatType())), True),
        StructField("emotion_features_basic", ArrayType(IntegerType()), True),
    ])

    # Schema for the Debezium envelope
    envelope_schema = StructType([
        StructField("schema", StringType(), True),
        StructField("payload", StructType([
            StructField("before", StringType(), True),
            StructField("after", StringType(), True),
            StructField("patch", StringType(), True),
            StructField("filter", StringType(), True),
            StructField("updateDescription", StringType(), True),
            StructField("source", StructType([
                StructField("version", StringType(), True),
                StructField("connector", StringType(), True),
                StructField("name", StringType(), True),
                StructField("ts_ms", LongType(), True),
                StructField("snapshot", StringType(), True),
                StructField("db", StringType(), True),
                StructField("sequence", StringType(), True),
                StructField("collection", StringType(), True),
                StructField("ord", IntegerType(), True),
            ]), True),
            StructField("op", StringType(), True),
            StructField("ts_ms", LongType(), True),
            StructField("transaction", StringType(), True),
        ]), True),
    ])

    result_schema = StructType([
        StructField("sentiment_label", StringType(), True),
        StructField("emotion_label", StringType(), True),
    ])

    # ── UDF: predict sentiment and emotion from precomputed features ─

    @udf(result_schema)
    def predict_udf(
        review: str,
        sentiment_vec, emotion_vec,
        basic_features,
    ):
        if not review or not review.strip():
            return (None, None)
        if sentiment_vec is None or emotion_vec is None:
            return None

        import numpy as np
        from scipy.sparse import csr_matrix, hstack

        # Reconstruct 1500-dim sentiment vector
        s_indices = [int(p[0]) for p in sentiment_vec]
        s_values = [float(p[1]) for p in sentiment_vec]
        s_vec = csr_matrix(
            (s_values, ([0] * len(s_indices), s_indices)),
            shape=(1, 1500),
        )

        # 11 basic features from single array
        if basic_features and len(basic_features) >= 11:
            basic_arr = np.array([float(basic_features[i]) for i in range(11)]).reshape(1, 11)
        else:
            basic_arr = np.zeros((1, 11))

        # Predict sentiment: 1500 TF-IDF + 11 basic = 1511
        X_sent = hstack([s_vec, csr_matrix(basic_arr)])
        sent_label = str(sentiment_bc.value.predict(X_sent)[0])

        # Reconstruct 1500-dim emotion vector
        e_indices = [int(p[0]) for p in emotion_vec]
        e_values = [float(p[1]) for p in emotion_vec]
        e_vec = csr_matrix(
            (e_values, ([0] * len(e_indices), e_indices)),
            shape=(1, 1500),
        )

        # Sentiment binary feature
        sent_binary = np.array([[1.0 if sent_label == "Positive" else 0.0]])

        # Combine: 1500 + 11 + 1 = 1512
        dense_part = csr_matrix(np.hstack([basic_arr, sent_binary]))
        X_emo = hstack([e_vec, dense_part])

        emo_label = str(emotion_bc.value.predict(X_emo)[0])

        return (sent_label, emo_label)

    # ── Kafka source ───────────────────────────────────────────────

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", "100")
        .load()
    )

    # ── Parse Debezium envelope ────────────────────────────────────

    parsed_envelope = raw.select(
        from_json(col("value").cast("string"), envelope_schema).alias("envelope")
    ).select("envelope.payload.*")

    # ── Parse after field ──────────────────────────────────────────

    parsed = parsed_envelope.select(
        col("op"),
        col("ts_ms"),
        from_json(col("after"), after_schema).alias("doc"),
        col("after"),
    )

    # ── Filter for insert / snapshot operations ────────────────────

    valid = parsed.where(col("op").isin(["c", "r"])).where(col("doc").isNotNull())

    # ── Apply prediction ──────────────────────────────────────────

    predictions = valid.select(
        coalesce(
            get_json_object(col("after"), "$._id.$oid"),
            col("doc._id"),
        ).alias("comment_id"),
        col("doc.nama pengguna").alias("buyer_username"),
        col("doc.produk").alias("product_name"),
        col("doc.review").alias("comment"),
        col("doc.rating").alias("rating_star"),
        col("doc.ctime").alias("create_time_ts"),
        predict_udf(
            col("doc.review"),
            col("doc.sentiment_vectorized"),
            col("doc.emotion_vectorized"),
            col("doc.emotion_features_basic"),
        ).alias("result"),
    ).select(
        col("comment_id"),
        col("buyer_username"),
        col("product_name"),
        col("comment"),
        col("rating_star"),
        from_unixtime(col("create_time_ts")).alias("create_time"),
        col("result.sentiment_label").alias("sentiment"),
        col("result.emotion_label").alias("emotion"),
    )

    # ── foreachBatch: write to PostgreSQL ──────────────────────────

    def write_to_postgres(df: DataFrame, epoch_id: int):
        count = df.count()
        if count == 0:
            logger.info("[EPOCH %d] No records to write", epoch_id)
            return
        logger.info("[EPOCH %d] Writing %d predictions to PostgreSQL", epoch_id, count)
        import psycopg2
        rows = df.collect()
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
        )
        try:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute("""
                        INSERT INTO reviews
                            (comment_id, buyer_username, product_name, comment,
                             rating_star, create_time, sentiment, emotion)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (comment_id) DO UPDATE SET
                            sentiment = EXCLUDED.sentiment,
                            emotion = EXCLUDED.emotion,
                            processed_at = CURRENT_TIMESTAMP
                        RETURNING id
                    """, (
                        row.comment_id, row.buyer_username, row.product_name,
                        row.comment, row.rating_star, row.create_time,
                        row.sentiment, row.emotion,
                    ))
                    review_id = cur.fetchone()[0]
                    if row.sentiment == 'Negative' or row.emotion in ('Fear', 'Anger', 'Sadness'):
                        logger.info("[ALERT] Sentimen negatif terdeteksi: %s", row.comment_id)
                        cur.execute("""
                            INSERT INTO alerts (alert_type, comment, review_id)
                            VALUES ('sentiment_negative', %s, %s)
                        """, (row.comment, review_id))
            conn.commit()
            logger.info("[EPOCH %d] Upserted %d rows, alerts: %s", epoch_id, len(rows), count)
        finally:
            conn.close()

    # ── Start streaming ───────────────────────────────────────────

    pg_query = (
        predictions.writeStream.foreachBatch(write_to_postgres)
        .outputMode("append")
        .option("checkpointLocation", CHECKPOINT_DIR + "/postgres")
        .trigger(processingTime="10 seconds")
        .start()
    )

    debug_query = (
        predictions.writeStream.format("console")
        .outputMode("append")
        .option("checkpointLocation", CHECKPOINT_DIR + "/console_debug")
        .trigger(processingTime="10 seconds")
        .start()
    )

    recent_ratings = (
        predictions
        .withColumn("ts", col("create_time").cast(TimestampType()))
        .filter(col("ts") >= expr("current_timestamp() - INTERVAL '10 minutes'"))
        .withWatermark("ts", "1 minute")
        .groupBy(window(col("ts"), "10 minutes", "1 minute"))
        .agg(avg("rating_star").alias("avg_rating"))
        .filter(col("avg_rating") < 4.0)
    )

    def write_rating_alert(df: DataFrame, epoch_id: int):
        count = df.count()
        if count == 0:
            return
        rows = df.collect()
        import psycopg2
        conn = psycopg2.connect(
            host=POSTGRES_HOST, port=POSTGRES_PORT, database=POSTGRES_DB,
            user=POSTGRES_USER, password=POSTGRES_PASSWORD,
        )
        try:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute("""
                        INSERT INTO alerts (alert_type, rating_avg)
                        SELECT 'rating_drop', %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM alerts
                            WHERE alert_type = 'rating_drop'
                            AND triggered_at > NOW() - INTERVAL '10 minutes'
                        )
                    """, (float(row.avg_rating),))
            conn.commit()
        finally:
            conn.close()

    rating_alert_query = (
        recent_ratings.writeStream
        .foreachBatch(write_rating_alert)
        .outputMode("update")
        .trigger(processingTime="10 seconds")
        .option("checkpointLocation", CHECKPOINT_DIR + "/rating_alerts")
        .start()
    )

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
