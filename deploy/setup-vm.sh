#!/bin/bash
# Run this once on the GCP VM to install dependencies and register both services.
# Usage: bash setup-vm.sh

set -e

echo "==> Installing Python dependencies..."
pip3 install flask firebase-admin yfinance pandas numpy requests pytz gunicorn

echo "==> Creating scanner user (if not exists)..."
id -u scanner &>/dev/null || useradd -m -s /bin/bash scanner

echo "==> Copying files..."
cp scanner.py         /home/scanner/scanner.py
cp .env.staging       /home/scanner/.env.staging
cp .env.prod          /home/scanner/.env.prod
cp deploy/swingscanner-staging.service /etc/systemd/system/
cp deploy/swingscanner-prod.service    /etc/systemd/system/

echo ""
echo "==> MANUAL STEPS REQUIRED before starting services:"
echo "    1. Upload firebase_cred_staging.json → /home/scanner/firebase_cred_staging.json"
echo "    2. Upload firebase_cred_prod.json    → /home/scanner/firebase_cred_prod.json"
echo "    3. Fill in FILL_ME_IN values in /home/scanner/.env.staging and .env.prod"
echo "       (FIREBASE_URL, FIREBASE_API_KEY, ALPACA_SECRET, etc.)"
echo ""
echo "    Then run:"
echo "      sudo systemctl daemon-reload"
echo "      sudo systemctl enable --now swingscanner-staging"
echo "      sudo systemctl enable --now swingscanner-prod"
echo ""
echo "    Check logs:"
echo "      journalctl -u swingscanner-staging -f"
echo "      journalctl -u swingscanner-prod -f"
