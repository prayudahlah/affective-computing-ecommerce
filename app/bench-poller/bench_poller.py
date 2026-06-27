#!/usr/bin/env python3
import hashlib
import json
import os
import sys
import threading
import time
import random
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "polled-data")
KAFKA_CDC_TOPIC = os.getenv("KAFKA_CDC_TOPIC", "cdc.mongodb.ecommerce.reviews")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ecommerce")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "reviews")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
MESSAGE_COUNT = int(os.getenv("BENCH_MESSAGE_COUNT", "100"))
TIMEOUT_SEC = int(os.getenv("BENCH_TIMEOUT_SEC", "300"))
OUTPUT_PATH = os.getenv("BENCH_OUTPUT_PATH", "/app/data/benchmark_result.json")
PRODUCE_INTERVAL = float(os.getenv("PRODUCE_INTERVAL", "1.0"))
PRODUCE_PROBABILITY = float(os.getenv("PRODUCE_PROBABILITY", "1.0"))
BENCH_STARTUP_DELAY_SEC = int(os.getenv("BENCH_STARTUP_DELAY_SEC", "0"))

FAKE_PRODUCTS = [
    "ASUS ROG Phone 7", "ASUS Zenbook 14 OLED", "ASUS Vivobook 15",
    "ASUS TUF Gaming A15", "ASUS ROG Strix G16", "ASUS ProArt Studiobook 16",
    "ASUS ExpertBook B9", "ASUS Zenfone 10",
]
FAKE_REVIEWS = [
    "Produk bagus berkualitas tinggi, sangat puas",
    "Barang sampai dengan cepat, kualitas sesuai ekspektasi",
    "Recommended banget, puas dengan pembelian ini",
    "Kualitas bagus, harga sesuai worth it",
    "Produk original, pengiriman cepat dan packing rapi",
    "Mantap! Sesuai deskripsi, recommended",
    "Barang bagus, makasih seller",
    "Kualitas terbaik, cocok untuk kebutuhan sehari-hari",
]

cdc_records = {}
cdc_lock = threading.Lock()


def epoch_ms(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def produce_messages(producer):
    if BENCH_STARTUP_DELAY_SEC > 0:
        print(f"[BENCH] Waiting {BENCH_STARTUP_DELAY_SEC}s for infrastructure...")
        time.sleep(BENCH_STARTUP_DELAY_SEC)

    messages = []
    sent = 0

    print(f"[BENCH] Producing {MESSAGE_COUNT} messages "
          f"(interval={PRODUCE_INTERVAL}s, prob={PRODUCE_PROBABILITY})")

    while sent < MESSAGE_COUNT:
        if random.random() < PRODUCE_PROBABILITY:
            ctime = int(time.time())
            ts_ms = int(time.time() * 1000)
            bench_id = f"bench_{sent:05d}"
            produk = f"{FAKE_PRODUCTS[sent % len(FAKE_PRODUCTS)]}|{ts_ms}"

            value = {
                "nama pengguna": bench_id,
                "produk": produk,
                "review": FAKE_REVIEWS[sent % len(FAKE_REVIEWS)],
                "rating": 5,
                "waktu transaksi": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "ctime": ctime,
            }

            doc_id = hashlib.md5(f"{ctime}_{bench_id}".encode()).hexdigest()

            producer.send(KAFKA_TOPIC, key=str(ctime).encode(), value=value)

            messages.append({
                "bench_id": bench_id,
                "ctime": ctime,
                "send_ts_ms": ts_ms,
                "doc_id": doc_id,
            })
            sent += 1

            if sent % 10 == 0:
                print(f"[BENCH] Produced {sent}/{MESSAGE_COUNT}")

        time.sleep(PRODUCE_INTERVAL)

    producer.flush()
    print(f"[BENCH] Flushed {MESSAGE_COUNT} messages")
    return messages


def cdc_consumer_thread():
    from kafka import KafkaConsumer

    for attempt in range(30):
        try:
            consumer = KafkaConsumer(
                KAFKA_CDC_TOPIC,
                bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
                group_id="bench-cdc-group",
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                session_timeout_ms=6000,
                request_timeout_ms=10000,
            )
            break
        except Exception as e:
            print(f"[CDC] Retry init ({attempt+1}/30): {e}")
            time.sleep(2)
    else:
        print("[CDC] Failed to init consumer")
        return

    try:
        for msg in consumer:
            try:
                payload = msg.value.get("payload", {})
                source = payload.get("source", {})
                cdc_ts = source.get("ts_ms")
                after_str = payload.get("after")
                op = payload.get("op")
                if cdc_ts and after_str and op in ("c", "r"):
                    after = json.loads(after_str)
                    doc_id = after.get("_id")
                    username = after.get("nama pengguna", "")
                    if doc_id and username.startswith("bench_"):
                        with cdc_lock:
                            if doc_id not in cdc_records:
                                cdc_records[doc_id] = cdc_ts
            except Exception as e:
                print(f"[CDC] Parse error: {e}")
    except Exception as e:
        print(f"[CDC] Consumer error: {e}")
    finally:
        consumer.close()


def wait_postgres(expected_ids):
    import psycopg2

    pending = set(expected_ids)
    start = time.time()

    while time.time() - start < TIMEOUT_SEC:
        try:
            conn = psycopg2.connect(
                host=POSTGRES_HOST, port=POSTGRES_PORT,
                dbname=POSTGRES_DB, user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT buyer_username FROM reviews WHERE buyer_username LIKE 'bench_%'"
                )
                found = {row[0] for row in cur.fetchall()}
            conn.close()
            remaining = pending - found
            if not remaining:
                print(f"\n[BENCH] All {len(found)} messages arrived in PostgreSQL")
                return True
            print(f"[BENCH] PostgreSQL: {len(found)}/{len(pending)}", end="\r")
        except Exception as e:
            print(f"[BENCH] PG poll error: {e}")
        time.sleep(2)

    print(f"\n[BENCH] TIMEOUT after {TIMEOUT_SEC}s. Missing: {len(remaining)}/{len(pending)}")
    return False


def collect_timestamps(messages):
    import psycopg2
    import pymongo

    pg_rows = {}
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT buyer_username, product_name, comment_id, processed_at "
            "FROM reviews WHERE buyer_username LIKE 'bench_%'"
        )
        for row in cur.fetchall():
            pg_rows[row[0]] = {
                "product_name": row[1],
                "comment_id": row[2],
                "processed_at": row[3],
            }
    conn.close()

    mongo_docs = {}
    mcli = pymongo.MongoClient(MONGO_URI)
    coll = mcli[MONGO_DB][MONGO_COLLECTION]
    for msg in messages:
        doc = coll.find_one({"_id": msg["doc_id"]})
        if doc:
            mongo_docs[msg["doc_id"]] = doc.get("preprocessed_at")
    mcli.close()

    with cdc_lock:
        cdc_snapshot = dict(cdc_records)

    results = []
    for msg in messages:
        bench_id = msg["bench_id"]
        doc_id = msg["doc_id"]
        send_ts = msg["send_ts_ms"]

        pg = pg_rows.get(bench_id)
        if not pg:
            continue

        mongo_ts = mongo_docs.get(doc_id)
        pg_ts = pg["processed_at"]
        cdc_ts = cdc_snapshot.get(doc_id)

        mongo_epoch = epoch_ms(mongo_ts) if mongo_ts else None
        pg_epoch = epoch_ms(pg_ts) if pg_ts else None

        p2p = mongo_epoch - send_ts if mongo_epoch else None
        ref = cdc_ts if cdc_ts is not None else mongo_epoch
        i2pg = (pg_epoch - ref) if pg_epoch is not None and ref is not None else None
        e2e = pg_epoch - send_ts if pg_epoch else None

        results.append({
            "bench_id": bench_id,
            "doc_id": doc_id,
            "send_ts_ms": send_ts,
            "poller_to_preprocess_ms": round(p2p, 1) if p2p is not None else None,
            "preprocess_to_postgres_ms": round(i2pg, 1) if i2pg is not None else None,
            "end_to_end_ms": round(e2e, 1) if e2e is not None else None,
            "cdc_ts_ms": cdc_ts,
            "mongo_preprocessed_at_epoch": mongo_epoch,
            "postgres_processed_at_epoch": pg_epoch,
        })

    return results


