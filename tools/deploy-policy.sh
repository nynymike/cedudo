#!/usr/bin/env bash
# Deploy policy/cedudo.cjar to the root-owned enforcement path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/policy/cedudo.cjar"
DEST="/opt/cedudo/cedudo.cjar"

if [[ ! -f "${SRC}" ]]; then
  echo "error: missing ${SRC}; run tools/build-cjar.sh first" >&2
  exit 1
fi

# Validate ZIP / .cjar structure
if ! unzip -t "${SRC}" > /dev/null; then
  echo "error: ${SRC} is not a valid ZIP/.cjar archive" >&2
  exit 1
fi

if ! unzip -l "${SRC}" | grep -q 'metadata.json'; then
  echo "error: ${SRC} is missing metadata.json (not a Cedarling policy store)" >&2
  exit 1
fi

if ! unzip -l "${SRC}" | grep -q 'schema.cedarschema'; then
  echo "error: ${SRC} is missing schema.cedarschema (not a Cedarling policy store)" >&2
  exit 1
fi

if ! unzip -l "${SRC}" | grep -q 'policies/'; then
  echo "error: ${SRC} is missing policies/ (not a Cedarling policy store)" >&2
  exit 1
fi

sudo mkdir -p /opt/cedudo
sudo cp "${SRC}" "${DEST}"
sudo chown root:root "${DEST}"
sudo chmod 0644 "${DEST}"

echo "Deployed ${SRC} -> ${DEST}"
ls -l "${DEST}"
