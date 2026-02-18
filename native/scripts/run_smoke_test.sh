#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 - <<'PY'
import os
from pathlib import Path

root = Path(os.environ.get("ROOT_DIR", ""))  # unused
print("Smoke test placeholder:")
print("- Verify libubodoom.so exists in native/out/")
print("- Verify service folder exists in ubo_service/070-doom/")
PY
