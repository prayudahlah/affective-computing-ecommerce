import os
import json
import time
import asyncio
import aiohttp
from datetime import datetime
from kafka import KafkaProducer

# ── Konfigurasi ──────────────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
KAFKA_TOPIC             = os.getenv("KAFKA_TOPIC", "polled-data")
SHOPEE_URL              = os.getenv("SHOPEE_URL", "")
SCRAPE_INTERVAL         = float(os.getenv("SCRAPE_INTERVAL", "10"))
POLL_INTERVAL           = int(os.getenv("POLL_INTERVAL", "60"))
DATA_DIR                = os.getenv("DATA_DIR", "/app/data")

CATCHUP_WORKERS         = int(os.getenv("CATCHUP_WORKERS", "10"))
CATCHUP_DELAY           = float(os.getenv("CATCHUP_DELAY", "0.5"))
CATCHUP_CHECKPOINT_N    = int(os.getenv("CATCHUP_CHECKPOINT_N", "500"))
CATCHUP_THRESHOLD_SECS  = int(os.getenv("CATCHUP_THRESHOLD_SECS", "3600"))

METADATA_FILE = os.path.join(DATA_DIR, "latest_metadata.json")
COOKIES_FILE  = os.path.join(DATA_DIR, "cookies.json")


# ── Kafka ─────────────────────────────────────────────────────────
def init_producer() -> KafkaProducer:
    print(f"[KAFKA] Menghubungkan ke {KAFKA_BOOTSTRAP_SERVERS}...")
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        request_timeout_ms=10_000,
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


# ── Shared State untuk Catch-up ───────────────────────────────────
class CatchUpState:
    def __init__(self, last_ctime: int):
        self.last_ctime          = last_ctime       # batas bawah — ulasan lama
        self.max_ctime           = last_ctime        # batas atas — ulasan terbaru yang ditemukan
        self.new_count           = 0                 # total ulasan baru yang sudah di-produce
        self.stop_event          = asyncio.Event()   # di-set kalau worker menemukan ulasan lama / data habis
        self.lock                = asyncio.Lock()    # guard max_ctime & new_count
        self.offset_gen_stopped  = False             # flag bahwa generator offset sudah berhenti
        self.empty_page_count    = 0                 # berapa kali dapat halaman BENAR-BENAR kosong (bukan error)


# ── Fetch satu halaman (async) ────────────────────────────────────
async def _fetch_once(
    session: aiohttp.ClientSession,
    api_url: str,
    headers: dict,
    offset: int,
) -> list[dict] | None:
    async with session.get(
        api_url,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status != 200:
            print(f"[SCRAPE] HTTP {resp.status} pada offset {offset}.")
            return None

        # Baca raw text dulu untuk bisa log kalau parsing gagal
        raw = await resp.text()
        if not raw or not raw.strip():
            print(f"[SCRAPE] Respons kosong (empty body) pada offset {offset}.")
            return None

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[SCRAPE] JSON decode error pada offset {offset}: {e}")
            return None

        # Shopee kadang mengembalikan returncode != 0 saat rate-limit / session invalid
        returncode = body.get("returncode", 0)
        if returncode != 0:
            print(f"[SCRAPE] returncode={returncode} pada offset {offset} — kemungkinan rate-limit.")
            return None   # transient, bukan data habis

        # Struktur normal: body["data"]["items"]
        data_obj = body.get("data")
        if data_obj is None:
            print(f"[SCRAPE] data=null pada offset {offset} — anggap transient.")
            return None

        if not isinstance(data_obj, dict):
            print(f"[SCRAPE] data bukan dict pada offset {offset}: {type(data_obj)}.")
            return None

        items = data_obj.get("items")

        # items=None artinya key tidak ada → anggap transient (struktur tak terduga)
        if items is None:
            print(f"[SCRAPE] items=None pada offset {offset} — anggap transient.")
            return None

        if not isinstance(items, list):
            print(f"[SCRAPE] items bukan list pada offset {offset}: {type(items)}.")
            return None

        # items=[] artinya halaman benar-benar kosong (data habis)
        return items


async def fetch_page(
    session: aiohttp.ClientSession,
    shop_id: str,
    user_id: str,
    offset: int,
    headers: dict,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> list[dict] | None:
    api_url = (
        f"https://shopee.co.id/api/v4/seller_operation/get_shop_ratings_new"
        f"?limit=6&offset={offset}&replied=false&shopid={shop_id}&userid={user_id}"
    )
    for attempt in range(1, max_retries + 1):
        try:
            result = await _fetch_once(session, api_url, headers, offset)
            if result is not None:
                return result   # sukses

            # result=None
            if attempt < max_retries:
                wait = retry_delay * attempt
                print(f"[SCRAPE] Offset {offset}: retry {attempt}/{max_retries} dalam {wait:.0f}s...")
                await asyncio.sleep(wait)

        except asyncio.TimeoutError:
            print(f"[ERROR] Offset {offset}: timeout (attempt {attempt}).")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)
        except aiohttp.ClientError as e:
            print(f"[ERROR] Offset {offset}: {e} (attempt {attempt}).")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)
        except Exception as e:
            print(f"[ERROR] Offset {offset}: {e} (attempt {attempt}).")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)

    print(f"[SCRAPE] Offset {offset}: gagal setelah {max_retries} percobaan.")
    return None


