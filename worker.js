const DISC = "#EXT-X-DISCONTINUITY";

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const cors = { "Access-Control-Allow-Origin": "*" };

    if (url.pathname === "/playlist.m3u") {
      return new Response(
        `#EXTM3U\n#EXTINF:-1 group-title="Эфир",FixEye ТВ\n${url.origin}/live.m3u8\n`,
        { headers: { ...cors, "Content-Type": "audio/x-mpegurl; charset=utf-8" } });
    }
    if (url.pathname !== "/live.m3u8") return new Response("not found", { status: 404 });

    const r = await fetch(env.SCHEDULE_URL, { cf: { cacheTtl: 60, cacheEverything: true } });
    if (!r.ok) return new Response("schedule error", { status: 502 });
    const s = await r.json();
    const segs = s.segs, n = segs.length;

    const total = segs.reduce((a, x) => a + x.d, 0);
    const isDisc = (x) => x.pre.includes(DISC);
    const D = segs.filter(isDisc).length;

    const elapsed = Math.max(0, Date.now() / 1000 - s.start);
    const cycles = Math.floor(elapsed / total);
    let pos = elapsed - cycles * total, i = 0;
    while (i < n - 1 && pos >= segs[i].d) { pos -= segs[i].d; i++; }

    let before = 0;
    for (let k = 0; k < i; k++) if (isDisc(segs[k])) before++;

    const WIN = 6;
    const target = Math.ceil(Math.max(...segs.map((x) => x.d)));
    const out = [
      "#EXTM3U",
      `#EXT-X-VERSION:${segs.some((x) => x.m) ? 7 : 3}`,
      `#EXT-X-TARGETDURATION:${target}`,
      `#EXT-X-MEDIA-SEQUENCE:${cycles * n + i}`,
      `#EXT-X-DISCONTINUITY-SEQUENCE:${cycles * D + before}`,
    ];
    let lastMap = null;
    for (let j = 0; j < WIN; j++) {
      const x = segs[(i + j) % n];
      const hasMap = x.pre.some((t) => t.startsWith("#EXT-X-MAP"));
      if (x.m && x.m !== lastMap && !hasMap) out.push(x.m);
      if (x.m) lastMap = x.m;
      out.push(...x.pre, `#EXTINF:${x.d.toFixed(3)},`, x.u);
    }

    return new Response(out.join("\n"), {
      headers: { ...cors, "Content-Type": "application/vnd.apple.mpegurl", "Cache-Control": "no-store" },
    });
  },
};