#!/bin/bash
# Run once on the GCP VM to install the swing scanner as a systemd service.
# Usage:  sudo bash deploy/setup-vm.sh
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR=/home/scanner

# These VMs run the service as root and use /home/scanner only as a working
# directory — there is no dedicated 'scanner' user.

echo "==> Creating Python venv at $HOME_DIR/venv (if missing) ..."
apt-get update -qq && apt-get install -y python3-venv python3-pip
[ -x "$HOME_DIR/venv/bin/python3" ] || python3 -m venv "$HOME_DIR/venv"
"$HOME_DIR/venv/bin/pip" install --upgrade pip
"$HOME_DIR/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

echo "==> Installing scanner.py ..."
cp "$REPO_DIR/scanner.py" "$HOME_DIR/scanner.py"

echo "==> Installing systemd service ..."
cp "$REPO_DIR/deploy/swingscanner.service" /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "==> MANUAL STEPS before starting the service:"
echo "    1. Upload the Firebase admin key:"
echo "         scp firebase_cred.json  VM:$HOME_DIR/firebase_cred.json"
echo "    2. Create $HOME_DIR/.env from .env.example and fill in:"
echo "         FIREBASE_CRED=$HOME_DIR/firebase_cred.json"
echo "         FIREBASE_URL=https://<project>-default-rtdb.firebaseio.com"
echo "         ALPACA_KEY / ALPACA_SECRET"
echo "       chown scanner:scanner $HOME_DIR/.env"
echo ""
echo "    Then start it:"
echo "         sudo systemctl enable --now swingscanner"
echo "         journalctl -u swingscanner -f"
