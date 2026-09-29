#!/usr/bin/env bash
# Sunumdan sonra: emülatörü, Expo sunucusunu ve sunum tarayıcı penceresini kapatır.
#   sunum/durdur.sh [--demo-bitir] [--docker]
#   --demo-bitir  saati yeniden akıt (demo modundan çık)
#   --docker      Docker yığınını da durdur
set -u
source "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"

for a in "$@"; do
  case "$a" in
    --demo-bitir) DEMO_BITIR=1 ;;
    --docker) DOCKER=1 ;;
    *) hata "bilinmeyen seçenek: $a (--demo-bitir, --docker)" ;;
  esac
done

adim "Emülatör"
if [[ -x $ADB ]] && "$ADB" devices | grep -q '^emulator-.*device$'; then
  "$ADB" emu kill >/dev/null 2>&1 && tamam "kapatıldı" || uyari "kapatılamadı"
else
  tamam "açık değil"
fi

adim "Expo sunucusu"
if [[ -f $CACHE/expo.pid ]] && kill -0 "$(cat "$CACHE/expo.pid")" 2>/dev/null; then
  kill -- "-$(cat "$CACHE/expo.pid")" 2>/dev/null || kill "$(cat "$CACHE/expo.pid")"
  rm -f "$CACHE/expo.pid"
  tamam "kapatıldı"
else
  pid=$(ss -ltnpH 'sport = :8081' 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
  if [[ -n $pid ]]; then
    kill "$pid" && tamam "8081'deki sunucu kapatıldı (pid $pid)"
  else
    tamam "çalışmıyor"
  fi
fi

adim "Sunum tarayıcı penceresi"
if pkill -f -- "--user-data-dir=$CACHE/tarayici"; then tamam "kapatıldı"; else tamam "açık değil"; fi

if [[ ${DEMO_BITIR:-0} == 1 ]]; then
  adim "Demo modu"
  dev demo bitir | sed 's/^/  ✓ /'
fi
if [[ ${DOCKER:-0} == 1 ]]; then
  adim "Docker yığını"
  (cd "$ROOT" && docker compose stop >/dev/null 2>&1) && tamam "durduruldu"
fi
