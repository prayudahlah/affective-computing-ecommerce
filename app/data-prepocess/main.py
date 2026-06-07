import os
import sys
import logging
import re
import itertools

import nltk
import emoji
import pandas as pd
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory

nltk.download("punkt_tab", quiet=True)
nltk.download("stopwords", quiet=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("DataPoller")

# ── Configuration ──────────────────────────────────────────────────

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "polled-data")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
MONGO_DB = os.getenv("MONGO_DB", "ecommerce")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "reviews")
SPARK_MASTER_URL = os.getenv("SPARK_MASTER_URL", "spark://spark-master:7077")
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/app/data/checkpoint")
VECTORIZER_PATH = os.getenv("VECTORIZER_PATH", "/app/tfidf_vectorizer.joblib")

# ── Preprocessing ──────────────────────────────────────────────────

_stemmer = None


def _get_stemmer():
    global _stemmer
    if _stemmer is None:
        factory = StemmerFactory()
        _stemmer = factory.create_stemmer()
    return _stemmer


def _build_slang_dict():
    paths = [
        "/app/data-prepocess/colloquial-indonesian-lexicon.csv",
    ]
    csv_path = next((p for p in paths if os.path.exists(p)), None)
    if csv_path is None:
        logger.warning("Slang lexicon CSV not found — slang normalization disabled")
        return {}
    logger.info("Loading slang lexicon from %s", csv_path)
    kamus_df = pd.read_csv(csv_path)
    kamus_valid = kamus_df[kamus_df["In-dictionary"] == 1]
    slang_dict = {}
    for _, row in kamus_valid.iterrows():
        slang = str(row["slang"]).strip().lower()
        formal = str(row["formal"]).strip().lower()
        if slang in slang_dict:
            if len(formal) < len(slang_dict[slang]):
                slang_dict[slang] = formal
        else:
            slang_dict[slang] = formal
    logger.info("Loaded %d slang entries", len(slang_dict))
    return slang_dict


def normalize_repetitive_chars(text):
    if not isinstance(text, str) or not text.strip():
        return text
    text = re.sub(r"(a)\1{2,}", "a", text)
    text = re.sub(r"(i)\1{2,}", "i", text)
    text = re.sub(r"(u)\1{2,}", "u", text)
    text = re.sub(r"(e)\1{2,}", "e", text)
    text = re.sub(r"(o)\1{2,}", "o", text)
    text = re.sub(r"([^aiueo])\1{2,}", r"\1", text)
    return text


def normalize_slang(text, slang_dict):
    if not isinstance(text, str) or not text.strip():
        return text
    if not slang_dict:
        return text
    words = text.split()
    normalized = []
    for w in words:
        w_lower = w.lower()
        if w_lower in slang_dict:
            normalized.append(slang_dict[w_lower])
        elif w_lower.rstrip(".,!?;:") in slang_dict:
            punct = w[len(w_lower.rstrip(".,!?;:")) :]
            normalized.append(slang_dict[w_lower.rstrip(".,!?;:")] + punct)
        else:
            normalized.append(w)
    return " ".join(normalized)


def emoji_to_text(text):
    if not isinstance(text, str) or not text.strip():
        return text
    return emoji.demojize(text, language="id")


def tokenize(text):
    if not isinstance(text, str) or not text.strip():
        return []
    return word_tokenize(text)


def remove_stopwords(tokens):
    stop_words = set(stopwords.words("indonesian"))
    return [t for t in tokens if t.lower() not in stop_words]


