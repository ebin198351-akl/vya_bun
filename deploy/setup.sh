#!/usr/bin/env bash
#
# Path-agnostic one-time server setup for Amazon Linux 2023.
# Run from anywhere inside the repo:
#   bash deploy/setup.sh
#
# Auto-detects:
#   - repo dir (from script location)
#   - run-as user (whoami at invocation; you should NOT run this as root)
#
# Idempotent — safe to re-run after pulls.
set -euo pipefail

# ----- auto-detect -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_USER="$(whoami)"
SVC_NAME="vya-kitchen"
DOMAIN="vya.co.nz"
WWW_DOMAIN="www.vya.co.nz"
ADMIN_EMAIL="ebin198351@gmail.com"

echo "===== 0. Sanity ====="
if [ "$RUN_USER" = "root" ]; then
  echo "✗ Do not run as root. Login as ec2-user (or your own non-root user) and re-run."
  exit 1
fi
[ -f "$REPO_DIR/server.py" ] || {
  echo "✗ Doesn't look like the repo (no server.py at $REPO_DIR)"; exit 1;
}
echo "  user:     $RUN_USER"
echo "  repo:     $REPO_DIR"
echo "  service:  $SVC_NAME"

echo "===== 1. System packages ====="
sudo dnf install -y nginx python3-pip git certbot python3-certbot-nginx >/dev/null
echo "  ✓ nginx, python3-pip, git, certbot installed"

echo "===== 2. Python deps (user-level) ====="
cd "$REPO_DIR"
python3 -m pip install --user --quiet --upgrade pip
python3 -m pip install --user --quiet -r requirements.txt
echo "  ✓ requirements.txt installed for $RUN_USER"

echo "===== 3. .env scaffold ====="
if [ ! -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  chmod 600 "$REPO_DIR/.env"
  echo "  → .env created from .env.example"
  echo "  ⚠  EDIT IT NOW with real keys: nano $REPO_DIR/.env"
  echo "     (then re-run: sudo systemctl restart $SVC_NAME)"
else
  echo "  ✓ .env already exists, leaving alone"
fi

echo "===== 4. Initialise SQLite + seed menu ====="
mkdir -p "$REPO_DIR/data"
python3 db.py
COUNT=$(python3 -c "from db import get_conn; print(get_conn().execute('SELECT COUNT(*) FROM menu_items').fetchone()[0])")
if [ "$COUNT" = "0" ]; then
  python3 seed_menu.py
  echo "  → seeded menu items"
else
  echo "  ✓ DB already has $COUNT menu items, skipping seed"
fi

echo "===== 5. systemd service (generated for this path/user) ====="
SVC_FILE="/etc/systemd/system/$SVC_NAME.service"
sudo tee "$SVC_FILE" > /dev/null <<EOF
[Unit]
Description=Vya's Kitchen Flask app
After=network.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
ExecStart=/usr/bin/python3 $REPO_DIR/server.py
Restart=on-failure
RestartSec=3
StandardOutput=append:$REPO_DIR/server.log
StandardError=append:$REPO_DIR/server.log
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable "$SVC_NAME"
sudo systemctl restart "$SVC_NAME"
sleep 1
if sudo systemctl is-active --quiet "$SVC_NAME"; then
  echo "  ✓ $SVC_NAME running (User=$RUN_USER, WorkingDir=$REPO_DIR)"
else
  echo "  ✗ $SVC_NAME failed to start"
  sudo journalctl -u "$SVC_NAME" --no-pager -n 30
  exit 1
fi

echo "===== 6. nginx ====="
if [ -f /etc/nginx/conf.d/default.conf ]; then
  sudo mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.disabled
fi
sudo cp "$REPO_DIR/deploy/nginx.conf" /etc/nginx/conf.d/vya.conf
sudo mkdir -p /var/www/certbot
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
echo "  ✓ nginx reloaded; HTTP listening on 80"

echo "===== 7. Sudoers for GH Actions deploy ====="
SUDOERS="/etc/sudoers.d/vya-deploy"
if ! sudo test -f "$SUDOERS"; then
  echo "$RUN_USER ALL=(root) NOPASSWD: /bin/systemctl restart $SVC_NAME, /bin/systemctl status $SVC_NAME, /usr/bin/systemctl restart $SVC_NAME, /usr/bin/systemctl status $SVC_NAME" \
    | sudo tee "$SUDOERS" >/dev/null
  sudo chmod 440 "$SUDOERS"
  echo "  ✓ $RUN_USER can restart $SVC_NAME without password"
else
  echo "  ✓ sudoers already configured"
fi

# Drop a deploy info file so GH Actions / future scripts know where this lives
INFO_FILE="$REPO_DIR/.deploy_info"
{
  echo "REPO_DIR=$REPO_DIR"
  echo "RUN_USER=$RUN_USER"
  echo "SVC_NAME=$SVC_NAME"
} > "$INFO_FILE"

echo
echo "================================================================"
echo " ✓ Local stack ready"
echo
echo "   Repo:     $REPO_DIR"
echo "   User:     $RUN_USER"
echo "   Service:  systemctl status $SVC_NAME"
echo "   Logs:     tail -f $REPO_DIR/server.log"
echo "   Health:   curl -s http://127.0.0.1:8000/health"
echo "================================================================"
echo
echo " Next: get HTTPS certificate (one-time)"
echo "   sudo certbot --nginx -d $DOMAIN -d $WWW_DOMAIN \\"
echo "     --non-interactive --agree-tos -m $ADMIN_EMAIL --redirect"
echo
echo " ⚠ For GitHub Actions auto-deploy, your workflow YAML's 'cd' line"
echo "   must use:  cd $REPO_DIR"
echo "================================================================"
