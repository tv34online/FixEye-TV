import os, re, sys, time, random, requests
from urllib.parse import urljoin

PERSON = "40273629"
NAME = "FixEye ТВ"
MAX_HOURS = 4
PAGES = 10

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
if os.environ.get("PROXY"):
    S.proxies = {"http": os.environ["PROXY"], "https": os.environ["PROXY"]}

SKIP = ("#EXTM3U", "#EXT-X-ENDLIST", "#EXT-X-VERSION", "#EXT-X-MEDIA-SEQUENCE",
        "#EXT-X-PLAYLIST-TYPE", "#EXT-X-DISCONTINUITY-SEQUENCE",
        "#EXT-X-INDEPENDENT-SEGMENTS", "#EXT-X-TARGETDURATION")

def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = repr(e)
        time.sleep(2)
    raise RuntimeError(f"{url} -> {last}")

def list_videos():
    vids = []
    for p in range(1, PAGES + 1):
        try:
            d = get(f"https://rutube.ru/api/video/person/{PERSON}/?page={p}").json()
        except Exception as e:
            print("СПИСОК ВИДЕО:", e)
            break
        vids += d.get("results", [])
        if not d.get("has_next"):
            break
    print("найдено видео:", len(vids))
    return vids

def master_url(vid):
    o = get(f"https://rutube.ru/api/play/options/{vid}/?no_404=true").json()
    b = o.get("video_balancer") or {}
    return b.get("m3u8") or b.get("default")

def pick_variant(url):
    lines = get(url).text.splitlines()
    best = None
    for i, l in enumerate(lines):
        if l.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"RESOLUTION=\d+x(\d+)", l)
            h = int(m.group(1)) if m else 0
            cand = (abs(h - 720), urljoin(url, lines[i + 1].strip()))
            if best is None or cand < best:
                best = cand
    return best[1] if best else url

def parse(url):
    segs, pre, d = [], [], None
    for l in get(url).text.splitlines():
        l = l.strip()
        if not l:
            continue
        if l.startswith("#EXTINF"):
            d = float(l.split(":")[1].split(",")[0])
            continue
        if l.startswith("#"):
            if l.startswith(SKIP):
                continue
            l = re.sub(r'URI="([^"]+)"',
                       lambda m: f'URI="{urljoin(url, m.group(1))}"', l)
            pre.append(l)
            continue
        if d is None:
            continue
        segs.append({"u": urljoin(url, l), "d": d, "pre": pre})
        pre, d = [], None
    return segs

vids = list_videos()
random.shuffle(vids)
body, total, count, target, errors = [], 0.0, 0, 0, 0

for v in vids:
    if total >= MAX_HOURS * 3600:
        break
    try:
        m = master_url(v["id"])
        if not m:
            raise RuntimeError("нет ссылки на поток")
        segs = parse(pick_variant(m))
        if not segs:
            raise RuntimeError("пустой плейлист")
    except Exception as e:
        errors += 1
        print("пропуск", v.get("id"), "-", e)
        if errors >= 5 and count == 0:
            break
        continue
    if "#EXT-X-DISCONTINUITY" not in segs[0]["pre"]:
        segs[0]["pre"].insert(0, "#EXT-X-DISCONTINUITY")
    for s in segs:
        body += s["pre"] + [f"#EXTINF:{s['d']:.3f},", s["u"]]
        target = max(target, int(s["d"] + 0.999))
        total += s["d"]
    count += 1

if not count:
    sys.exit("ОШИБКА: не получилось взять ни одного видео. Смотрите строки "
             "выше: если там HTTP 403/451 или таймаут, Rutube не пускает "
             "этот сервер (нужен российский раннер или PROXY).")

head = ["#EXTM3U", "#EXT-X-VERSION:7", f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-START:TIME-OFFSET=0,PRECISE=YES"]

os.makedirs("public", exist_ok=True)
open("public/channel.m3u8", "w", encoding="utf-8").write("\n".join(head + body))
open("public/index.html", "w", encoding="utf-8").write(
    "<!doctype html><meta charset=utf-8><title>FixEye ТВ</title><p>FixEye ТВ")

base = os.environ.get("BASE_URL", "").rstrip("/")
repo = os.environ.get("GITHUB_REPOSITORY", "")
if not base and repo and "github.com" in os.environ.get("GITHUB_SERVER_URL", ""):
    owner, name = repo.split("/")
    base = f"https://{owner}.github.io/{name}"
if base:
    open("public/playlist.m3u", "w", encoding="utf-8").write(
        f'#EXTM3U\n#EXTINF:-1 group-title="Эфир",{NAME}\n{base}/channel.m3u8\n')

print(f"готово: {count} видео, {total/3600:.1f} ч")