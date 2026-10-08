"""API gecikmesinin yüzdelikleri: ortalama, p50, p95, p99, en büyük (ms).

    cd api && uv run python ../docs/degerlendirme/gecikme.py http://127.0.0.1:8010 > ../docs/degerlendirme/gecikme.json

Her uç noktaya ısınmadan sonra ``N`` ardışık istek atılır (tek bağlantı, keep-alive). Ölçüm
geliştirme makinesinde, tek süreçli uvicorn ve aynı makinedeki PostgreSQL/Neo4j ile yapılır;
üretim performansını değil, uç noktalar arasındaki farkı ve dağılımın kuyruğunu gösterir.
"""

import json
import statistics
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
N, WARMUP = 300, 20
PATHS = {
    "Meydan ön sayfası (/news)": "/news",
    "Açık öneriler": "/proposals?state=open",
    "Konu sayfası": "/topics/5",
    "Dilekçe": "/petitions/1",
    "Takvim": "/calendar",
    "Arama (istanbul)": "/search?q=istanbul",
    "Karar Saati durumu": "/decision-hour",
}


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


out = {"n": N, "olcumler": {}}
with httpx.Client(base_url=BASE, timeout=30) as c:
    for label, path in PATHS.items():
        if c.get(path).status_code != 200:
            out["olcumler"][label] = {"hata": c.get(path).status_code}
            continue
        for _ in range(WARMUP):
            c.get(path)
        ms = []
        for _ in range(N):
            t0 = time.perf_counter()
            c.get(path)
            ms.append((time.perf_counter() - t0) * 1000)
        out["olcumler"][label] = {
            "yol": path, "ortalama": round(statistics.fmean(ms), 1),
            "p50": round(pct(ms, 0.5), 1), "p95": round(pct(ms, 0.95), 1),
            "p99": round(pct(ms, 0.99), 1), "en_buyuk": round(max(ms), 1),
        }
print(json.dumps(out, ensure_ascii=False, indent=1))
