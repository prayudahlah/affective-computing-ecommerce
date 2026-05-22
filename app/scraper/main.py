import requests
import csv
import os
from datetime import datetime
import json
from kafka import KafkaProducer

def load_cookie(cookies_json) -> str:
    if not os.path.exists(cookies_json):
        print(f"Peringatan: File cookie {cookies_json} tidak ditemukan. Mencoba tanpa cookie...")
        return ""
    
    try:
        with open(cookies_json, 'r', encoding='utf-8') as f:
            cookies_data = json.load(f)
        
        if not cookies_data:
            return ""
            
        cookies_string = ""
        for index, data in enumerate(cookies_data):
            temp = f"{str(data['name'])}={data['value']}"
            if index < len(cookies_data) - 1:
                temp += ";"
            cookies_string += temp
        return cookies_string
    except Exception as e:
        print(f"Gagal membaca cookies.json: {e}")
        return ""

def load_metadata(metadata_file) -> dict:
    if not os.path.exists(metadata_file) or os.path.getsize(metadata_file) == 0:
        return {}
    
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Gagal membaca metadata: {e}. Menggunakan metadata kosong.")
        return {}

def save_metadata(metadata_file, metadata):
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        print(f"Metadata berhasil diperbarui di {metadata_file}")
    except Exception as e:
        print(f"Gagal menyimpan metadata: {e}")

def append_to_csv(csv_file, new_reviews):
    if not new_reviews:
        return
        
    file_exists = os.path.exists(csv_file) and os.path.getsize(csv_file) > 0
    keys = new_reviews[0].keys()
    
    try:
        with open(csv_file, "a", newline="", encoding="utf-8-sig") as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            if not file_exists:
                dict_writer.writeheader()
            dict_writer.writerows(new_reviews)
        print(f"Backup lokal: Berhasil menambahkan {len(new_reviews)} data baru ke {csv_file}")
    except Exception as e:
        print(f"Gagal menyimpan data ke CSV: {e}")

def init_kafka_producer() -> KafkaProducer:
    kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
    
    print(f"Menghubungkan ke Kafka broker di: {kafka_servers}...")
    try:
        producer = KafkaProducer(
            bootstrap_servers=[kafka_servers],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            request_timeout_ms=5000,
            api_version_auto_timeout_ms=5000
        )
        print("Koneksi Kafka Producer BERHASIL!")
        return producer
    except Exception as e:
        print(f"Peringatan: Gagal terhubung ke Kafka ({e}).")
        print("Scraper akan berjalan dalam MODE OFFLINE (hanya menyimpan backup CSV lokal).")
        return None

