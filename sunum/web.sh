#!/usr/bin/env bash
# Sunum: web. Yığını, Expo'yu ve demonun 1. adımını hazırlar, uygulamayı ayrı bir tarayıcı
# penceresinde açar, sonra kumandayı başlatır (Enter = sonraki adım).
#   sunum/web.sh [--sifirla] [--kumandasiz]
set -eu
source "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"
argumanlar "$@"

printf '\033[1mMeşveret · sunum (web)\033[0m\n'
yigin
expo
isit web
demo

adim "Tarayıcı penceresi"
# Ayrı profil: sekme çubuğu, eklenti ve yer imi yok; giriş ve menü tercihi bu pencerede kalır.
profil="$CACHE/tarayici"
if command -v brave >/dev/null; then
  setsid nohup brave --user-data-dir="$profil" --no-first-run --no-default-browser-check \
    --app="$WEB" >"$CACHE/tarayici.log" 2>&1 </dev/null &
  tamam "Brave uygulama penceresi: $WEB"
elif command -v firefox >/dev/null; then
  setsid nohup firefox --new-window "$WEB" >"$CACHE/tarayici.log" 2>&1 </dev/null &
  tamam "Firefox: $WEB"
else
  xdg-open "$WEB" >/dev/null 2>&1 &
  tamam "varsayılan tarayıcı: $WEB"
fi
echo "  Sağ alttaki menü adımın sayfalarını o kullanıcıyla açar. Adımlar ve konuşma notları: DEMO.md"

[[ ${KUMANDASIZ:-0} == 1 ]] || kumanda