def compute_aggregates(results):
    def stats(vals):
        if not vals:
            return None
        a = np.array(vals)
        p = np.percentile(a, [50, 95, 99])
        return {
            "min": round(float(a.min()), 1),
            "max": round(float(a.max()), 1),
            "avg": round(float(a.mean()), 1),
            "p50": round(float(p[0]), 1),
            "p95": round(float(p[1]), 1),
            "p99": round(float(p[2]), 1),
        }

    return {
        "poller_to_preprocess_ms": stats(
            [r["poller_to_preprocess_ms"] for r in results
             if r["poller_to_preprocess_ms"] is not None]
        ),
        "preprocess_to_postgres_ms": stats(
            [r["preprocess_to_postgres_ms"] for r in results
             if r["preprocess_to_postgres_ms"] is not None]
        ),
        "end_to_end_ms": stats(
            [r["end_to_end_ms"] for r in results
             if r["end_to_end_ms"] is not None]
        ),
    }


def main():
    from kafka import KafkaProducer

    print(f"[BENCH] Starting benchmark: {MESSAGE_COUNT} messages, timeout {TIMEOUT_SEC}s")

    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        request_timeout_ms=10000,
    )

    t = threading.Thread(target=cdc_consumer_thread, daemon=True)
    t.start()
    time.sleep(2)

    messages = produce_messages(producer)
    producer.close()

    bench_ids = {m["bench_id"] for m in messages}
    ok = wait_postgres(bench_ids)

    results = collect_timestamps(messages)
    agg = compute_aggregates(results)

    output = {
        "benchmark": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {
                "total_messages": MESSAGE_COUNT,
                "processed": len(results),
                "timeout_sec": TIMEOUT_SEC,
            },
            "success": ok and len(results) == MESSAGE_COUNT,
            "aggregate": agg,
            "per_message": results,
        }
    }

    json_str = json.dumps(output, indent=2)
    sys.stdout.write("\n" + "=" * 60 + "\n")
    sys.stdout.write("BENCHMARK RESULT\n")
    sys.stdout.write("=" * 60 + "\n")
    sys.stdout.write(json_str + "\n")
    sys.stdout.flush()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(json_str)
    print(f"[BENCH] Written to {OUTPUT_PATH}")

    sys.exit(0 if ok and len(results) == MESSAGE_COUNT else 1)


if __name__ == "__main__":
    main()
