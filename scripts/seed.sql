-- Seed data untuk dashboard ASUS Monitoring Sentimen Shopee
-- Jalankan: docker exec -i affective-computing-ecommerce-postgres-1 psql -U postgres -d postgres < scripts/seed.sql

BEGIN;

TRUNCATE TABLE alerts, reviews, model_metadata RESTART IDENTITY CASCADE;

-- ============================================================
-- 1. MODEL METADATA
-- ============================================================
INSERT INTO model_metadata (model_name, f1_score_macro, is_active, task_type)
VALUES
    ('sentiment_model_v1', 0.8567, TRUE, 'sentiment'),
    ('emotion_model_v1',   0.7821, TRUE, 'emotion');

-- ============================================================
-- 2. PRODUCTS & REVIEW DATA
-- ============================================================
DO $$
DECLARE
    products TEXT[] := ARRAY[
        'ASUS ROG Phone 7',
        'ASUS Zenbook 14 OLED',
        'ASUS Vivobook 15',
        'ASUS TUF Gaming A15',
        'ASUS ROG Strix G16',
        'ASUS ProArt Studiobook 16',
        'ASUS ExpertBook B9',
        'ASUS Zenfone 10'
    ];
    usernames TEXT[] := ARRAY[
        'BudiSantoso', 'SitiNurhaliza', 'AhmadFauzi', 'DewiLestari',
        'RizkyPratama', 'MayaAnggraini', 'DimasAditya', 'PutriAyunda',
        'HendraGunawan', 'RatnaSari', 'AdiNugroho', 'WulanDari',
        'FebrianHakim', 'IntanPermata', 'GilangRamadhan', 'CitraKirana',
        'EkoWibowo', 'RinaMelati', 'ArifSetiawan', 'NadiaPramesti'
    ];
    pos_comments TEXT[] := ARRAY[
        'Barang sampai dengan cepat, kualitas bagus sesuai ekspektasi!',
        'Produk original, recommended banget buat kerja dan gaming',
        'Kualitas display sangat jernih, cocok untuk desain grafis',
        'Performa kencang, ga pernah lag buat multitasking',
        'Baterai tahan lama, bisa dipakai kerja seharian penuh',
        'Desainnya elegant dan premium, puas banget dengan pembelian ini',
        'Keyboard nyaman dipakai ngetik lama, backlightnya keren',
        'Fitur lengkap, harga sesuai kualitas, worth it banget',
        'Pengiriman cepat, packing rapi, produk tidak ada cacat',
        'Sudah 3 bulan pemakaian, masih mulus seperti baru, mantap!',
        'Suhu tetap adem walau dipakai main game berat',
        'Audio jernih, cocok buat nonton film dan dengerin musik'
    ];
    neg_comments TEXT[] := ARRAY[
        'Barang datang terlambat 3 hari dari estimasi',
        'Keyboard ada beberapa tombol yang macet setelah seminggu',
        'Baterai boros, tidak sesuai dengan yang diiklankan',
        'Sering overheating padahal hanya dipakai browsing',
        'Kualitas build kurang solid, ada celah di bagian body',
        'Layar kurang cerah, warna agak pudar dibanding ekspektasi',
        'Fans berisik sekali, mengganggu saat bekerja di malam hari',
        'Touchpad tidak responsif, kursor sering loncat-loncat',
        'Spek tidak sesuai deskripsi, merasa dibohongi',
        'Harga terlalu mahal untuk kualitas yang didapatkan',
        'Garansi sulit diklaim, CS lambat merespon',
        'Software sering crash, harus restart berkali-kali'
    ];
    emo_pos TEXT[] := ARRAY['Senang', 'Puas', 'Netral'];
    emo_neg TEXT[] := ARRAY['Kecewa', 'Marah', 'Sedih'];
    rnd REAL;
    rating INT;
    sentiment TEXT;
    emotion TEXT;
    comment TEXT;
    pid INT;
    uid INT;
    cid INT;
BEGIN
    FOR i IN 1..120 LOOP
        rnd := random();
        pid := 1 + floor(random() * array_length(products, 1))::int;
        uid := 1 + floor(random() * array_length(usernames, 1))::int;

        IF rnd < 0.70 THEN
            rating := 4 + floor(random() * 2)::int;
        ELSIF rnd < 0.85 THEN
            rating := 3;
        ELSE
            rating := 1 + floor(random() * 2)::int;
        END IF;

        IF rating >= 4 THEN
            sentiment := 'Positive';
            emotion := emo_pos[1 + floor(random() * array_length(emo_pos, 1))::int];
            cid := 1 + floor(random() * array_length(pos_comments, 1))::int;
            comment := pos_comments[cid];
        ELSIF rating = 3 THEN
            IF random() < 0.5 THEN
                sentiment := 'Positive';
                emotion := emo_pos[1 + floor(random() * array_length(emo_pos, 1))::int];
                cid := 1 + floor(random() * array_length(pos_comments, 1))::int;
                comment := pos_comments[cid];
            ELSE
                sentiment := 'Negative';
                emotion := emo_neg[1 + floor(random() * array_length(emo_neg, 1))::int];
                cid := 1 + floor(random() * array_length(neg_comments, 1))::int;
                comment := neg_comments[cid];
            END IF;
        ELSE
            sentiment := 'Negative';
            emotion := emo_neg[1 + floor(random() * array_length(emo_neg, 1))::int];
            cid := 1 + floor(random() * array_length(neg_comments, 1))::int;
            comment := neg_comments[cid];
        END IF;

        INSERT INTO reviews (comment_id, buyer_username, product_name, comment, rating_star, create_time, sentiment, emotion)
        VALUES (
            'SEED-' || encode(md5((i::text || random()::text))::bytea, 'hex'),
            usernames[uid],
            products[pid],
            comment,
            rating,
            NOW() - (floor(random() * 30)::int || ' days')::interval
                - (floor(random() * 24)::int || ' hours')::interval
                - (floor(random() * 60)::int || ' minutes')::interval,
            sentiment,
            emotion
        );
    END LOOP;
END $$;

-- ============================================================
-- 3. ALERTS
-- ============================================================
WITH review_sample AS (
    SELECT id, comment, rating_star, create_time
    FROM reviews
    WHERE rating_star <= 3
    ORDER BY random()
    LIMIT 10
)
INSERT INTO alerts (alert_type, triggered_at, comment, rating_avg, review_id)
SELECT
    CASE WHEN random() < 0.5 THEN 'rating_drop' ELSE 'sentiment_negative' END,
    r.create_time + (floor(random() * 4)::int || ' hours')::interval,
    r.comment,
    round((1 + random() * 2.5)::numeric, 2),
    r.id
FROM review_sample r;

COMMIT;
