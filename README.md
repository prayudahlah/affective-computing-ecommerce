

# ROSBD Kelompok 4 - Kelas A
<p align="center">
  Anindya Artanti Pambudi | L0224002<br>
  Prayuda Afifan Handoyo | L0224008<br>
  Satria Manggala Putra Pratama | L0224024<br> 
  Viola Herfina Putri | L0224026<br> 
</p>

---
## Arsitektur

Data mengalir melalui 4 tahap: **Ingestion** (scrape Shopee → Kafka), **Preprocessing** (Spark → MongoDB → Debezium CDC → Kafka), **Inference** (Spark ML → PostgreSQL), **Visualisasi & Notifikasi** (Streamlit dashboard + Telegram alert).

![Pipeline](https://via.placeholder.com/800x100?text=Shopee+API+%E2%86%92+data-poller+%E2%86%92+Kafka+%E2%86%92+preprocess+%E2%86%92+MongoDB+%E2%86%92+Debezium+%E2%86%92+Kafka+%E2%86%92+inference+%E2%86%92+PostgreSQL+%E2%86%92+Streamlit+/+Telegram)

### Teknologi Utama

| Komponen | Teknologi |
|---|---|
| Message Broker | Apache Kafka 4.1.2 |
| Stream Processing | Apache Spark 4.1.2 Structured Streaming |
| Document Store | MongoDB 8.0 (Replica Set) |
| Change Data Capture | Debezium 3.1.2 |
| Relational DB | PostgreSQL 18 + PL/Python3u |
| Dashboard | Streamlit + Altair + SQLAlchemy |
| Notifikasi | PostgreSQL Trigger → Telegram Bot API |
| Orchestrasi | Docker Compose |

---

## Mode Deployment

### 1. Local (1 mesin)

Semua service jalan di satu mesin. Cocok untuk development/testing.

```bash
docker compose -f compose.dev.local.yaml --profile dev up -d --build
```

### 2. Distributed (4 mesin via Tailscale)

Service terdistribusi ke 4 perangkat yang terhubung via Tailscale. Setiap perangkat menjalankan profile masing-masing.

| Perangkat | Hostname | Profile | Layanan |
|---|---|---|---|
| Device 1 | nixia | `--profile device_1` | data-poller, kafka, kafka-init, kafka-ui |
| Device 2 | prayudahlah | `--profile device_2` | data-preprocess, spark-master, spark-worker, mongodb, mongo-express, debezium |
| Device 3 | anin | `--profile device_3` | ml-inference, spark-master, spark-worker, postgres |
| Device 4 | vioouw | `--profile device_4` | streamlit |

```bash
# Di setiap device, jalankan profile masing-masing:
docker compose -f compose.dev.distributed.yaml --profile device_X up -d --build
```

---

## Setup

### 1. Clone & Branch

```bash
git clone https://github.com/prayudahlah/affective-computing-ecommerce.git
cd affective-computing-ecommerce
```

### 2. Buat `.env`

```bash
cp .env.example .env
```

### 3. Konfigurasi Environment

| Variabel | Default | Keterangan |
|---|---|---|
| `SHOPEE_URL` | — | URL halaman rating toko Shopee |
| `SCRAPE_INTERVAL` | 10 | Jeda antar request (detik) |
| `POLL_INTERVAL` | 60 | Jeda siklus scraping (detik) |
| `CATCHUP_WORKERS` | 3 | Jumlah worker catch-up paralel |
| `DEVICE_1_IP` | 127.0.0.1 | Hostname/IP Kafka (device 1) |
| `DEVICE_2_IP` | 127.0.0.1 | Hostname/IP Spark master (device 2) |
| `DEVICE_3_IP` | 127.0.0.1 | Hostname/IP PostgreSQL (device 3) |
| `DEVICE_4_IP` | 127.0.0.1 | Hostname/IP Streamlit (device 4) |
| `KAFKA_HOST_PORT` | 9092 | Port Kafka |
| `MONGO_HOST_PORT` | 27017 | Port MongoDB |
| `INFERENCE_DB_HOST_PORT` | 5432 | Port PostgreSQL (host) |
| `INFERENCE_DB_USER` | postgres | User PostgreSQL |
| `INFERENCE_DB_PASSWORD` | postgres | Password PostgreSQL |
| `INFERENCE_DB_NAME` | postgres | Database PostgreSQL |
| `TELEGRAM_BOT_TOKEN` | — | Token bot Telegram |
| `TELEGRAM_CHAT_ID` | — | ID chat tujuan notifikasi |

> **Catatan:** Untuk mode distributed, set `DEVICE_X_IP` ke Tailscale MagicDNS atau IP Tailscale masing-masing perangkat.

### 4. Setup Telegram Alert (Opsional)

Alert otomatis terkirim via **PL/Python trigger** di PostgreSQL. Setup:

1. Buat bot via [@BotFather](https://t.me/BotFather), dapatkan token
2. Cari chat ID:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Isi token & chat ID di `.env`:
   ```
   TELEGRAM_BOT_TOKEN=7234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   TELEGRAM_CHAT_ID=-123456789
   ```
4. Service `postgres` akan menjalankan `init-telegram-config.sh` yang menyimpan kredensial via `ALTER SYSTEM SET`.

### 5. Jalankan

**Mode Local:**
```bash
docker compose -f compose.dev.local.yaml --profile dev up -d --build
```

**Mode Distributed:** jalankan perintah di atas di setiap device dengan profile masing-masing.

### 6. Verifikasi

Cek status container:
```bash
docker compose -f compose.dev.local.yaml --profile dev ps
```

Cek log inisialisasi:
```bash
# MongoDB Replica Set
docker compose logs mongodb-init

# Debezium Connector
docker compose logs debezium-register
```

Verifikasi Debezium:
```bash
curl http://localhost:8083/connectors/mongodb-source-connector/status
```

Akses dashboard:
- **Streamlit:** http://localhost:8501
- **Kafka UI:** http://localhost:8082
- **Mongo-express:** http://localhost:8084
- **Spark Master:** http://localhost:8080

---

## Alur Data Lengkap

```
[Shopee API]
    │  HTTP scraping (POLL_INTERVAL=60s)
    ▼
[data-poller] ──Kafka "polled-data"──▶ [data-preprocess]
(Device 1)                               (Spark Streaming, Device 2)
                                             │
                                             │ slang normalization, stemming,
                                             │ TF-IDF vectorization, fitur dasar
                                             ▼
                                         [MongoDB]  (collection: ecommerce.reviews)
                                             │
                                             │ Debezium CDC (Replica Set rs0)
                                             ▼
                                    Kafka "cdc.mongodb.ecommerce.reviews"
                                             │
                                             ▼
                                    [ml-inference]  (Spark Streaming, Device 3)
                                             │
                                             │ reconstruct TF-IDF vectors,
                                             │ predict sentiment & emotion
                                             ▼
                                        [PostgreSQL]
                                          ↙        ↘
                                  [Streamlit]    [Telegram Bot]
                                  (Dashboard)    (Notifikasi)
```

### Pipeline Detail

1. **data-poller** — Scraping Shopee Open API secara periodik. Dua mode: catch-up (paralel, 3 worker) untuk data historis, dan realtime (sinkron, sequential) untuk data baru. Output ke Kafka topic `polled-data`.

2. **data-preprocess** — Spark Structured Streaming membaca Kafka. Preprocessing teks Bahasa Indonesia: normalisasi slang, tokenisasi, stopword removal, stemming (Sastrawi), negation handling, TF-IDF vectorization (1500 fitur), ekstraksi 11 fitur dasar. Output ke MongoDB.

3. **Debezium CDC** — MongoDB Replica Set → change stream → Kafka topic `cdc.mongodb.ecommerce.reviews`.

4. **ml-inference** — Spark Structured Streaming membaca CDC Kafka. Rekonstruksi vektor TF-IDF dari sparse indices/values, prediksi sentimen (Logistic Regression, 2 kelas) dan emosi (SMOTE + Logistic Regression, 5 kelas). Output ke PostgreSQL + deteksi anomali (alert).

5. **Streamlit Dashboard** — Visualisasi real-time: KPI cards, time series rating, distribusi sentimen/emosi, tabel review & alert.

6. **Telegram Notification** — PostgreSQL trigger (PL/Python3u) → HTTP POST ke Telegram API.

---

## Catatan

- `data-poller` akan restart otomatis setelah selesai scraping — normal jika tidak ada ulasan baru.
- Untuk scraping dengan cookie (akses lebih banyak data), letakkan file `cookies.json` di folder `app/data-poller/`.
- Folder `storage/` tidak ikut di-push ke git (berisi data runtime).
- Hapus folder checkpoint (`/app/data/checkpoint`) jika ingin memulai streaming dari awal.
