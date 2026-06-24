import os
import uuid
import random
from datetime import datetime, timedelta, timezone
import psycopg2
from psycopg2.extras import execute_values

DB_USER     = os.getenv("INFERENCE_DB_USER",     "postgres")
DB_PASSWORD = os.getenv("INFERENCE_DB_PASSWORD", "postgres")
DB_HOST     = os.getenv("INFERENCE_DB_HOST",     "localhost")
DB_NAME     = os.getenv("INFERENCE_DB_NAME",     "postgres")

PRODUCTS = [
    "ASUS ROG Phone 7",
    "ASUS Zenbook 14 OLED",
    "ASUS Vivobook 15",
    "ASUS TUF Gaming A15",
    "ASUS ROG Strix G16",
    "ASUS ProArt Studiobook 16",
    "ASUS ExpertBook B9",
    "ASUS Zenfone 10",
]

USERNAMES = [
    "BudiSantoso", "SitiNurhaliza", "AhmadFauzi", "DewiLestari",
    "RizkyPratama", "MayaAnggraini", "DimasAditya", "PutriAyunda",
    "HendraGunawan", "RatnaSari", "AdiNugroho", "WulanDari",
    "FebrianHakim", "IntanPermata", "GilangRamadhan", "CitraKirana",
    "EkoWibowo", "RinaMelati", "ArifSetiawan", "NadiaPramesti",
]

COMMENTS_POSITIVE = [
    "Barang sampai dengan cepat, kualitas bagus sesuai ekspektasi!",
    "Produk original, recommended banget buat kerja dan gaming",
    "Kualitas display sangat jernih, cocok untuk desain grafis",
    "Performa kencang, ga pernah lag buat multitasking",
    "Baterai tahan lama, bisa dipakai kerja seharian penuh",
    "Desainnya elegant dan premium, puas banget dengan pembelian ini",
    "Keyboard nyaman dipakai ngetik lama, backlightnya keren",
    "Fitur lengkap, harga sesuai kualitas, worth it banget",
    "Pengiriman cepat, packing rapi, produk tidak ada cacat",
    "Sudah 3 bulan pemakaian, masih mulus seperti baru, mantap!",
    "Suhu tetap adem walau dipakai main game berat",
    "Audio jernih, cocok buat nonton film dan dengerin musik",
]

COMMENTS_NEGATIVE = [
    "Barang datang terlambat 3 hari dari estimasi",
    "Keyboard ada beberapa tombol yang macet setelah seminggu",
    "Baterai boros, tidak sesuai dengan yang diiklankan",
    "Sering overheating padahal hanya dipakai browsing",
    "Kualitas build kurang solid, ada celah di bagian body",
    "Layar kurang cerah, warna agak pudar dibanding ekspektasi",
    "Fans berisik sekali, mengganggu saat bekerja di malam hari",
    "Touchpad tidak responsif, kursor sering loncat-loncat",
    "Spek tidak sesuai deskripsi, merasa dibohongi",
    "Harga terlalu mahal untuk kualitas yang didapatkan",
    "Garansi sulit diklaim, CS lambat merespon",
    "Software sering crash, harus restart berkali-kali",
]

SENTIMENTS = ["Positif", "Negatif"]

EMOTIONS_POS = ["Senang", "Puas", "Netral"]
EMOTIONS_NEG = ["Kecewa", "Marah", "Sedih"]

ALERT_TYPES = ["rating_drop", "sentiment_negative"]


def generate_reviews(n: int, now: datetime):
    rows = []
    for i in range(n):
        product = random.choice(PRODUCTS)
        is_positive = random.random() < 0.7
        rating = random.choices(
            [5, 4, 3, 2, 1],
            weights=[40, 30, 15, 10, 5],
        )[0]
        if rating >= 4:
            sentiment = "Positif"
            emotion = random.choice(EMOTIONS_POS)
            comment = random.choice(COMMENTS_POSITIVE)
        elif rating == 3:
            sentiment = random.choice(SENTIMENTS)
            emotion = random.choice(EMOTIONS_NEG) if sentiment == "Negatif" else random.choice(EMOTIONS_POS)
            comment = random.choice(COMMENTS_NEGATIVE) if sentiment == "Negatif" else random.choice(COMMENTS_POSITIVE)
        else:
            sentiment = "Negatif"
            emotion = random.choice(EMOTIONS_NEG)
            comment = random.choice(COMMENTS_NEGATIVE)

        create_time = now - timedelta(
            days=random.randint(0, 29),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )

        rows.append((
            f"SEED-{uuid.uuid4().hex[:12]}",
            random.choice(USERNAMES),
            product,
            comment,
            rating,
            create_time,
            sentiment,
            emotion,
        ))
    return rows


def generate_alerts(reviews_with_ids: list[tuple], now: datetime):
    rows = []
    sample = random.sample(reviews_with_ids, min(10, len(reviews_with_ids)))
    for review_id, review in sample:
        alert_type = random.choice(ALERT_TYPES)
        triggered_at = review[5] + timedelta(hours=random.randint(0, 4))
        rows.append((
            alert_type,
            triggered_at,
            review[3],
            round(random.uniform(1.5, 3.5), 2),
            review_id,
        ))
    return rows


def main():
    conn = psycopg2.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )
    conn.autocommit = False
    cur = conn.cursor()

    now = datetime.now(timezone.utc)

    print("Membersihkan data lama...")
    cur.execute("DELETE FROM alerts")
    cur.execute("DELETE FROM reviews")
    cur.execute("DELETE FROM model_metadata")

    print("Men-generate data reviews...")
    reviews = generate_reviews(120, now)

    print("Insert reviews...")
    execute_values(
        cur,
        """
        INSERT INTO reviews (comment_id, buyer_username, product_name, comment, rating_star, create_time, sentiment, emotion)
        VALUES %s
        RETURNING id, comment_id, buyer_username, product_name, comment, rating_star, create_time, sentiment, emotion
        """,
        reviews,
        template="(%s, %s, %s, %s, %s, %s, %s, %s)",
        page_size=500,
    )

    inserted_reviews = cur.fetchall()
    print(f"  -> {len(inserted_reviews)} reviews inserted")

    print("Insert alerts...")
    alerts = generate_alerts(inserted_reviews, now)
    execute_values(
        cur,
        """
        INSERT INTO alerts (alert_type, triggered_at, comment, rating_avg, review_id)
        VALUES %s
        """,
        alerts,
        template="(%s, %s, %s, %s, %s)",
        page_size=500,
    )
    print(f"  -> {len(alerts)} alerts inserted")

    print("Insert model_metadata...")
    model_data = [
        ("sentiment_model_v1", 0.8567, True, "sentiment"),
        ("emotion_model_v1",   0.7821, True, "emotion"),
    ]
    execute_values(
        cur,
        """
        INSERT INTO model_metadata (model_name, f1_score_macro, is_active, task_type)
        VALUES %s
        """,
        model_data,
        template="(%s, %s, %s, %s)",
    )
    print("  -> 2 models inserted (sentiment, emotion)")

    conn.commit()
    cur.close()
    conn.close()

    print("\nSeeding selesai! Data siap ditampilkan di dashboard.")


if __name__ == "__main__":
    main()
