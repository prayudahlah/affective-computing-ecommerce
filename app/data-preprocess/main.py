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
SENTIMENT_VECTORIZER_PATH = os.getenv("SENTIMENT_VECTORIZER_PATH", "/app/sentiment_vectorizer.joblib")
EMOTION_VECTORIZER_PATH = os.getenv("EMOTION_VECTORIZER_PATH", "/app/emotion_vectorizer.joblib")

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
        "/app/colloquial-indonesian-lexicon.csv",
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


def stem(tokens):
    stemmer = _get_stemmer()
    return [stemmer.stem(t) for t in tokens]


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
    tokens = stem(tokens)
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


def _discriminative_features_row(text):
    if not isinstance(text, str):
        text = str(text) if text else ""
    words = text.lower().split()
    demand_words = {"kembalikan", "ganti", "refund", "komplain", "keluhan",
                    "kembali", "tolong", "mohon", "urus", "klarifikasi", "balas"}
    n_demands = sum(1 for w in words if w in demand_words)
    uncertainty_words = {"mungkin", "khawatir", "takut", "was-was", "cemas",
                         "ragu", "bimbang", "curiga", "sepertinya", "seolah",
                         "antisipasi", "harap"}
    n_uncertainty = sum(1 for w in words if w in uncertainty_words)
    swear_words = {"anjing", "bangsat", "bodoh", "tolol", "jelek", "parah",
                   "payah", "sampah", "busuk", "brengsek", "persetan",
                   "keparat", "setan", "sial", "kacau"}
    n_swear = sum(1 for w in words if w in swear_words)
    attachment_words = {"cinta", "sayang", "suka", "gemas",
                        "love", "favorit", "kesayangan", "favorite"}
    n_attachment = sum(1 for w in words if w in attachment_words)
    repurchase_words = {"beli lagi", "order lagi", "repeat order", "langganan",
                        "balik lagi", "pasti beli", "akan beli", "nanti beli",
                        "rekomendasi", "recommend", "beli disini terus"}
    n_repurchase = sum(1 for phrase in repurchase_words if phrase in text.lower())
    transactional_words = {"bagus", "mantap", "ok", "oke", "cocok", "puas",
                           "sesuai", "recommended", "keren", "mantul",
                           "top", "good", "nice", "great", "worth"}
    n_transactional = sum(1 for w in words if w in transactional_words)
    return (n_demands, n_uncertainty, n_swear, n_attachment, n_repurchase, n_transactional)


