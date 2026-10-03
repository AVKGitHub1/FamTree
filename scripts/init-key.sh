#!/usr/bin/env bash
# Create the database encryption key, readable only by you.
# Usage: scripts/init-key.sh [path]   (default: ~/.config/famtree/encryption.key)
set -euo pipefail

KEY_PATH="${1:-$HOME/.config/famtree/encryption.key}"

if [[ -e "$KEY_PATH" ]]; then
  echo "Key already exists at $KEY_PATH; refusing to overwrite it." >&2
  echo "Replacing the key makes existing encrypted data unreadable." >&2
  exit 1
fi

umask 077
mkdir -p "$(dirname "$KEY_PATH")"
chmod 700 "$(dirname "$KEY_PATH")"
if command -v openssl >/dev/null 2>&1; then
  openssl rand -hex 32 > "$KEY_PATH"
else
  python3 -c 'import secrets; print(secrets.token_hex(32))' > "$KEY_PATH"
fi
chmod 600 "$KEY_PATH"

echo "Created $KEY_PATH"
echo "Back this file up somewhere safe and separate from the data backups."
echo "If it is lost, the encrypted family tree cannot be recovered."
