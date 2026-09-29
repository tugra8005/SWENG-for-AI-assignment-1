#!/usr/bin/env bash
# Başlatıcıları uygulama menüsüne ekler (~/.local/share/applications): "Meşveret · sunum (web)",
# "Meşveret · sunum (Android)" ve "Meşveret · sunumu durdur". Her biri bir terminal penceresinde
# açılır; pencere, iş bitince kumanda ya da özetle açık kalır.
#   sunum/kur.sh            ekle
#   sunum/kur.sh --kaldir   kaldır
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$DIR")"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON="$ROOT/client/assets/images/icon.png"
NAMES=(mesveret-sunum-web mesveret-sunum-android mesveret-sunum-durdur)

if [[ ${1:-} == --kaldir ]]; then
  for n in "${NAMES[@]}"; do rm -f "$APPS/$n.desktop"; done
  echo "Başlatıcılar kaldırıldı."
  exit 0
fi

# Pencereyi açık tutabilen bir terminal: kitty, foot, konsole; yoksa masaüstünün seçtiği.
term_exec() {
  local script=$1
  if command -v kitty >/dev/null; then
    echo "kitty --title Meşveret --hold bash \"$script\""
  elif command -v foot >/dev/null; then
    echo "foot --title Meşveret --hold bash \"$script\""
  elif command -v konsole >/dev/null; then
    echo "konsole --hold -e bash \"$script\""
  else
    echo "bash \"$script\""
  fi
}
terminal_flag() { command -v kitty >/dev/null || command -v foot >/dev/null || command -v konsole >/dev/null && echo false || echo true; }

mkdir -p "$APPS"
yaz() {
  local name=$1 title=$2 comment=$3 script=$4
  cat >"$APPS/$name.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$title
Comment=$comment
Exec=$(term_exec "$script")
Icon=$ICON
Terminal=$(terminal_flag)
Categories=Development;
DESKTOP
  chmod +x "$APPS/$name.desktop"
  echo "  ✓ $title → $APPS/$name.desktop"
}

echo "Başlatıcılar ekleniyor:"
yaz mesveret-sunum-web "Meşveret · sunum (web)" \
  "Yığını, Expo'yu ve demoyu hazırlar; uygulamayı ayrı pencerede açar" "$DIR/web.sh"
yaz mesveret-sunum-android "Meşveret · sunum (Android)" \
  "Yığını, Expo'yu ve demoyu hazırlar; emülatörü açıp uygulamayı Expo Go'da başlatır" "$DIR/android.sh"
yaz mesveret-sunum-durdur "Meşveret · sunumu durdur" \
  "Emülatörü, Expo sunucusunu ve sunum penceresini kapatır" "$DIR/durdur.sh"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "Uygulama menüsünde \"Meşveret\" diye arayın. Kaldırmak için: sunum/kur.sh --kaldir"
