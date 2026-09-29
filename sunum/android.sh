#!/usr/bin/env bash
# Sunum: Android. Yığını, Expo'yu ve demonun 1. adımını hazırlar, emülatörü pencereli açar,
# uygulamayı Expo Go'da başlatır, sonra kumandayı başlatır (Enter = sonraki adım).
#   sunum/android.sh [--sifirla] [--kumandasiz]
set -eu
source "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"
argumanlar "$@"
AVD="${AVD:-mesveret}"

printf '\033[1mMeşveret · sunum (Android)\033[0m\n'
[[ -x $ADB ]] || hata "Android SDK bulunamadı: $SDK (ANDROID_HOME ile değiştirilebilir)"
yigin
expo
demo

adim "Android emülatörü ($AVD)"
if "$ADB" devices | grep -q '^emulator-.*device$'; then
  tamam "zaten açık"
else
  # Wayland'de emülatörün Qt arayüzü XWayland üzerinden açılır.
  [[ -n ${DISPLAY:-} ]] && export QT_QPA_PLATFORM=xcb
  setsid nohup "$SDK/emulator/emulator" -avd "$AVD" -gpu auto -no-audio -no-boot-anim \
    >"$CACHE/emulator.log" 2>&1 </dev/null &
  printf '  … açılıyor (~20 sn)\n'
  timeout 90 "$ADB" wait-for-device || hata "emülatör başlamadı; ayrıntı: $CACHE/emulator.log"
  bekle 240 "Android" bash -c "[[ \$('$ADB' shell getprop sys.boot_completed 2>/dev/null | tr -d '\r') == 1 ]]"
  tamam "açıldı (günlük: $CACHE/emulator.log)"
fi
# Emülatörün 127.0.0.1'i bilgisayarın 8081 (Expo) ve 8000 (API) portlarına gider.
"$ADB" reverse tcp:8081 tcp:8081 >/dev/null
"$ADB" reverse tcp:8000 tcp:8000 >/dev/null
tamam "portlar yönlendirildi (8081, 8000)"
"$ADB" shell pm list packages 2>/dev/null | grep -q host.exp.exponent \
  || hata "Expo Go yüklü değil. Yükleyin: $ADB install Expo-Go-57.0.9.apk (github.com/expo/expo-go-releases)"

isit android
adim "Uygulama"
"$ADB" shell am start -a android.intent.action.VIEW -d exp://127.0.0.1:8081 >/dev/null
tamam "Expo Go'da açıldı; sağ alttaki menü adımın sayfalarını o kullanıcıyla açar"

[[ ${KUMANDASIZ:-0} == 1 ]] || kumanda
