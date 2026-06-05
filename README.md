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

> ⚠️ Langkah ini **wajib dilakukan sekali** setiap kali folder `storage/mongodb/` baru (fresh clone atau dihapus).

**Linux / Mac:**
```bash
docker compose -f compose.dev.local.yaml --profile dev exec mongodb mongosh --eval "rs.initiate({_id: 'rs0', members: [{_id: 0, host: 'mongodb:27017'}]})"
```

**Windows (PowerShell):**
```powershell
docker compose -f compose.dev.local.yaml --profile dev exec mongodb mongosh --eval "rs.initiate({_id: 'rs0', members: [{_id: 0, host: 'mongodb:27017'}]})"
```

Verifikasi berhasil jika output mengandung `"ok": 1`.

### 5. Daftarkan Debezium MongoDB Connector

> ⚠️ Langkah ini **wajib dilakukan sekali** setiap kali container Debezium di-recreate.

**Linux / Mac:**
```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mongodb-source-connector",
    "config": {
      "connector.class": "io.debezium.connector.mongodb.MongoDbConnector",
      "mongodb.connection.string": "mongodb://mongodb:27017/?replicaSet=rs0",
      "topic.prefix": "cdc.mongodb",
      "database.include.list": "ecommerce",
      "collection.include.list": "ecommerce.reviews",
      "snapshot.mode": "initial"
    }
  }'
```

**Windows (PowerShell):**
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8083/connectors" -ContentType "application/json" -Body '{
  "name": "mongodb-source-connector",
  "config": {
    "connector.class": "io.debezium.connector.mongodb.MongoDbConnector",
    "mongodb.connection.string": "mongodb://mongodb:27017/?replicaSet=rs0",
    "topic.prefix": "cdc.mongodb",
    "database.include.list": "ecommerce",
    "collection.include.list": "ecommerce.reviews",
    "snapshot.mode": "initial"
  }
}'
```

Verifikasi connector berjalan:

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
- Folder `storage/` tidak ikut di-push ke git (berisi data runtime). Jangan lupa jalankan langkah 4 dan 5 setiap kali fresh clone.