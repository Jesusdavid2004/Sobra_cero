#!/usr/bin/env sh
set -eu
BASE="${API_URL:-http://localhost:8000/api/v1}"
TOKEN=$(curl -fsS -X POST "$BASE/auth/register" -H 'content-type: application/json' -d '{"email":"smoke@example.com","password":"password123"}' | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
curl -fsS "$BASE/shops" -H "authorization: Bearer $TOKEN" >/dev/null
echo "Smoke test passed"
