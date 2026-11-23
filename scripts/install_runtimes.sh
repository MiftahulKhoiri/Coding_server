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
# Language server untuk editor (tanpa sudo): clangd (wheel resmi ARM64 dari PyPI) di venv server,
# pyright (npm) di .lsp/. Keduanya ikut terhapus oleh uninstall.sh.
if [ -x "$PY" ]; then
  if "$PY" -c "import clangd" 2>/dev/null; then c_ok "clangd sudah ada ($("$VENV/bin/clangd" --version 2>/dev/null | head -1))"
  else
    c_info "Memasang clangd (LSP C/C++)..."
    "$PY" -m pip install -q clangd && c_ok "$("$VENV/bin/clangd" --version | head -1)" || c_warn "clangd gagal dipasang (opsional)"
  fi
else c_warn "venv belum ada: clangd dilewati (jalankan install.sh)"; fi
if [ -f "$BASE/.lsp/node_modules/pyright/langserver.index.js" ]; then c_ok "pyright sudah ada"
elif command -v npm >/dev/null; then
  c_info "Memasang pyright (LSP Python)..."
  mkdir -p "$BASE/.lsp" && npm install --prefix "$BASE/.lsp" --no-audit --no-fund --silent pyright@1 \
    && c_ok "pyright $("$BASE/.lsp/node_modules/.bin/pyright" --version 2>/dev/null | awk '{print $2}')" || c_warn "pyright gagal dipasang (opsional)"
else c_warn "npm tidak ada: pyright dilewati (sudo apt install npm)"; fi
for c in gcc g++ javac go node sqlite3 make cmake; do
  command -v $c >/dev/null && c_ok "$c tersedia" || c_warn "$c belum ada (sudo apt install: gcc g++ default-jdk golang nodejs sqlite3 make cmake ninja-build)"
done
