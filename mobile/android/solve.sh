#!/system/bin/sh
# wxsheep mobile runner  --  runs entirely on the phone (root required)
#
# deploy:  adb push wxsheep/ /data/local/tmp/
# run   :  su -c "sh /data/local/tmp/wxsheep/solve.sh"
#
# exit codes:
#   0 ok       1 no root    2 no game process    3 inject failed

BASE=/data/local/tmp/wxsheep
APP=/data/data/com.tencent.mm
FILES=$APP/files
PAYLOAD_DST=$FILES/wxsheep_payload.txt

log() { echo "[wxsheep] $*"; }

[ "$(id -u)" = "0" ] || { log "ERROR need root"; exit 1; }
[ -d "$BASE" ] || { log "ERROR missing $BASE"; exit 1; }

# ---- 1. ensure frida-server is up -------------------------------------------
if ! ss -tln 2>/dev/null | grep -q ':27042'; then
  log "starting frida-server"
  setsid "$BASE/fs" -l 127.0.0.1:27042 >/dev/null 2>&1 &
  sleep 2
fi

# ---- 2. stage payload where the app uid can read it -------------------------
# SELinux blocks the app from reading /data/local/tmp, so copy into app private dir
if [ -f "$BASE/payload.txt" ]; then
  UID_APP=$(stat -c %u "$APP" 2>/dev/null)
  cp -f "$BASE/payload.txt" "$PAYLOAD_DST"
  [ -n "$UID_APP" ] && chown "$UID_APP:$UID_APP" "$PAYLOAD_DST"
  chmod 644 "$PAYLOAD_DST"
fi

# ---- 3. locate the mini-game host process -----------------------------------
PID=$(ps -A 2>/dev/null | grep 'com.tencent.mm:appbrand' | awk '{print $2}' | head -1)
if [ -z "$PID" ]; then
  log "ERROR game not running (open the mini game first)"
  exit 2
fi
log "target pid=$PID"

# ---- 4. inject --------------------------------------------------------------
"$BASE/fi" -p "$PID" -s "$BASE/eval_payload.js" >/dev/null 2>&1 &
FI_PID=$!
sleep 9
kill "$FI_PID" 2>/dev/null

# ---- 5. never leave the game frozen in ptrace-stop --------------------------
if grep -q 't (tracing stop)' "/proc/$PID/status" 2>/dev/null; then
  log "WARN game was ptrace-stopped, sending CONT"
  kill -CONT "$PID" 2>/dev/null
fi

log "done. output: /storage/emulated/0/Android/data/com.tencent.mm/MicroMsg/wxanewfiles/*/"
exit 0
