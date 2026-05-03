#!/bin/zsh
# build.sh — builds RoXBot and copies the binary into RoXBot.app
set -e
cd "$(dirname "$0")"

swift build
cp .build/debug/RoXBot RoXBot.app/Contents/MacOS/RoXBot
xattr -cr RoXBot.app
codesign --force --deep --sign - RoXBot.app
echo "✅ RoXBot.app signed and ready"
