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