import os
import json
import time
import requests
from datetime import datetime
from kafka import KafkaProducer

# ── Konfigurasi ──────────────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
KAFKA_TOPIC             = os.getenv("KAFKA_TOPIC", "polled-data")
SHOPEE_URL              = os.getenv("SHOPEE_URL", "")
SCRAPE_INTERVAL         = int(os.getenv("SCRAPE_INTERVAL", "10"))   # detik antar halaman
POLL_INTERVAL           = int(os.getenv("POLL_INTERVAL", "60"))     # detik antar siklus polling
DATA_DIR                = os.getenv("DATA_DIR", "/app/data")

METADATA_FILE = os.path.join(DATA_DIR, "latest_metadata.json")
COOKIES_FILE  = os.path.join(DATA_DIR, "cookies.json")

# ── Kafka ─────────────────────────────────────────────────────────
def init_producer() -> KafkaProducer:
    print(f"[KAFKA] Menghubungkan ke {KAFKA_BOOTSTRAP_SERVERS}...")
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        request_timeout_ms=10_000,
        api_version_auto_timeout_ms=10_000,
    )
    print("[KAFKA] Producer terhubung!")
    return producer

# ── Cookie ────────────────────────────────────────────────────────
def load_cookie(cookies_file: str) -> str:
    if not os.path.exists(cookies_file):
        print(f"[COOKIE] File {cookies_file} tidak ditemukan, lanjut tanpa cookie.")
        return ""
    try:
        with open(cookies_file, "r", encoding="utf-8") as f:
            cookies_data = json.load(f)
        return ";".join(f"{d['name']}={d['value']}" for d in cookies_data)
    except Exception as e:
        print(f"[COOKIE] Gagal membaca: {e}")
        return ""

# ── Metadata ──────────────────────────────────────────────────────
def load_metadata() -> dict:
    if not os.path.exists(METADATA_FILE) or os.path.getsize(METADATA_FILE) == 0:
        return {}
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[META] Gagal membaca metadata: {e}")
        return {}

def save_metadata(metadata: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        print(f"[META] Metadata diperbarui.")
    except Exception as e:
        print(f"[META] Gagal menyimpan metadata: {e}")

# ── Scraping + Produce ────────────────────────────────────────────
def scrape_and_produce(producer: KafkaProducer):
    if not SHOPEE_URL:
        print("[ERROR] SHOPEE_URL belum di-set! Cek environment variable.")
        return

    # Parse URL
    parts = SHOPEE_URL.split("/")
    if len(parts) < 6:
        print("[ERROR] Format SHOPEE_URL tidak valid!")
        return

    user_id  = parts[4]
    shop_id  = parts[5].replace("rating?shop_id=", "")
    shop_key = f"{user_id}_{shop_id}"

    cookies  = load_cookie(COOKIES_FILE)
    metadata = load_metadata()

    # Ambil ctime terakhir yang sudah dikirim
    last_ctime = metadata.get(shop_key, {}).get("comment_time", 0)
    print(f"\n[SCRAPE] Shop: {shop_id} | Mulai dari ctime: {last_ctime}")

    headers = {
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if cookies:
        headers["cookie"] = cookies

    offset        = 0
    new_count     = 0
    max_ctime     = last_ctime
    stop_scraping = False

    while not stop_scraping:
        try:
            api_url = (
                f"https://shopee.co.id/api/v4/seller_operation/get_shop_ratings_new"
                f"?limit=6&offset={offset}&replied=false&shopid={shop_id}&userid={user_id}"
            )
            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code != 200:
                print(f"[SCRAPE] HTTP {response.status_code}, berhenti.")
                break

            items = response.json().get("data", {}).get("items", [])
            if not items:
                print("[SCRAPE] Tidak ada ulasan lagi.")
                break

            for item in items:
                current_ctime = item.get("ctime", 0)

                if current_ctime <= last_ctime:
                    print(f"[SCRAPE] Ulasan lama ditemukan, berhenti.")
                    stop_scraping = True
                    break

                product_name = "Produk tidak diketahui"
                if item.get("product_items"):
                    product_name = item["product_items"][0].get("name", product_name)

                data = {
                    "nama pengguna" : item.get("author_username", "Anonymous"),
                    "produk"        : product_name,
                    "review"        : item.get("comment", ""),
                    "rating"        : item.get("rating_star", 0),
                    "waktu transaksi": datetime.fromtimestamp(current_ctime).strftime("%Y-%m-%d %H:%M"),
                    "ctime"         : current_ctime,
                }

                # Langsung kirim ke Kafka — tanpa CSV
                producer.send(
                    KAFKA_TOPIC,
                    key=str(current_ctime).encode("utf-8"),
                    value=data,
                )
                print(f"[KAFKA] Terkirim: {data['nama pengguna']} | {data['produk']}")
                new_count += 1

                if current_ctime > max_ctime:
                    max_ctime = current_ctime

            if not stop_scraping:
                offset += 6
                print(f"[SCRAPE] Halaman berikutnya... sleep {SCRAPE_INTERVAL}s")
                time.sleep(SCRAPE_INTERVAL)

        except Exception as e:
            print(f"[ERROR] {e}")
            break

    if new_count > 0:
        producer.flush()
        print(f"[KAFKA] Flush selesai. Total terkirim: {new_count} ulasan.")

        # Update metadata
        metadata[shop_key] = {
            "comment_time"               : max_ctime,
            "last_scraped_time_formatted": datetime.fromtimestamp(max_ctime).strftime("%Y-%m-%d %H:%M"),
            "last_run_time"              : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "new_reviews_count"          : new_count,
        }
        save_metadata(metadata)
    else:
        print("[SCRAPE] Tidak ada ulasan baru.")

# ── Main Loop ─────────────────────────────────────────────────────
def main():
    producer = init_producer()
    print(f"[POLLER] Mulai polling setiap {POLL_INTERVAL} detik...\n")

    while True:
        scrape_and_produce(producer)
        print(f"[POLLER] Selesai satu siklus. Tunggu {POLL_INTERVAL}s...\n")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()