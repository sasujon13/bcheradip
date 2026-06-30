#!/usr/bin/env bash
# Diagnose cheradip-ailt MySQL / .env — run on server:
#   bash ailt_api/deploy/diagnose-ailt-db.sh

set -euo pipefail

ENV_FILE="${ENV_FILE:-/home/sasha/apps/cheradip/bcheradip/ailt_api/.env}"
DJANGO_ENV="${DJANGO_ENV:-/home/sasha/apps/cheradip/bcheradip/.env}"

echo "=== AILT API database diagnostic ==="
echo ""

echo "1) ailt_api/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "   FAIL  Missing $ENV_FILE"
  echo "   Fix: cd ~/apps/cheradip/bcheradip/ailt_api"
  echo "        cp .env.production.example .env && nano .env"
else
  if grep -q "^DATABASE_URL=" "$ENV_FILE" 2>/dev/null; then
    echo "   OK  DATABASE_URL is set (value hidden)"
  else
    echo "   FAIL  DATABASE_URL missing in $ENV_FILE"
    echo "   Add (use same MySQL user/password as Django .env):"
    echo '   DATABASE_URL=mysql+pymysql://cheradip_cheradip:YOUR_PASSWORD@127.0.0.1:3306/ailanguagetutor?charset=utf8mb4'
  fi
  grep -E "^(SMTP_|GUEST_AI|HOST|PORT)" "$ENV_FILE" 2>/dev/null | sed 's/PASSWORD=.*/PASSWORD=***/' || true
fi
echo ""

echo "2) Django .env (reference for DB user/password)"
if [[ -f "$DJANGO_ENV" ]]; then
  grep -E "^DATABASE_(NAME|USER|PASSWORD|HOST|PORT)=" "$DJANGO_ENV" 2>/dev/null | sed 's/PASSWORD=.*/PASSWORD=***/' || echo "   (no DATABASE_* vars)"
else
  echo "   (no $DJANGO_ENV)"
fi
echo ""

echo "3) MySQL database ailanguagetutor"
if command -v mysql >/dev/null 2>&1; then
  if mysql -e "SHOW DATABASES LIKE 'ailanguagetutor';" 2>/dev/null | grep -q ailanguagetutor; then
    echo "   OK  database ailanguagetutor exists"
  else
    echo "   FAIL  database ailanguagetutor not found"
    echo "   Create/sync: cd ~/apps/cheradip/bcheradip && source venv/bin/activate"
    echo "                python manage.py mysql_db_sync --l2r   # or create DB manually"
  fi
else
  echo "   (mysql client not in PATH)"
fi
echo ""

echo "4) cheradip-ailt service (last errors)"
journalctl -u cheradip-ailt -n 15 --no-pager 2>/dev/null || true
echo ""

echo "5) After fixing .env:"
echo "   sudo systemctl restart cheradip-ailt"
echo "   curl -s http://127.0.0.1:8790/api/ailt/health | head -c 200"
echo ""
