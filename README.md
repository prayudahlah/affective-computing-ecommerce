# Affective Computing E-Commerce
---

## Cara Setup dari Awal

### 1. Clone repository

```bash
git clone https://github.com/prayudahlah/affective-computing-ecommerce.git
cd affective-computing-ecommerce
git checkout mongodb
```

### 2. Buat file `.env`

Salin dari contoh yang tersedia, lalu sesuaikan isinya:

```bash
cp .env.example .env
```

Variabel yang perlu diperhatikan:

| Variabel | Keterangan |
|----------|-----------|
| `SHOPEE_URL` | URL halaman rating toko Shopee yang ingin di-scrape |
| `SCRAPE_INTERVAL` | Jeda antar request scraping (detik), default `10` |
| `MONGO_USER` / `MONGO_PASSWORD` | Kredensial MongoDB |
| `INFERENCE_DB_USER` / `INFERENCE_DB_PASSWORD` | Kredensial PostgreSQL |
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram dari @BotFather (untuk PL/Python, isi langsung di `scripts/telegram-alert-function.sql`) |
| `TELEGRAM_CHAT_ID` | ID chat tujuan alert Telegram (untuk PL/Python, isi langsung di `scripts/telegram-alert-function.sql`) |

### 2.5. Setup Telegram Alert (di PostgreSQL laptop 3)

Alert otomatis terkirim ke Telegram via **PL/Python** — fungsi PostgreSQL yang dipanggil trigger setiap ada INSERT ke tabel `alerts`.

#### 2.5.1. Buat bot Telegram

1. Buka @BotFather di Telegram, ketik `/newbot`, ikuti petunjuk
2. Simpan token (contoh: `7234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`)
3. Kirim pesan ke bot kamu, lalu cek chat ID:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
4. Ganti `TOKEN` & `CHAT_ID` di `scripts/telegram-alert-function.sql`

#### 2.5.2. Install plpython3u di PostgreSQL

```bash
# Jika pakai Docker, butuh image postgres dengan Python:
# docker.io/postgres:18.3-bookworm (bukan alpine)
```

```sql
CREATE EXTENSION IF NOT EXISTS plpython3u;
```

#### 2.5.3. Jalankan fungsi forward_alert_to_telegram

```bash
psql -U postgres -d postgres -f scripts/telegram-alert-function.sql
```

#### 2.5.4. Buat trigger yang memanggil fungsi

```sql
CREATE TRIGGER trg_forward_alert
    AFTER INSERT ON alerts
    FOR EACH ROW
    EXECUTE FUNCTION forward_alert_to_telegram();
```

### 3. Jalankan semua container

```bash
docker compose -f compose.dev.local.yaml --profile dev up -d --build
```

Tunggu semua container berstatus `healthy` atau `running`:

```bash
docker compose -f compose.dev.local.yaml --profile dev ps
```

### 4. Inisialisasi MongoDB Replica Set

Otomatis via service `mongodb-init`. Cek log:

```bash
docker compose -f compose.dev.local.yaml --profile dev logs mongodb-init
```

Output: `Replica set initialized` atau `Replica set already initialized`.

### 5. Registrasi Debezium Connector

Otomatis via service `debezium-register`. Cek log:

```bash
docker compose -f compose.dev.local.yaml --profile dev logs debezium-register
```

Output: `Success (HTTP 201)` atau `Success (HTTP 409)`. Verifikasi status connector:

**Linux / Mac:**
```bash
curl http://localhost:8083/connectors/mongodb-source-connector/status
```

**Windows (PowerShell):**
```powershell
Invoke-RestMethod -Uri "http://localhost:8083/connectors/mongodb-source-connector/status"
```

Output harus mengandung `"state": "RUNNING"`.

---

## Catatan

- `data-poller` akan restart otomatis setelah selesai scraping — ini perilaku normal jika tidak ada ulasan baru.
- Untuk scraping dengan cookie (akses lebih banyak data), letakkan file `cookies.json` di folder `app/data-poller/`.
- Folder `storage/` tidak ikut di-push ke git (berisi data runtime). Jangan lupa jalankan langkah 4 setiap kali fresh clone.