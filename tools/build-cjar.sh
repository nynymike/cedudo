#!/usr/bin/env bash
# Package the AuthZEN policy store directory into cedudo.cjar (ZIP archive).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STORE="${ROOT}/policy/store"
OUT="${ROOT}/policy/cedudo.cjar"

if [[ ! -d "${STORE}" ]]; then
  echo "error: policy store directory not found: ${STORE}" >&2
  exit 1
fi

if [[ ! -f "${STORE}/metadata.json" ]]; then
  echo "error: missing required metadata.json in ${STORE}" >&2
  exit 1
fi

if [[ ! -d "${STORE}/policies" ]] || ! compgen -G "${STORE}/policies/*" > /dev/null; then
  echo "error: policies/ must contain at least one policy file" >&2
  exit 1
fi

# Basic AuthZEN metadata checks
python3 - <<'PY' "${STORE}/metadata.json"
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    meta = json.load(fh)
required = ("policy_engine", "policy_engine_version", "policy_store")
missing = [k for k in required if k not in meta]
if missing:
    raise SystemExit(f"metadata.json missing keys: {', '.join(missing)}")
ps = meta["policy_store"]
for key in ("id", "name"):
    if key not in ps:
        raise SystemExit(f"policy_store missing required field: {key}")
store_id = ps["id"]
if not (15 <= len(store_id) <= 64) or any(c not in "0123456789abcdef" for c in store_id.lower()):
    raise SystemExit("policy_store.id must be a hexadecimal string of 15–64 characters")
print("metadata.json OK")
PY

# Require @id() on each .cedar policy (AuthZEN / Cedar convention)
for policy in "${STORE}/policies"/*.cedar; do
  if ! grep -qE '@id\("' "${policy}"; then
    echo "error: policy missing @id(...): ${policy}" >&2
    exit 1
  fi
  # Exactly one policy document: exactly one trailing semicolon at top-level is hard;
  # enforce a single @id annotation as a practical workshop check.
  count="$(grep -cE '@id\("' "${policy}" || true)"
  if [[ "${count}" -ne 1 ]]; then
    echo "error: expected exactly one @id(...) in ${policy}" >&2
    exit 1
  fi
done

rm -f "${OUT}"
(
  cd "${STORE}"
  zip -r "${OUT}" . \
    -x "*.DS_Store" \
    -x "**/.DS_Store" \
    -x "*/.git/*"
)

echo "Wrote ${OUT}"
unzip -l "${OUT}"