def pos_tag(tokens):
    konjungsi = {
        "dan",
        "atau",
        "tetapi",
        "namun",
        "sedangkan",
        "serta",
        "karena",
        "sehingga",
        "maka",
        "lalu",
        "kemudian",
        "setelah",
        "sebelum",
        "ketika",
        "sementara",
        "walaupun",
        "meskipun",
        "jika",
        "kalau",
        "apabila",
        "bahwa",
    }
    preposisi = {
        "di",
        "ke",
        "dari",
        "pada",
        "dengan",
        "untuk",
        "bagi",
        "oleh",
        "tentang",
        "seperti",
        "sebagai",
        "tanpa",
        "dalam",
        "antara",
        "menurut",
        "sampai",
        "hingga",
    }
    hasil = []
    for token in tokens:
        t = token.lower()
        if re.match(r"^[.,!?;:()\[\]{}\"\'\-]$", token):
            hasil.append((token, "PUNCT"))
        elif re.match(r"^[0-9.,\-]+$", token):
            hasil.append((token, "NUM"))
        elif t in konjungsi:
            hasil.append((token, "CONJ"))
        elif t in preposisi:
            hasil.append((token, "ADP"))
        elif re.match(r"^(me|men|meng|meny|mem|di|ber|bel|ter|per)", t):
            hasil.append((token, "VERB"))
        elif (
            re.match(r"^(pe|pen|pem|peng|ke)", t)
            or t.endswith("an")
            or t.endswith("kan")
        ):
            hasil.append((token, "NOUN"))
        elif t.endswith("i"):
            hasil.append((token, "VERB"))
        else:
            hasil.append((token, "NOUN"))
    return hasil


def lemmatize(tokens, pos_tags):
    stemmer = _get_stemmer()
    hasil = []
    for token, (_, pos) in zip(tokens, pos_tags):
        t = token.lower()
        t = re.sub(r"(-lah|-kah|-pun|-ku|-mu|-nya)$", "", t)
        redup_match = re.match(r"^(.+?)[-]?\1$", t)
        if redup_match:
            t = redup_match.group(1)
        if pos == "PUNCT":
            continue
        elif pos == "VERB":
            t = stemmer.stem(t)
        hasil.append(t)
    return hasil


def handle_negation(text):
    if not isinstance(text, str) or not text.strip():
        return text
    neg_words = {
        "tidak",
        "bukan",
        "belum",
        "tak",
        "ngga",
        "gak",
        "ga",
        "tdk",
        "enggak",
        "nggak",
        "kagak",
        "ndak",
        "ngg",
    }
    words = text.split()
    result = []
    negate = False
    for w in words:
        w_clean = w.lower().strip(".,!?")
        if w_clean in neg_words:
            result.append(w)
            negate = True
        elif negate:
            result.append("NEG_" + w)
            negate = False
        else:
            result.append(w)
    return " ".join(result)


def full_pipeline(text, slang_dict):
    if not isinstance(text, str) or not text.strip():
        return ""
    t = text
    t = normalize_repetitive_chars(t)
    t = normalize_slang(t, slang_dict)
    t = emoji_to_text(t)
    tokens = tokenize(t)
    tokens = remove_stopwords(tokens)
    pos_tags = pos_tag(tokens)
    tokens = lemmatize(tokens, pos_tags)
    tokens = handle_negation(" ".join(tokens)).split()
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def _emotion_features_row(text):
    if not isinstance(text, str):
        text = str(text) if text else ""
    return (
        text.count("!"),
        text.count("?"),
        sum(1 for w in text.split() if w.isupper() and len(w) > 2),
        text.count(".."),
        max((len(list(g)) for _, g in itertools.groupby(text.lower())), default=0),
    )


# ── Main ───────────────────────────────────────────────────────────


