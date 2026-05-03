#!/bin/zsh
# run.sh — kill all RoXBot instances, rebuild, and launch exactly one.
set -e
cd "$(dirname "$0")"

echo "🛑 Stopping any running RoXBot instances…"
pkill -x RoXBot 2>/dev/null || true
pkill -f "RoXBot.app/Contents/MacOS/RoXBot" 2>/dev/null || true
sleep 1

echo "🔨 Building…"
swift build

echo "📦 Copying binary into app bundle…"
cp .build/debug/RoXBot RoXBot.app/Contents/MacOS/RoXBot

echo "🔏 Signing…"
xattr -cr RoXBot.app
CERT_NAME="RoXBotSign"
if security find-certificate -c "$CERT_NAME" ~/Library/Keychains/login.keychain-db &>/dev/null; then
    codesign --force --deep --sign "$CERT_NAME" RoXBot.app
else
    codesign --force --deep --sign - RoXBot.app
    echo "⚠️  Ad-hoc sign used — run 'bash setup_signing.sh' once to fix TCC resets."
fi

echo "🚀 Launching RoXBot…"
open RoXBot.app

echo "✅ Done — RoXBot is running"
