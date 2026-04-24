#!/usr/bin/env bash
#
# One-time server setup for Amazon Linux 2023.
# Run as ec2-user from /home/ec2-user/vya:
#   bash deploy/setup.sh
#
# Idempotent — safe to re-run after pulls.
set -euo pipefail

REPO_DIR="/home/ec2-user/vya"
SVC_NAME="vya-kitchen"
DOMAIN="vya.co.nz"
WWW_DOMAIN="www.vya.co.nz"
ADMIN_EMAIL="ebin198351@gmail.com"   # for Let's Encrypt notifications

echo "===== 0. Sanity ====="
[ "$(whoami)" = "ec2-user" ] || { echo "Please run as ec2-user"; exit 1; }
[ -d "$REPO_DIR" ] || { echo "Expected repo at $REPO_DIR"; exit 1; }
cd "$REPO_DIR"

echo "===== 1. System packages ====="
sudo dnf install -y nginx python3-pip git certbot python3-certbot-nginx

echo "===== 2. Python deps (user-level) ====="
python3 -m pip install --user --quiet --upgrade pip
python3 -m pip install --user --quiet -r requirements.txt

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
# only seed if menu_items empty
COUNT=$(python3 -c "from db import get_conn; print(get_conn().execute('SELECT COUNT(*) FROM menu_items').fetchone()[0])")
if [ "$COUNT" = "0" ]; then
  python3 seed_menu.py
  echo "  → seeded $COUNT items"
else
  echo "  ✓ DB already has $COUNT menu items, skipping seed"
fi

echo "===== 5. systemd service ====="
sudo cp "$REPO_DIR/deploy/vya-kitchen.service" "/etc/systemd/system/$SVC_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SVC_NAME"
sudo systemctl restart "$SVC_NAME"
sleep 1
sudo systemctl is-active --quiet "$SVC_NAME" && echo "  ✓ $SVC_NAME running" || {
  echo "  ✗ $SVC_NAME failed to start"
  sudo journalctl -u "$SVC_NAME" --no-pager -n 30
  exit 1
}

echo "===== 6. nginx ====="
# Disable default config that ships with AL2023 nginx (catches all on 80)
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
  echo "ec2-user ALL=(root) NOPASSWD: /bin/systemctl restart $SVC_NAME, /bin/systemctl status $SVC_NAME, /usr/bin/systemctl restart $SVC_NAME, /usr/bin/systemctl status $SVC_NAME" \
    | sudo tee "$SUDOERS" >/dev/null
  sudo chmod 440 "$SUDOERS"
  echo "  ✓ ec2-user can now restart $SVC_NAME without password"
else
  echo "  ✓ sudoers already configured"
fi

echo
echo "================================================================"
echo " ✓ Local stack ready"
echo "   Service:  systemctl status $SVC_NAME"
echo "   Logs:     tail -f $REPO_DIR/server.log"
echo "   Health:   curl -s http://127.0.0.1:8000/health"
echo "================================================================"
echo
echo " Next manual step (one time): get HTTPS certificate"
echo "   sudo certbot --nginx -d $DOMAIN -d $WWW_DOMAIN \\"
echo "     --non-interactive --agree-tos -m $ADMIN_EMAIL --redirect"
echo
echo " Then verify:  https://$DOMAIN"
echo "================================================================"
