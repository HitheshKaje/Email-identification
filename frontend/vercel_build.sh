#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FLUTTER_VERSION="${FLUTTER_VERSION:-3.50.1}"
FLUTTER_ROOT="${FLUTTER_ROOT:-$HOME/.flutter-sdk}"
API_URL="${JOBMAIL_API_URL:-https://jobmail-backend-tzwt.onrender.com}"
export PUB_CACHE="${PUB_CACHE:-$HOME/.pub-cache}"

if ! command -v flutter >/dev/null 2>&1; then
  if [ ! -x "$FLUTTER_ROOT/bin/flutter" ]; then
    echo "Installing Flutter SDK ($FLUTTER_VERSION) into $FLUTTER_ROOT..."
    rm -rf "$FLUTTER_ROOT"
    if ! git clone --depth 1 --branch "$FLUTTER_VERSION" https://github.com/flutter/flutter.git "$FLUTTER_ROOT"; then
      echo "Falling back to Flutter stable channel..."
      rm -rf "$FLUTTER_ROOT"
      git clone --depth 1 --branch stable https://github.com/flutter/flutter.git "$FLUTTER_ROOT"
    fi
  fi
  export PATH="$FLUTTER_ROOT/bin:$PATH"
fi

git config --global --add safe.directory "$FLUTTER_ROOT" >/dev/null 2>&1 || true

flutter --version
flutter config --no-analytics --enable-web >/dev/null 2>&1 || true
flutter precache --web

flutter pub get
flutter build web --release --no-wasm-dry-run --dart-define="JOBMAIL_API_URL=${API_URL}"

test -f "build/web/index.html"
test -f "build/web/main.dart.js"
echo "Flutter Web build ready at $SCRIPT_DIR/build/web"
