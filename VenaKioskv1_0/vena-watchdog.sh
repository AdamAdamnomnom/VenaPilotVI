#!/bin/sh
# VENA Kiosk — watchdog UI
# Trzyma VenaKioskv1_2.py przy życiu. Celowe wyjście do CLI (tryb serwisowy)
# tworzy data/no_autorestart — wtedy pętla się kończy. Po reboocie flaga
# jest kasowana i VENA znów startuje.

APP_DIR=/home/kiosk/vena
APP="$APP_DIR/VenaKioskv1_2.py"
STOP="$APP_DIR/data/no_autorestart"
LOG="$APP_DIR/logs/vena_stdout.log"
LOCK=/tmp/vena-watchdog.lock

# Jedna instancja watchdoga na sesję X
if [ -f "$LOCK" ]; then
  old=$(cat "$LOCK" 2>/dev/null || true)
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    exit 0
  fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT INT TERM

cd "$APP_DIR" || exit 1
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

# Po restarcie sesji / reboot — zawsze startuj (nie trzymaj starej flagi)
rm -f "$STOP"

while true; do
  if [ -f "$STOP" ]; then
    rm -f "$STOP"
    echo "$(date '+%F %T') [watchdog] stop (no_autorestart) — wyjście do CLI" >> "$LOG"
    break
  fi

  # Unikaj drugiego procesu, jeśli VENA już żyje
  if pgrep -f "/home/kiosk/vena/VenaKioskv1_2.py|./VenaKioskv1_2.py" >/dev/null 2>&1; then
    sleep 3
    continue
  fi

  python3 "$APP" >> "$LOG" 2>&1
  code=$?

  if [ -f "$STOP" ]; then
    rm -f "$STOP"
    echo "$(date '+%F %T') [watchdog] stop po wyjściu serwisowym (code=$code)" >> "$LOG"
    break
  fi

  echo "$(date '+%F %T') [watchdog] VENA exit=$code — restart za 2s" >> "$LOG"
  sleep 2
done