# ── Worker Catch-up ───────────────────────────────────────────────
async def catchup_worker(
    worker_id: int,
    offset_queue: asyncio.Queue,
    session: aiohttp.ClientSession,
    producer: KafkaProducer,
    shop_id: str,
    user_id: str,
    headers: dict,
    state: CatchUpState,
    metadata: dict,
    shop_key: str,
):
    while not state.stop_event.is_set():
        try:
            offset = await asyncio.wait_for(offset_queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            if state.offset_gen_stopped:
                break
            continue

        items = await fetch_page(session, shop_id, user_id, offset, headers)

        # None = gagal permanen setelah semua retry
        if items is None or not items:
            label = "Gagal permanen" if items is None else "Halaman kosong"
            async with state.lock:
                state.empty_page_count += 1
                empty = state.empty_page_count

            if empty >= CATCHUP_WORKERS:
                print(f"[W{worker_id}] {label} ({empty}x berturut-turut), Set STOP.")
                state.stop_event.set()

            offset_queue.task_done()
            await asyncio.sleep(CATCHUP_DELAY)
            continue

        # Ada data: reset empty counter
        async with state.lock:
            state.empty_page_count = 0

        found_old = False
        batch = []
        for item in items:
            current_ctime = item.get("ctime", 0)
            if current_ctime <= state.last_ctime:
                print(f"[W{worker_id}] Ulasan lama (ctime={current_ctime}), set STOP.")
                found_old = True
                break

            product_name = "Produk tidak diketahui"
            if item.get("product_items"):
                product_name = item["product_items"][0].get("name", product_name)

            batch.append({
                "nama pengguna"  : item.get("author_username", "Anonymous"),
                "produk"         : product_name,
                "review"         : item.get("comment", ""),
                "rating"         : item.get("rating_star", 0),
                "waktu transaksi": datetime.fromtimestamp(current_ctime).strftime("%Y-%m-%d %H:%M"),
                "ctime"          : current_ctime,
            })

        # Produce batch ke Kafka
        for data in batch:
            producer.send(
                KAFKA_TOPIC,
                key=str(data["ctime"]).encode("utf-8"),
                value=data,
            )

        # Update shared state
        async with state.lock:
            state.new_count += len(batch)
            for data in batch:
                if data["ctime"] > state.max_ctime:
                    state.max_ctime = data["ctime"]
            if batch:
                print(
                    f"[W{worker_id}] offset={offset} | +{len(batch)} ulasan"
                    f" | total={state.new_count}"
                )
            # Checkpoint periodik
            if state.new_count > 0 and state.new_count % CATCHUP_CHECKPOINT_N == 0:
                _save_checkpoint(metadata, shop_key, state)

        if found_old:
            state.stop_event.set()

        offset_queue.task_done()
        await asyncio.sleep(CATCHUP_DELAY)

    print(f"[W{worker_id}] Worker selesai.")


# ── Checkpoint helper ─────────────────────────────────────────────
def _save_checkpoint(metadata: dict, shop_key: str, state: CatchUpState):
    now_epoch = int(time.time())
    metadata[shop_key] = {
        "comment_time"               : state.max_ctime,
        "last_scraped_time_formatted": datetime.fromtimestamp(state.max_ctime).strftime("%Y-%m-%d %H:%M"),
        "last_run_time"              : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_run_epoch"             : now_epoch,   # ← baru: epoch saat scrape selesai
        "new_reviews_count"          : state.new_count,
    }
    save_metadata(metadata)
    print(f"[CHECKPOINT] Disimpan pada {state.new_count} ulasan.")


# ── Mode Catch-up (async) ─────────────────────────────────────────
async def run_catchup(
    producer: KafkaProducer,
    shop_id: str,
    user_id: str,
    headers: dict,
    last_ctime: int,
    metadata: dict,
    shop_key: str,
) -> int:
    print(f"\n[CATCHUP] Mulai mode catch-up dengan {CATCHUP_WORKERS} worker...")
    state        = CatchUpState(last_ctime)
    offset_queue = asyncio.Queue(maxsize=CATCHUP_WORKERS * 3)

    async with aiohttp.ClientSession() as session:
        workers = [
            asyncio.create_task(
                catchup_worker(
                    worker_id=i,
                    offset_queue=offset_queue,
                    session=session,
                    producer=producer,
                    shop_id=shop_id,
                    user_id=user_id,
                    headers=headers,
                    state=state,
                    metadata=metadata,
                    shop_key=shop_key,
                )
            )
            for i in range(CATCHUP_WORKERS)
        ]

        offset = 0
        while not state.stop_event.is_set():
            try:
                await asyncio.wait_for(offset_queue.put(offset), timeout=1.0)
                offset += 6
            except asyncio.TimeoutError:
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[CATCHUP] Error feed offset: {e}")
                break

        state.offset_gen_stopped = True
        await asyncio.gather(*workers, return_exceptions=True)

    if state.new_count > 0:
        producer.flush()
        print(f"[CATCHUP] Selesai. Total terkirim: {state.new_count} ulasan.")
        _save_checkpoint(metadata, shop_key, state)
    else:
        print("[CATCHUP] Tidak ada ulasan baru ditemukan.")
        now_epoch = int(time.time())
        if shop_key in metadata:
            metadata[shop_key]["last_run_epoch"] = now_epoch
            metadata[shop_key]["last_run_time"]  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_metadata(metadata)

    return state.max_ctime


# ── Mode Realtime (sync, single-threaded) ────────────────────────
def run_realtime(
    producer: KafkaProducer,
    shop_id: str,
    user_id: str,
    headers: dict,
    last_ctime: int,
    metadata: dict,
    shop_key: str,
) -> int:
    import requests

    print(f"\n[REALTIME] Mulai mode realtime scraping...")
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
                print(f"[REALTIME] HTTP {response.status_code}, berhenti.")
                break

            body = response.json()

            # Guard: response bisa None atau strukturnya tidak sesuai
            if not isinstance(body, dict):
                print(f"[REALTIME] Respons tidak valid, berhenti.")
                break

            data_obj = body.get("data") or {}
            if not isinstance(data_obj, dict):
                print(f"[REALTIME] data.data tidak valid, berhenti.")
                break

            items = data_obj.get("items") or []

            if not items:
                print("[REALTIME] Tidak ada ulasan lagi.")
                break

            for item in items:
                current_ctime = item.get("ctime", 0)
                if current_ctime <= last_ctime:
                    print(f"[REALTIME] Ulasan lama ditemukan, berhenti.")
                    stop_scraping = True
                    break

                product_name = "Produk tidak diketahui"
                if item.get("product_items"):
                    product_name = item["product_items"][0].get("name", product_name)

                data = {
                    "nama pengguna"  : item.get("author_username", "Anonymous"),
                    "produk"         : product_name,
                    "review"         : item.get("comment", ""),
                    "rating"         : item.get("rating_star", 0),
                    "waktu transaksi": datetime.fromtimestamp(current_ctime).strftime("%Y-%m-%d %H:%M"),
                    "ctime"          : current_ctime,
                }
                producer.send(
                    KAFKA_TOPIC,
                    key=str(current_ctime).encode("utf-8"),
                    value=data,
                )
                print(f"[REALTIME] Terkirim: {data['nama pengguna']} | {data['produk']}")
                new_count += 1
                if current_ctime > max_ctime:
                    max_ctime = current_ctime

            if not stop_scraping:
                offset += 6
                print(f"[REALTIME] Halaman berikutnya... sleep {SCRAPE_INTERVAL}s")
                time.sleep(SCRAPE_INTERVAL)

        except Exception as e:
            print(f"[ERROR] {e}")
            break

    now_epoch = int(time.time())
    if new_count > 0:
        producer.flush()
        print(f"[REALTIME] Flush selesai. Total terkirim: {new_count} ulasan.")
        metadata[shop_key] = {
            "comment_time"               : max_ctime,
            "last_scraped_time_formatted": datetime.fromtimestamp(max_ctime).strftime("%Y-%m-%d %H:%M"),
            "last_run_time"              : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_run_epoch"             : now_epoch,
            "new_reviews_count"          : new_count,
        }
        save_metadata(metadata)
    else:
        print("[REALTIME] Tidak ada ulasan baru.")
        # Tetap perbarui last_run_epoch
        if shop_key in metadata:
            metadata[shop_key]["last_run_epoch"] = now_epoch
            metadata[shop_key]["last_run_time"]  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_metadata(metadata)

    return max_ctime


# ── Deteksi Mode ──────────────────────────────────────────────────
def is_catchup_needed(meta_entry: dict) -> bool:
    last_run_epoch = meta_entry.get("last_run_epoch", 0)
    if last_run_epoch == 0:
        return True
    gap = int(time.time()) - last_run_epoch
    return gap > CATCHUP_THRESHOLD_SECS


# ── Scrape & Produce (entry point per siklus) ─────────────────────
def scrape_and_produce(producer: KafkaProducer):
    if not SHOPEE_URL:
        print("[ERROR] SHOPEE_URL belum di-set!")
        return

    parts = SHOPEE_URL.split("/")
    if len(parts) < 6:
        print("[ERROR] Format SHOPEE_URL tidak valid!")
        return

    user_id  = parts[4]
    shop_id  = parts[5].replace("rating?shop_id=", "")
    shop_key = f"{user_id}_{shop_id}"

    cookies  = load_cookie(COOKIES_FILE)
    metadata = load_metadata()

    shop_meta  = metadata.get(shop_key, {})
    last_ctime = shop_meta.get("comment_time", 0)

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

    if is_catchup_needed(shop_meta):
        print(f"[MODE] CATCH-UP (pertama kali atau gap run > {CATCHUP_THRESHOLD_SECS}s)")
        asyncio.run(
            run_catchup(producer, shop_id, user_id, headers, last_ctime, metadata, shop_key)
        )
    else:
        print(f"[MODE] REALTIME (run terakhir < {CATCHUP_THRESHOLD_SECS}s yang lalu)")
        run_realtime(producer, shop_id, user_id, headers, last_ctime, metadata, shop_key)


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
    
