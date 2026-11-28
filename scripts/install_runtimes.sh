#!/usr/bin/env bash
# Pasang runtime yang tidak ada di repo apt tanpa sudo, khusus ARM64:
#  - .NET SDK 8 (dotnet-install.sh resmi Microsoft) -> ~/.dotnet
#  - PHP CLI 8.3 statis (static-php-cli, linux-aarch64)  -> ~/.local/opt/php
# Bila apt tersedia (sudo), lebih baik: sudo apt install php-cli
# Runtime yang benar-benar dipasang skrip ini dicatat di $RUNTIME_MANIFEST agar
# uninstall.sh --remove-runtimes hanya menghapus yang memang milik CODING_SERVER.
set -uo pipefail
source "$(dirname "$0")/common.sh"
mkdir -p "$HOME/.local/bin" "$HOME/.local/opt"
ARCH=$(uname -m)
record() { mkdir -p "$(dirname "$RUNTIME_MANIFEST")"; grep -qx "$1" "$RUNTIME_MANIFEST" 2>/dev/null || echo "$1" >> "$RUNTIME_MANIFEST"; }
if ! command -v dotnet >/dev/null; then
  c_info "Memasang .NET SDK 8..."
  curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 8.0 --install-dir "$HOME/.dotnet" >/dev/null \
    && ln -sf "$HOME/.dotnet/dotnet" "$HOME/.local/bin/dotnet" && record dotnet \
    && c_ok ".NET $("$HOME/.dotnet/dotnet" --version)" \
    || c_warn ".NET gagal dipasang"
  rm -f /tmp/dotnet-install.sh
else c_ok ".NET sudah ada ($(dotnet --version))"; fi
if ! command -v php >/dev/null; then
  if [ "$ARCH" = "aarch64" ]; then
    c_info "Memasang PHP CLI statis..."
    mkdir -p "$HOME/.local/opt/php"
    curl -fsSL -o /tmp/php.tgz "https://dl.static-php.dev/static-php-cli/common/php-8.3.14-cli-linux-aarch64.tar.gz" \
      && tar xzf /tmp/php.tgz -C "$HOME/.local/opt/php" && ln -sf "$HOME/.local/opt/php/php" "$HOME/.local/bin/php" \
      && record php && c_ok "$(php -v | head -1)" || c_warn "PHP gagal dipasang (alternatif: sudo apt install php-cli)"
    rm -f /tmp/php.tgz
  else c_warn "PHP tidak ada: sudo apt install php-cli"; fi
else c_ok "PHP sudah ada"; fi
# Language server & formatter untuk editor (tanpa sudo): paket pip di venv server, paket npm di .lsp/.
# Semuanya ikut terhapus oleh uninstall.sh (venv & .lsp dihapus).
pip_tool() {  # pip_tool NAMA_PAKET FILE_PENANDA KETERANGAN
  if [ ! -x "$PY" ]; then c_warn "venv belum ada: $1 dilewati (jalankan install.sh)"; return; fi
  if [ -e "$2" ]; then c_ok "$1 sudah ada ($3)"; return; fi
  c_info "Memasang $1 ($3)..."
  "$PY" -m pip install -q "$1" && c_ok "$1 terpasang" || c_warn "$1 gagal dipasang (opsional)"
}
PYV_DIR="$VENV/lib/python$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
pip_tool clangd "$VENV/bin/clangd" "LSP C/C++"
pip_tool clang-format "$PYV_DIR/site-packages/clang_format/data/bin/clang-format" "format C/C++/Java/C#"
pip_tool ruff "$VENV/bin/ruff" "format Python"
npm_tool() {  # npm_tool PAKET@VERSI FILE_PENANDA(relatif .lsp) KETERANGAN
  if [ -e "$BASE/.lsp/$2" ]; then c_ok "${1%@*} sudah ada ($3)"; return; fi
  if ! command -v npm >/dev/null; then c_warn "npm tidak ada: ${1%@*} dilewati (sudo apt install npm)"; return; fi
  c_info "Memasang ${1%@*} ($3)..."
  mkdir -p "$BASE/.lsp" && npm install --prefix "$BASE/.lsp" --no-audit --no-fund --silent "$1" \
    && c_ok "${1%@*} terpasang" || c_warn "${1%@*} gagal dipasang (opsional)"
}
npm_tool pyright@1 node_modules/pyright/langserver.index.js "LSP Python"
npm_tool prettier@3 node_modules/prettier/bin/prettier.cjs "format JS/TS/CSS/HTML/JSON/YAML/Markdown"
for c in gcc g++ javac go node sqlite3 make cmake; do
  command -v $c >/dev/null && c_ok "$c tersedia" || c_warn "$c belum ada (sudo apt install: gcc g++ default-jdk golang nodejs sqlite3 make cmake ninja-build)"
done
