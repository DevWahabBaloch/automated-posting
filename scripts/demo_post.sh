#!/usr/bin/env bash
# Publish one real post through the running API and record the evidence in
# docs/sample-run.md. Start the API first (VS Code task "Run API").
# Usage: ./scripts/demo_post.sh [base_url]
set -euo pipefail
cd "$(dirname "$0")/.."

BASE_URL="${1:-http://localhost:4000}"
OUT="docs/sample-run.md"
PY="${PYTHON:-.venv/bin/python}"
MESSAGE="Automated multi-platform posting with FastAPI: one API call, many platforms. https://github.com/DevWahabBaloch/automated-posting"

curl -sf "$BASE_URL/health" >/dev/null || { echo "API is not running at $BASE_URL - start the 'Run API' task first." >&2; exit 1; }

pretty() { "$PY" -m json.tool --no-ensure-ascii; }
post() { curl -s -X POST "$BASE_URL/posting" -H "Content-Type: application/json" -d "$1"; }
curl_cmd() {  # $1 = body to show
  printf '```bash\ncurl -X POST %s/posting -H "Content-Type: application/json" \\\n  -d '"'"'%s'"'"'\n```\n\n' "$BASE_URL" "$1"
}
block() {  # $1 = description, $2 = request body, $3 = optional body to display
  printf '### %s\n\n' "$1"
  curl_cmd "${3:-$2}"
  printf '```json\n%s\n```\n\n' "$(post "$2" | pretty)"
}

PAYLOAD=$("$PY" -c 'import json,sys; print(json.dumps({"message": sys.argv[1]}))' "$MESSAGE")
RESULT=$(post "$PAYLOAD" | pretty)

{
  echo "# Sample run"
  echo
  echo "Recorded with \`scripts/demo_post.sh\` on $(date '+%Y-%m-%d %H:%M %Z') against a local server"
  echo "(\`uvicorn app.main:app --port 4000\`). The \`posted_url\` values are live, public posts."
  echo
  echo "## Platforms"
  echo
  echo '```json'
  curl -s "$BASE_URL/platforms" | pretty
  echo '```'
  echo
  echo "## Publishing a message"
  echo
  curl_cmd "$PAYLOAD"
  echo '```json'
  echo "$RESULT"
  echo '```'
  echo
  echo "## Validation errors"
  echo
  block "No CTA link" '{"message": "No link in this message"}'
  block "More than one link" '{"message": "Two links https://a.example and https://b.example"}'
  block "Non-public host" '{"message": "Local link https://localhost:8000"}'
  block "Unsupported scheme" '{"message": "Bad scheme ftp://example.com/file"}'
  block "Caller tries to choose platforms" '{"message": "Our platform https://example.com", "platforms": ["Discord"]}'
  block "Over 200 characters" "{\"message\": \"$(printf 'a%.0s' $(seq 1 190)) https://example.com\"}" \
    '{"message": "aaaa…(190 characters)… https://example.com"}'
} > "$OUT"

echo "$RESULT" | "$PY" -c '
import json, sys
for r in json.load(sys.stdin)["results"]:
    print(r["status"].ljust(8), r["platform"].ljust(15), r["posted_url"] or r["error"])
'
echo "Saved $OUT"
