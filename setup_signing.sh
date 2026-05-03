#!/bin/zsh
# setup_signing.sh — creates a stable local signing certificate for RoXBot.
# Run this ONCE on any machine. The cert lives in your login keychain and
# persists across all future builds so macOS TCC (Accessibility/Screen Recording)
# never revokes permissions.
set -e

CERT_NAME="RoXBotSign"

# Check if already exists
if security find-certificate -c "$CERT_NAME" ~/Library/Keychains/login.keychain-db &>/dev/null; then
    echo "✅ Certificate '$CERT_NAME' already exists — nothing to do."
    echo "   build.sh will use it automatically."
    exit 0
fi

echo "🔑 Creating self-signed code-signing certificate: $CERT_NAME"

# Generate cert via certtool (pure shell, no GUI)
TMPDIR=$(mktemp -d)
cat > "$TMPDIR/cert.cfg" <<EOF
[ req ]
default_bits       = 2048
prompt             = no
distinguished_name = dn
x509_extensions    = v3_codesign
[ dn ]
CN = $CERT_NAME
[ v3_codesign ]
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints       = critical, CA:false
keyUsage               = critical, digitalSignature
extendedKeyUsage       = critical, codeSigning
EOF

# Use openssl to create key + self-signed cert
openssl req -x509 -newkey rsa:2048 -keyout "$TMPDIR/key.pem" \
    -out "$TMPDIR/cert.pem" -days 3650 -nodes -config "$TMPDIR/cert.cfg" 2>/dev/null

# Bundle into PKCS#12
openssl pkcs12 -export -out "$TMPDIR/roxbot.p12" \
    -inkey "$TMPDIR/key.pem" -in "$TMPDIR/cert.pem" \
    -passout pass:roxbot 2>/dev/null

# Import into login keychain
security import "$TMPDIR/roxbot.p12" \
    -k ~/Library/Keychains/login.keychain-db \
    -P roxbot \
    -T /usr/bin/codesign \
    -f pkcs12

# Trust for code signing
security add-trusted-cert -d -r trustRoot \
    -k ~/Library/Keychains/login.keychain-db \
    "$TMPDIR/cert.pem"

rm -rf "$TMPDIR"

echo "✅ Certificate '$CERT_NAME' created and trusted."
echo "   Run 'bash build.sh' — it will now use this cert for all future builds."
echo ""
echo "⚠️  After the first build with this cert, you'll need to re-grant"
echo "   Accessibility permission once more in System Settings (last time ever)."
