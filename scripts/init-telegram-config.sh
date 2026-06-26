#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    ALTER SYSTEM SET telegram.bot_token = '${TELEGRAM_BOT_TOKEN}';
    ALTER SYSTEM SET telegram.chat_id = '${TELEGRAM_CHAT_ID}';
    SELECT pg_reload_conf();
EOSQL
