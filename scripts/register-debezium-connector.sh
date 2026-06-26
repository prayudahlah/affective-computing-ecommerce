#!/bin/sh
# Register Debezium MongoDB source connector

DEBEZIUM_HOST="${1:-debezium}"
DEBEZIUM_PORT="${2:-8083}"
RETRIES=10
DELAY=3

echo "[REGISTER] Waiting for Debezium at ${DEBEZIUM_HOST}:${DEBEZIUM_PORT}..."

for i in $(seq 1 $RETRIES); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${DEBEZIUM_HOST}:${DEBEZIUM_PORT}/connectors" 2>/dev/null || echo "000")
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo "[REGISTER] Debezium ready (attempt $i)"
    break
  fi
  
  if [ "$i" = "$RETRIES" ]; then
    echo "[REGISTER] Debezium not ready after ${RETRIES} attempts, exiting"
    exit 1
  fi
  
  echo "[REGISTER] Waiting... ($i/$RETRIES)"
  sleep "$DELAY"
done

MONGO_URI="${MONGO_URI:-mongodb://mongodb:27017/?replicaSet=rs0}"

echo "[REGISTER] Registering mongodb-source-connector..."
echo "[REGISTER] Mongo URI: ${MONGO_URI}"

RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "http://${DEBEZIUM_HOST}:${DEBEZIUM_PORT}/connectors" \
  -H "Content-Type: application/json" \
  -d "$(cat <<CONFIG
{
  "name": "mongodb-source-connector",
  "config": {
    "connector.class": "io.debezium.connector.mongodb.MongoDbConnector",
    "mongodb.connection.string": "${MONGO_URI}",
    "topic.prefix": "cdc.mongodb",
    "database.include.list": "ecommerce",
    "collection.include.list": "ecommerce.reviews",
    "snapshot.mode": "initial"
  }
}
CONFIG
)")

if [ "$RESPONSE" = "201" ] || [ "$RESPONSE" = "409" ]; then
  echo "[REGISTER] Success (HTTP ${RESPONSE})"
  exit 0
else
  echo "[REGISTER] Failed (HTTP ${RESPONSE})"
  curl -s "http://${DEBEZIUM_HOST}:${DEBEZIUM_PORT}/connectors"
  exit 1
fi
