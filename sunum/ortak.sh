# Sunum başlatıcılarının ortak adımları (web.sh ve android.sh içe aktarır).
# Her adım işi zaten yapılmışsa dokunmaz: yığın ayaktaysa, Expo çalışıyorsa, demo kuruluysa geçer.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/mesveret-sunum"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
ADB="$SDK/platform-tools/adb"
API=http://localhost:8000
WEB=http://localhost:8081
mkdir -p "$CACHE"

adim() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
tamam() { printf '  ✓ %s\n' "$*"; }
uyari() { printf '\033[33m  ! %s\033[0m\n' "$*"; }
hata() { printf '\033[31m  ✗ %s\033[0m\n' "$*" >&2; exit 1; }

# bekle <saniye> <ne> <komut...>: komut başarılı olana kadar dener.
bekle() {
  local limit=$1 ne=$2 t=0
  shift 2
  until "$@" >/dev/null 2>&1; do
    t=$((t + 2))
    ((t >= limit)) && hata "$ne $limit sn içinde hazır olmadı."
    sleep 2
  done
}

# Girdi /dev/null: docker exec kumandaya basılan tuşları yutmasın.
dev() { (cd "$ROOT" && docker compose exec -T api meşveret-dev "$@" </dev/null); }

yigin() {
  adim "Docker yığını (PostgreSQL, Neo4j, defter, API)"
  docker info >/dev/null 2>&1 || hata "Docker çalışmıyor. Başlatın: sudo systemctl start docker"
  # --build: kod değiştiyse imaj yeniden derlenir; değişmediyse önbellekten birkaç saniyede geçer.
  # Olmazsa istemci yeni, API eski kalır ve yeni sayfalar "Not Found" alır.
  (cd "$ROOT" && docker compose up -d --build --wait >"$CACHE/docker.log" 2>&1) \
    || hata "docker compose up başarısız; ayrıntı: $CACHE/docker.log"
  bekle 120 "API" curl -sf "$API/health"
  tamam "API hazır: $API"
}

expo() {
  adim "Expo geliştirme sunucusu"
  if curl -sf -o /dev/null "$WEB"; then
    tamam "zaten çalışıyor: $WEB"
    return
  fi
  # BROWSER=none: Expo kendi tarayıcı sekmesini açmasın, pencereyi başlatıcı açar.
  (cd "$ROOT/client" && BROWSER=none EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 \
    setsid nohup npx expo start --web --port 8081 >"$CACHE/expo.log" 2>&1 </dev/null &
    echo $! >"$CACHE/expo.pid")
  bekle 180 "Expo" curl -sf -o /dev/null "$WEB"
  tamam "başladı: $WEB (günlük: $CACHE/expo.log)"
}

# isit web|android: ilk paket derlemesi (20–60 sn) sunumda değil şimdi olsun.
isit() {
  local url
  if [[ $1 == web ]]; then
    url=$(curl -s "$WEB/" | grep -o 'src="/[^"]*entry\.bundle[^"]*"' | head -1 | cut -d'"' -f2 || true)
    [[ -n $url ]] && url="$WEB$url"
  else
    url=$(curl -s -H 'expo-platform: android' -H 'accept: application/expo+json,application/json' \
      "$WEB" | python3 -c 'import json,sys; print(json.load(sys.stdin)["launchAsset"]["url"])' \
      2>/dev/null || true)
  fi
  if [[ -z $url ]]; then
    uyari "$1 paketinin adresi bulunamadı; ilk açılış yavaş olabilir"
    return
  fi
  printf '  … %s paketi derleniyor (ilk seferde 20–60 sn)\n' "$1"
  if curl -sf -o /dev/null -m 300 "$url"; then
    tamam "$1 paketi hazır"
  else
    uyari "$1 paketi önceden derlenemedi; ilk açılış yavaş olabilir"
  fi
}

demo() {
  adim "Demo"
  local durum
  durum=$(dev demo durum 2>&1 || true)
  durum=${durum%%$'\n'*}
  if [[ ${SIFIRLA:-0} == 1 || $durum == "Demo başlamadı"* ]]; then
    printf '  … 1. adım kuruluyor (~20 sn: tohum, Karar Saati #1, saat donuyor)\n'
    durum=$(dev demo goto 1) || hata "demo kurulamadı"
    tamam "${durum%%$'\n'*}"
  else
    tamam "$durum (baştan kurmak için --sifirla)"
  fi
}

# Kumanda: sunum sırasında uzun komut yazılmasın.
kumanda() {
  adim "Kumanda"
  cat <<'YARDIM'
  Enter   sonraki adım        p   önceki adım        g N   N. adıma git (1–9, 10a, 10b)
  d       şu anki adım        s   baştan kur (goto 1)   q   çık (yığın ve pencereler açık kalır)
YARDIM
  local komut arg
  while true; do
    printf '\n\033[1mdemo>\033[0m '
    read -r komut arg || break
    case "$komut" in
      "" | n) dev demo next ;;
      p) dev demo prev ;;
      g) [[ -n $arg ]] && dev demo goto "$arg" || echo "  kullanım: g 5" ;;
      d) dev demo durum ;;
      s) dev demo goto 1 ;;
      q) break ;;
      *) echo "  bilinmeyen komut: $komut" ;;
    esac
  done
}

argumanlar() {
  for a in "$@"; do
    case "$a" in
      --sifirla) SIFIRLA=1 ;;
      --kumandasiz) KUMANDASIZ=1 ;;
      -h | --help)
        echo "kullanım: $0 [--sifirla] [--kumandasiz]"
        echo "  --sifirla     demo kuruluysa bile 1. adımı baştan kur"
        echo "  --kumandasiz  hazırlıktan sonra kumandayı açma"
        exit 0 ;;
      *) hata "bilinmeyen seçenek: $a" ;;
    esac
  done
}