def main():
    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql.functions import from_json, col, current_timestamp, udf
    from pyspark.sql.types import (
        StructType,
        StructField,
        StringType,
        IntegerType,
        ArrayType,
        FloatType,
    )
    import joblib
    import pymongo

    logger.info("=" * 60)
    logger.info("Spark Structured Streaming — Data Poller (Distributed UDF)")
    logger.info("Kafka:        %s / %s", KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC)
    logger.info("MongoDB:      %s / %s.%s", MONGO_URI, MONGO_DB, MONGO_COLLECTION)
    logger.info("Spark master: %s", SPARK_MASTER_URL)
    logger.info("Checkpoint:   %s", CHECKPOINT_DIR)
    logger.info("=" * 60)

    spark = (
        SparkSession.builder.appName("StreamDataPreprocess")
        .master(SPARK_MASTER_URL)
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    logger.info("[SPARK] Session created")

    # Broadcast: slang dictionary
    slang_dict = _build_slang_dict()
    slang_dict_bc = spark.sparkContext.broadcast(slang_dict)
    logger.info("[BCAST] Slang dict broadcast (%d entries)", len(slang_dict))

    # Broadcast: TF-IDF vectorizer (optional)
    vectorizer_bc = None
    if os.path.exists(VECTORIZER_PATH):
        vec = joblib.load(VECTORIZER_PATH)
        vectorizer_bc = spark.sparkContext.broadcast(vec)
        logger.info(
            "[BCAST] Vectorizer broadcast (max_features=%s)",
            getattr(vec, "max_features", "?"),
        )
    else:
        logger.warning(
            "Vectorizer not found at %s — vectorization disabled", VECTORIZER_PATH
        )

    # ── UDF schemas ────────────────────────────────────────────────

    emotion_schema = StructType(
        [
            StructField("n_exclamation", IntegerType(), False),
            StructField("n_question", IntegerType(), False),
            StructField("n_allcaps", IntegerType(), False),
            StructField("n_ellipsis", IntegerType(), False),
            StructField("max_char_repeat", IntegerType(), False),
        ]
    )

    vector_item_schema = StructType(
        [
            StructField("i", IntegerType(), False),
            StructField("v", FloatType(), False),
        ]
    )
    vector_schema = ArrayType(vector_item_schema)

    # ── UDF definitions ────────────────────────────────────────────

    @udf(StringType())
    def preprocess_udf(text):
        return full_pipeline(text, slang_dict_bc.value)

    @udf(emotion_schema)
    def emotion_udf(text):
        return _emotion_features_row(text)

    @udf(vector_schema)
    def vectorize_udf(text):
        if vectorizer_bc is None or not text or not text.strip():
            return []
        vec = vectorizer_bc.value.transform([text])
        row = vec[0]
        return [{"i": int(c), "v": float(v)} for c, v in zip(row.indices, row.data)]

    # ── Kafka source ───────────────────────────────────────────────

    kafka_schema = StructType(
        [
            StructField("nama pengguna", StringType()),
            StructField("produk", StringType()),
            StructField("review", StringType()),
            StructField("rating", IntegerType()),
            StructField("waktu transaksi", StringType()),
            StructField("ctime", IntegerType()),
        ]
    )

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", "1000")
        .load()
    )

    # ── Parse JSON ─────────────────────────────────────────────────

    parsed = raw.select(
        from_json(col("value").cast("string"), kafka_schema).alias("data")
    ).select("data.*")

    # ── Apply UDFs (distributed on workers) ────────────────────────

    processed = (
        parsed.withColumn("review_preprocessed", preprocess_udf(col("review")))
        .withColumn("emotion_features", emotion_udf(col("review")))
        .withColumn("review_vectorized", vectorize_udf(col("review_preprocessed")))
        .withColumn("preprocessed_at", current_timestamp())
    )

    # ── foreachBatch: write to MongoDB via pymongo ──────────────

    def write_to_mongo(df: DataFrame, epoch_id: int):
        count = df.count()
        if count == 0:
            logger.info("[EPOCH %d] No records to write", epoch_id)
            return
        pdf = df.toPandas()
        records = pdf.to_dict(orient="records")
        logger.info(
            "[EPOCH %d] Writing %d records to MongoDB %s.%s",
            epoch_id,
            len(records),
            MONGO_DB,
            MONGO_COLLECTION,
        )
        client = pymongo.MongoClient(MONGO_URI)
        try:
            result = client[MONGO_DB][MONGO_COLLECTION].insert_many(
                records, ordered=False
            )
            logger.info(
                "[EPOCH %d] Inserted %d documents",
                epoch_id,
                len(result.inserted_ids),
            )
        except Exception as e:
            logger.error("[EPOCH %d] MongoDB write failed: %s", epoch_id, e)
            raise
        finally:
            client.close()

    # ── MongoDB sink (foreachBatch ─ pymongo) ───────────────────

    mongo_query = (
        processed.writeStream.foreachBatch(write_to_mongo)
        .outputMode("append")
        .option("checkpointLocation", CHECKPOINT_DIR + "/mongodb")
        .trigger(processingTime="10 seconds")
        .start()
    )

    # ── Debug: console sink untuk isi processed ──────────────────
    debug_query = (
        processed.writeStream.format("console")
        .outputMode("append")
        .option("checkpointLocation", CHECKPOINT_DIR + "/console_debug")
        .trigger(processingTime="10 seconds")
        .start()
    )

    mongo_query.awaitTermination()


if __name__ == "__main__":
    main()
