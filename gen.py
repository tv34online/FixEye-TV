import os, re, sys, random, requests
from urllib.parse import urljoin

PERSON = "40273629"
NAME = "FixEye ТВ"
MAX_HOURS = 4
PAGES = 10

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"

SKIP = ("#EXTM3U", "#EXT-X-ENDLIST", "#EXT-X-VERSION", "#EXT-X-MEDIA-SEQUENCE",
        "#EXT-X-PLAYLIST-TYPE", "#EXT-X-DISCONTINUITY-SEQUENCE",
        "#EXT-X-INDEPENDENT-SEGMENTS", "#EXT-X-TARGETDURATION")

def get(url):
    r = S.get(url, timeout=30)
    r.raise_for_status()
    return r

def list_videos():
    vids = []
    for p in range(1, PAGES + 1):
        try:
            d = get(f"https://rutube.ru/api/video/person/{PERSON}/?page={p}").json()
        except Exception:
            break
        vids += d.get("results", [])
        if not d.get("has_next"):
            break
    return vids

def master_url(vid):
    o = get(f"https://rutube.ru/api/play/options/{vid}/?no_404=true").json()
    return (o.get("video_balancer") or {}).get("m3u8")

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
body, total, count, target = [], 0.0, 0, 0

for v in vids:
    if total >= MAX_HOURS * 3600:
        break
    try:
        m = master_url(v["id"])
        if not m:
            continue
        segs = parse(pick_variant(m))
    except Exception as e:
        print("skip", v.get("id"), e)
        continue
    if not segs:
        continue
    if "#EXT-X-DISCONTINUITY" not in segs[0]["pre"]:
        segs[0]["pre"].insert(0, "#EXT-X-DISCONTINUITY")
    for s in segs:
        body += s["pre"] + [f"#EXTINF:{s['d']:.3f},", s["u"]]
        target = max(target, int(s["d"] + 0.999))
        total += s["d"]
    count += 1

if not count:
    sys.exit("нет ни одного видео, деплой отменён")

head = ["#EXTM3U", "#EXT-X-VERSION:7", f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-START:TIME-OFFSET=0,PRE