def shopee_incremental_scraper(url, cookies_json="cookies.json", metadata_json="latest_metadata.json", csv_file="shoope_rating.csv"):
    # 1. Parsing URL untuk mendapatkan user_id dan shop_id
    shop_url = url.split("/")
    if len(shop_url) < 6:
        print("Format URL Shopee tidak valid!")
        return

    user_id = shop_url[4]
    shop_id = shop_url[5].replace("rating?shop_id=", "")
    shop_key = f"{user_id}_{shop_id}"

    # 2. Muat cookies, metadata, dan inisialisasi Kafka
    cookies = load_cookie(cookies_json)
    metadata = load_metadata(metadata_json)
    producer = init_kafka_producer()
    kafka_topic = os.getenv("KAFKA_TOPIC", "polled-data")

    # Ambil waktu scraping terakhir dari metadata (default 0 jika belum pernah di-scrape)
    last_scraped_ctime = 0
    if shop_key in metadata:
        last_scraped_ctime = metadata[shop_key].get("last_scraped_ctime", 0)
        formatted_last_time = metadata[shop_key].get("last_scraped_time_formatted", "N/A")
        print(f"\nMemulai Incremental Scraping untuk Shop ID: {shop_id}")
        print(f"Ulasan terakhir yang di-scrape: {formatted_last_time} (Epoch: {last_scraped_ctime})")
    else:
        print(f"\nMemulai Scraping Pertama Kali untuk Shop ID: {shop_id}")

    headers = {
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if cookies:
        headers["cookie"] = cookies

    count = 0
    new_reviews = []
    max_ctime_in_run = last_scraped_ctime
    stop_scraping = False

    while not stop_scraping:
        try:
            api_url = f"https://shopee.co.id/api/v4/seller_operation/get_shop_ratings_new?limit=6&offset={count}&replied=false&shopid={shop_id}&userid={user_id}"
            
            response = requests.get(api_url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"Error: API Shopee mengembalikan status {response.status_code}")
                break
                
            data_req = response.json()
            data_review = data_req.get("data", {}).get("items", [])
            if not data_review:
                print("Tidak ada ulasan baru lagi di halaman ini.")
                break

            for value in data_review:
                current_ctime = value.get("ctime", 0)
                
                # Ulasan BARU (ctime > last_scraped_ctime)
                if current_ctime > last_scraped_ctime:
                    product_name = "Produk tidak diketahui"
                    if value.get("product_items"):
                        product_name = value["product_items"][0].get("name", "Produk tidak diketahui")
                        
                    data_result = {
                        "nama pengguna": value.get("author_username", "Anonymous"),
                        "produk": product_name,
                        "review": value.get("comment", ""),
                        "rating": value.get("rating_star", 0),
                        "waktu transaksi": datetime.fromtimestamp(current_ctime).strftime("%Y-%m-%d %H:%M"),
                        "ctime": current_ctime
                    }
                    
                    new_reviews.append(data_result)
                    
                    # KIRIM KE KAFKA PRODUCER
                    if producer:
                        try:
                            producer.send(
                                kafka_topic, 
                                key=str(current_ctime).encode('utf-8'),
                                value=data_result
                            )
                            print(f"[KAFKA] Terkirim! Review oleh {data_result['nama pengguna']}")
                        except Exception as kafka_err:
                            print(f"Gagal mengirim ke Kafka untuk ulasan {data_result['nama pengguna']}: {kafka_err}")
                    else:
                        print(f"[LOKAL] Menyiapkan ulasan dari {data_result['nama pengguna']}")
                    
                    if current_ctime > max_ctime_in_run:
                        max_ctime_in_run = current_ctime
                else:
                    print(f"Menemukan ulasan lama (Waktu: {datetime.fromtimestamp(current_ctime).strftime('%Y-%m-%d %H:%M')}). Menghentikan scraping.")
                    stop_scraping = True
                    break
            
            if not stop_scraping:
                count += 6
                
        except Exception as e:
            print(f"Terjadi kesalahan saat memproses data: {e}")
            break

    if new_reviews:
        if producer:
            print("Memastikan semua pesan Kafka terkirim (flushing)...")
            producer.flush()
            producer.close()
            print("Kafka producer ditutup dengan bersih.")
            
        new_reviews.reverse()
        append_to_csv(csv_file, new_reviews)
        
        # Update metadata JSON
        metadata[shop_key] = {
            "last_scraped_ctime": max_ctime_in_run,
            "last_scraped_time_formatted": datetime.fromtimestamp(max_ctime_in_run).strftime("%Y-%m-%d %H:%M"),
            "last_run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "new_reviews_count": len(new_reviews),
            "sent_to_kafka": True if producer else False
        }
        save_metadata(metadata_json, metadata)
        print(f"Selesai! Berhasil memproses {len(new_reviews)} ulasan baru.")
    else:
        if producer:
            producer.close()
        print("Selesai! Tidak ada ulasan baru yang ditemukan.")

if __name__ == '__main__':

    url_shop = os.getenv("SHOPEE_URL")
    cookies_file = "cookies.json"
    metadata_file = "latest_metadata.json"
    csv_output = "shoope_rating.csv"
    
    shopee_incremental_scraper(
        url=url_shop,
        cookies_json=cookies_file,
        metadata_json=metadata_file,
        csv_file=csv_output
    )
