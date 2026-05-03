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
codesign --force --deep --sign - RoXBot.app

echo "🚀 Launching RoXBot…"
open RoXBot.app

echo "✅ Done — RoXBot is running"
