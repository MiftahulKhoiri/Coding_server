#!/usr/bin/env bash
# Pasang runtime yang tidak ada di repo apt tanpa sudo, khusus ARM64:
#  - .NET SDK 8 (dotnet-install.sh resmi Microsoft) -> ~/.dotnet
#  - PHP CLI 8.3 statis (static-php-cli, linux-aarch64)  -> ~/.local/opt/php
# Bila apt tersedia (sudo), lebih baik: sudo apt install php-cli
set -uo pipefail
source "$(dirname "$0")/common.sh"
mkdir -p "$HOME/.local/bin" "$HOME/.local/opt"
ARCH=$(uname -m)
if ! command -v dotnet >/dev/null; then
  c_info "Memasang .NET SDK 8..."
  curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 8.0 --install-dir "$HOME/.dotnet" >/dev/null \
    && ln -sf "$HOME/.dotnet/dotnet" "$HOME/.local/bin/dotnet" && c_ok ".NET $("$HOME/.dotnet/dotnet" --version)" \
    || c_warn ".NET gagal dipasang"
else c_ok ".NET sudah ada ($(dotnet --version))"; fi
if ! command -v php >/dev/null; then
  if [ "$ARCH" = "aarch64" ]; then
    c_info "Memasang PHP CLI statis..."
    mkdir -p "$HOME/.local/opt/php"
    curl -fsSL -o /tmp/php.tgz "https://dl.static-php.dev/static-php-cli/common/php-8.3.14-cli-linux-aarch64.tar.gz" \
      && tar xzf /tmp/php.tgz -C "$HOME/.local/opt/php" && ln -sf "$HOME/.local/opt/php/php" "$HOME/.local/bin/php" \
      && c_ok "$(php -v | head -1)" || c_warn "PHP gagal dipasang (alternatif: sudo apt install php-cli)"
  else c_warn "PHP tidak ada: sudo apt install php-cli"; fi
else c_ok "PHP sudah ada"; fi
for c in gcc g++ javac go node sqlite3; do
  command -v $c >/dev/null && c_ok "$c tersedia" || c_warn "$c belum ada (sudo apt install: gcc g++ default-jdk golang nodejs sqlite3)"
done
