#!/bin/bash
# Deja vigilar.py funcionando solo: macOS lo lanza al encender y cada 5 minutos.
# Uso:   ./instalar-vigilante.sh            (instalar o actualizar)
#        ./instalar-vigilante.sh quitar     (desinstalar)
set -e
cd "$(dirname "$0")"
ETIQUETA="com.transcriptor.vigilante"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"
LOG="$HOME/Library/Logs/transcriptor.log"

launchctl bootout "gui/$(id -u)/$ETIQUETA" 2>/dev/null || true
if [ "$1" = "quitar" ]; then
  rm -f "$PLIST"; echo "Vigilante desinstalado."; exit 0
fi

PY="$PWD/.venv/bin/python"
[ -x "$PY" ] || { echo "Falta el entorno .venv: sigue antes los pasos de instalación del README."; exit 1; }
FFMPEG_DIR="$(dirname "$(command -v ffmpeg || echo /opt/homebrew/bin/ffmpeg)")"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETIQUETA</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$PWD/vigilar.py</string></array>
  <key>WorkingDirectory</key><string>$PWD</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$FFMPEG_DIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Listo. Revisa las grabaciones cada 5 minutos. Registro: $LOG"
