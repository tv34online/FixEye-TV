import os, re, random, sys, requests
from urllib.parse import urljoin

PERSON = "40273629"
NAME = "FixEye ТВ"
MAX_VIDEOS = 60
MAX_HOURS = 12
PAGES = 10

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"

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

def segments(url):
    out, target, dur = [], 0, 0.0
    skip = ("#EXTM3U", "#EXT-X-ENDLIST", "#EXT-X-VERSION", "#EXT-X-MEDIA-SEQUENCE",
            "#EXT-X-PLAYLIST-TYPE", "#EXT-X-DISCONTINUITY-SEQUENCE", "#EXT-X-INDEPENDENT")
    for l in get(url).text.splitlines():
        l = l.strip()
        if not l or l.startswith(skip):
            continue
        if l.startswith("#EXT-X-TARGETDURATION"):
            target = int(l.split(":")[1])
            continue
        if l.startswith("#EXTINF"):
            dur += float(l.split(":")[1].split(",")[0])
        if l.startswith("#"):
            l = re.sub(r'URI="([^"]+)"',
                       lambda m: f'URI="{urljoin(url, m.group(1))}"', l)
        else:
            l = urljoin(url, l)
        out.append(l)
    return out, target, dur

vids = list_videos()
random.shuffle(vids)
body, used, target, total = [], [], 0, 0.0

for v in vids:
    if len(used) >= MAX_VIDEOS or total >= MAX_HOURS * 3600:
        break
    try:
        m = master_url(v["id"])
        if not m:
            continue
        seg, t, d = segments(pick_variant(m))
    except Exception as e:
        print("skip", v.get("id"), e)
        continue
    if not seg:
        continue
    if body:
        body.append("#EXT-X-DISCONTINUITY")
    body += seg
    target = max(target, t)
    total += d
    used.append((v, m))

if not used:
    sys.exit("нет ни одного видео, деплой отменён")

os.makedirs("public", exist_ok=True)
head = ["#EXTM3U", "#EXT-X-VERSION:3", f"#EXT-X-TARGETDURATION:{target or 10}",
        "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD"]
open("public/channel.m3u8", "w", encoding="utf-8").write(
    "\n".join(head + body + ["#EXT-X-ENDLIST"]))

owner, repo = os.environ.get("GITHUB_REPOSITORY", "user/repo").split("/")
base = f"https://{owner}.github.io/{repo}"
pl = ["#EXTM3U", f'#EXTINF:-1 group-title="Эфир",{NAME}\n{base}/channel.m3u8']
for v, m in used:
    title = re.sub(r"[\r\n,]+", " ", v["title"])
    pl.append(f'#EXTINF:-1 group-title="Видео" tvg-logo="{v.get("thumbnail_url","")}",{title}\n{m}')
open("public/playlist.m3u", "w", encoding="utf-8").write("\n".join(pl))
print(f"готово: {len(used)} видео, {total/3600:.1f} ч")