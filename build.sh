#!/bin/zsh
# build.sh — builds RoXBot and copies the binary into RoXBot.app
set -e
cd "$(dirname "$0")"

swift build
cp .build/debug/RoXBot RoXBot.app/Contents/MacOS/RoXBot
xattr -cr RoXBot.app

# Use a stable named certificate if available — this keeps the code signature
# identity consistent across builds so macOS TCC (Accessibility/Screen Recording)
# never revokes the granted permissions.
# Run setup_signing.sh once to create the certificate.
CERT_NAME="RoXBotSign"
if security find-certificate -c "$CERT_NAME" ~/Library/Keychains/login.keychain-db &>/dev/null; then
    codesign --force --deep --sign "$CERT_NAME" RoXBot.app
    echo "✅ RoXBot.app signed with stable cert '$CERT_NAME'"
else
    codesign --force --deep --sign - RoXBot.app
    echo "⚠️  Signed with ad-hoc identity (TCC permissions may reset)."
    echo "   Run 'bash setup_signing.sh' once to fix this permanently."
fi
echo "✅ RoXBot.app ready"
