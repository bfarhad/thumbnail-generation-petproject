#!/bin/bash
# Build the Azure Function deployment package.
# Installs dependencies into src/ so Terraform's archive_file picks them up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
SRC="$ROOT/src"

echo "Installing Python dependencies into $SRC..."
pip install \
  --target "$SRC" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --upgrade \
  -r "$ROOT/requirements.txt"

echo "Build complete. Run 'terraform apply' from terraform/ to deploy."