def _enhanced_features_row(text):
    if not isinstance(text, str):
        text = str(text) if text else ""
    words = text.split()
    n_words = len(words)
    avg_word_len = float(sum(len(w) for w in words)) / n_words if n_words > 0 else 0.0
    intensifiers = {"sangat", "sekali", "banget", "paling", "amat",
                    "terlalu", "super", "benar", "sungguh", "betul"}
    n_intensifiers = sum(1 for w in text.lower().split() if w in intensifiers)
    pos_emojis = {"\U0001f60d", "\U0001f60a", "\u2764", "\U0001f44d",
                  "\U0001f604", "\U0001f601", "\U0001f970", "\U0001f618",
                  "\U0001f495", "\U0001f496", "\u2728", "\U0001f4af",
                  "\U0001f525", "\U0001f44f", "\U0001f929", "\U0001f389"}
    neg_emojis = {"\U0001f621", "\U0001f620", "\U0001f622", "\U0001f62d",
                  "\U0001f629", "\U0001f62b", "\U0001f61e", "\U0001f641",
                  "\U0001f623", "\U0001f616", "\U0001f614", "\U0001f44e",
                  "\U0001f494"}
    n_positive_emoji = sum(1 for ch in text if ch in pos_emojis)
    n_negative_emoji = sum(1 for ch in text if ch in neg_emojis)
    first_person = {"aku", "saya", "kami", "kit", "gue", "gw", "akuu"}
    second_person = {"kamu", "anda", "kau", "kakak", "mas", "mbak", "bro", "sis"}
    n_pronoun_1st = sum(1 for w in text.lower().split() if w in first_person)
    n_pronoun_2nd = sum(1 for w in text.lower().split() if w in second_person)
    return (n_words, avg_word_len, n_intensifiers, n_positive_emoji, n_negative_emoji,
            n_pronoun_1st, n_pronoun_2nd)


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
        .config("spark.cores.max", "2")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    logger.info("[SPARK] Session created")

    # Broadcast: slang dictionary
    slang_dict = _build_slang_dict()
    slang_dict_bc = spark.sparkContext.broadcast(slang_dict)
    logger.info("[BCAST] Slang dict broadcast (%d entries)", len(slang_dict))

    # Broadcast: TF-IDF vectorizers
    sentiment_vectorizer_bc = None
    if os.path.exists(SENTIMENT_VECTORIZER_PATH):
        vec = joblib.load(SENTIMENT_VECTORIZER_PATH)
        sentiment_vectorizer_bc = spark.sparkContext.broadcast(vec)
        logger.info(
            "[BCAST] Sentiment vectorizer (max_features=%s)",
            getattr(vec, "max_features", "?"),
        )
    else:
        logger.warning(
            "Sentiment vectorizer not found at %s — disabled",
            SENTIMENT_VECTORIZER_PATH,
        )

    emotion_vectorizer_bc = None
    if os.path.exists(EMOTION_VECTORIZER_PATH):
        vec = joblib.load(EMOTION_VECTORIZER_PATH)
        emotion_vectorizer_bc = spark.sparkContext.broadcast(vec)
        logger.info(
            "[BCAST] Emotion vectorizer (max_features=%s, ngram=%s)",
            getattr(vec, "max_features", "?"),
            getattr(vec, "ngram_range", "?"),
        )
    else:
        logger.warning(
            "Emotion vectorizer not found at %s — disabled",
            EMOTION_VECTORIZER_PATH,
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

    discriminative_schema = StructType(
        [
            StructField("n_demands", IntegerType(), False),
            StructField("n_uncertainty", IntegerType(), False),
            StructField("n_swear", IntegerType(), False),
            StructField("n_attachment", IntegerType(), False),
            StructField("n_repurchase", IntegerType(), False),
            StructField("n_transactional", IntegerType(), False),
        ]
    )

    enhanced_schema = StructType(
        [
            StructField("n_words", IntegerType(), False),
            StructField("avg_word_len", FloatType(), False),
            StructField("n_intensifiers", IntegerType(), False),
            StructField("n_positive_emoji", IntegerType(), False),
            StructField("n_negative_emoji", IntegerType(), False),
            StructField("n_pronoun_1st", IntegerType(), False),
            StructField("n_pronoun_2nd", IntegerType(), False),
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

    @udf(discriminative_schema)
    def discriminative_udf(text):
        return _discriminative_features_row(text)

    @udf(enhanced_schema)
    def enhanced_udf(text):
        return _enhanced_features_row(text)

    @udf(vector_schema)
    def sentiment_vectorize_udf(text):
        if sentiment_vectorizer_bc is None or not text or not text.strip():
            return []
        vec = sentiment_vectorizer_bc.value.transform([text])
        row = vec[0]
        return [{"i": int(c), "v": float(v)} for c, v in zip(row.indices, row.data)]

    @udf(vector_schema)
    def emotion_vectorize_udf(text):
        if emotion_vectorizer_bc is None or not text or not text.strip():
            return []
        vec = emotion_vectorizer_bc.value.transform([text])
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
        .withColumn("discriminative_features", discriminative_udf(col("review")))
        .withColumn("emotion_features_enhanced", enhanced_udf(col("review")))
        .withColumn("sentiment_vectorized", sentiment_vectorize_udf(col("review_preprocessed")))
        .withColumn("emotion_vectorized", emotion_vectorize_udf(col("review_preprocessed")))
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
        import hashlib
        client = pymongo.MongoClient(MONGO_URI)
        try:
            coll = client[MONGO_DB][MONGO_COLLECTION]
            for record in records:
                key = f"{record.get('ctime')}_{record.get('nama pengguna')}"
                record["_id"] = hashlib.md5(key.encode()).hexdigest()
                coll.replace_one({"_id": record["_id"]}, record, upsert=True)
            logger.info("[EPOCH %d] Upserted %d documents", epoch_id, len(records))
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
