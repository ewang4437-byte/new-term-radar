"""Vietnam social hot-topic monitor: what Vietnamese people are searching, reading and watching today.

    python scripts/vn_social.py                 # today's snapshot + report
    python scripts/vn_social.py --date 2026-10-25 --days 7

Sources (all free, standard library only):
  - Google Trends "Trending now" RSS for Vietnam (rising searches, with the news behind them)
  - Báo Mới (VNG, the Zalo group's news app): hot stories and the topic clusters (#...) they belong to
  - YouTube Data API mostPopular, regionCode=VN, per category (needs YOUTUBE_API_KEY in .env; skipped without it)
TikTok Creative Center and the Facebook Ad Library have no free machine-readable feed for Vietnam,
so the report only links them for a weekly manual look.

Writes state-vn/social/<date>.json (raw snapshot, used for "days in a row") and report-vn-social-<date>.md.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state-vn" / "social"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
HT = "{https://trends.google.com/trending/rss}"
YT = "https://www.googleapis.com/youtube/v3/"
LONG_MIN = 30  # a video at least this long counts as "long-form" (stories, audiobooks...)


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def fetch(url: str, tries: int = 2) -> str:
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - network errors of any kind: retry once
            err = e
            time.sleep(2 * (i + 1))
    raise err


# --- Google Trends ------------------------------------------------------------------

def parse_trends(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for it in root.iter("item"):
        news = [{"title": html.unescape(n.findtext(f"{HT}news_item_title") or ""),
                 "source": n.findtext(f"{HT}news_item_source") or "",
                 "url": n.findtext(f"{HT}news_item_url") or ""} for n in it.findall(f"{HT}news_item")]
        traffic = it.findtext(f"{HT}approx_traffic") or ""
        out.append({"term": (it.findtext("title") or "").strip(), "traffic": traffic,
                    "traffic_n": int(re.sub(r"\D", "", traffic) or 0),
                    "pub": it.findtext("pubDate") or "", "news": news})
    return out


def google_trends() -> list[dict]:
    return parse_trends(fetch("https://trends.google.com/trending/rss?geo=VN"))


# --- Báo Mới ------------------------------------------------------------------------

def _walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)


def parse_baomoi(page: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        raise ValueError("Báo Mới: __NEXT_DATA__ not found (page layout changed?)")
    data = json.loads(m.group(1))
    seen, stories, clusters = set(), [], {}
    for d in _walk(data):
        if "contentId" in d and "title" in d and "url" in d:
            if d["contentId"] in seen:
                continue
            seen.add(d["contentId"])
            c = d.get("cluster") or {}
            hot = "hotnews" in d.get("url", "")
            stories.append({"title": d["title"], "url": "https://baomoi.com" + d["url"].split("#")[0],
                            "publisher": (d.get("publisher") or {}).get("name", ""), "hot": hot,
                            "cluster": c.get("name", "")})
            if c.get("name"):
                k = c["name"]
                e = clusters.setdefault(k, {"name": k, "url": "https://baomoi.com" + c.get("url", ""),
                                            "total": 0, "on_home": 0})
                e["on_home"] += 1
                e["total"] = max(e["total"], int(c.get("total") or 0))
        # boxes like "#Góc công nghệ" are editorial sections, not news clusters: ignored
    return {"stories": stories, "clusters": sorted(clusters.values(), key=lambda e: (-e["on_home"], -e["total"]))}


def baomoi() -> dict:
    return parse_baomoi(fetch("https://baomoi.com/"))


# --- YouTube ------------------------------------------------------------------------

def iso_minutes(d: str) -> float:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0.0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 1440 + h * 60 + mi + s / 60


def _yt(path: str, key: str, **params) -> dict:
    params["key"] = key
    return json.loads(fetch(YT + path + "?" + urllib.parse.urlencode(params)))


def youtube(key: str) -> dict:
    cats = {c["id"]: c["snippet"]["title"] for c in
            _yt("videoCategories", key, part="snippet", regionCode="VN", hl="vi").get("items", [])
            if c["snippet"].get("assignable")}
    videos, failed = {}, []
    for cid in [""] + list(cats):
        p = dict(part="snippet,statistics,contentDetails", chart="mostPopular", regionCode="VN",
                 maxResults=50, hl="vi")
        if cid:
            p["videoCategoryId"] = cid
        try:
            items = _yt("videos", key, **p).get("items", [])
        except Exception:  # noqa: BLE001 - some categories have no chart in VN (HTTP 404)
            failed.append(cid)
            continue
        for v in items:
            sn, st = v["snippet"], v.get("statistics", {})
            e = videos.setdefault(v["id"], {
                "id": v["id"], "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
                "category": cats.get(sn.get("categoryId", ""), sn.get("categoryId", "")),
                "published": sn.get("publishedAt", "")[:10], "views": int(st.get("viewCount", 0) or 0),
                "minutes": round(iso_minutes(v.get("contentDetails", {}).get("duration", "")), 1),
                "tags": [t.lower() for t in sn.get("tags", [])][:30], "charts": []})
            e["charts"].append(cats.get(cid, "Tổng") if cid else "Tổng")
    return {"videos": sorted(videos.values(), key=lambda v: -v["views"]), "categories": cats, "failed": failed}


def yt_keywords(videos: list[dict]) -> Counter:
    """Tags and #hashtags, counted once per channel so one uploader can't flood the list."""
    per_channel: dict[str, set] = {}
    for v in videos:
        words = set(v["tags"]) | {h.lower() for h in re.findall(r"#(\w+)", v["title"])}
        per_channel.setdefault(v["channel"], set()).update(w.strip() for w in words if len(w.strip()) > 1)
    c = Counter()
    for words in per_channel.values():
        c.update(words)
    return c


# --- history & report ---------------------------------------------------------------

def streaks(today: str, days: int) -> dict[str, dict[str, int]]:
    """For each source, how many of the previous `days` days each term was also present."""
    d0 = date.fromisoformat(today)
    out = {"trends": Counter(), "baomoi": Counter(), "yt": Counter()}
    for i in range(1, days):
        f = STATE / f"{(d0 - timedelta(days=i)).isoformat()}.json"
        if not f.exists():
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        out["trends"].update({t["term"].lower() for t in s.get("trends") or []})
        out["baomoi"].update({c["name"] for c in (s.get("baomoi") or {}).get("clusters", [])})
        out["yt"].update(set(yt_keywords((s.get("youtube") or {}).get("videos", []))))
    return out


def mark(n_before: int) -> str:
    return "🆕" if n_before == 0 else f"{n_before + 1}天"


def md(x: str) -> str:
    return str(x).replace("|", "/").replace("\n", " ").strip()


def report(d: str, snap: dict, hist: dict, days: int) -> str:
    L = [f"# 越南社交热点 {d}", "",
         f"> 每天一次快照。「连续」= 最近 {days} 天里出现的天数，🆕 = 今天第一次出现。"
         "持续 3 天以上的词比一天爆的新闻更值得看。", ""]
    errs = snap.get("errors") or {}

    L += ["## 1. Google 搜索上升词（越南）", ""]
    if snap.get("trends"):
        L += ["| 词 | 搜索量 | 连续 | 相关新闻 |", "|---|---|---|---|"]
        for t in sorted(snap["trends"], key=lambda t: -t["traffic_n"]):
            news = f"[{md(t['news'][0]['title'])[:70]}]({t['news'][0]['url']}) · {md(t['news'][0]['source'])}" if t["news"] else ""
            L.append(f"| {md(t['term'])} | {t['traffic']} | {mark(hist['trends'][t['term'].lower()])} | {news} |")
    else:
        L.append(f"> 没取到：{errs.get('trends', '无数据')}")
    L.append("")

    L += ["## 2. Báo Mới 热点话题（VNG / Zalo 生态的新闻入口）", ""]
    bm = snap.get("baomoi")
    if bm:
        L += ["| 话题 | 首页文章数 | 话题累计文章 | 连续 |", "|---|---|---|---|"]
        for c in bm["clusters"][:25]:
            L.append(f"| [{md(c['name'])}]({c['url']}) | {c['on_home']} | {c['total']} | {mark(hist['baomoi'][c['name']])} |")
        hot = [s for s in bm["stories"] if s["hot"]][:8]
        if hot:
            L += ["", "**头条：**", ""] + [f"- [{md(s['title'])}]({s['url']}) · {md(s['publisher'])}" for s in hot]
    else:
        L.append(f"> 没取到：{errs.get('baomoi', '无数据')}")
    L.append("")

    L += ["## 3. YouTube 越南热门", ""]
    yt = snap.get("youtube")
    if yt and yt["videos"]:
        vids = yt["videos"]
        kw = yt_keywords(vids)
        longf = [v for v in vids if v["minutes"] >= LONG_MIN]
        by_cat = Counter(v["category"] for v in vids)
        L += [f"共 {len(vids)} 个上榜视频（{len(yt['categories'])} 个分类榜去重）；"
              f"长视频（≥{LONG_MIN} 分钟）{len(longf)} 个。分类分布：" +
              "、".join(f"{k} {n}" for k, n in by_cat.most_common(8)), ""]
        L += ["### 高频标签（按频道去重计数）", "", "| 标签 | 频道数 | 连续 |", "|---|---|---|"]
        for w, n in kw.most_common(40):
            if n < 2:
                break
            L.append(f"| {md(w)} | {n} | {mark(hist['yt'][w])} |")
        L += ["", "### 播放最多的 20 个", "", "| 视频 | 频道 | 分类 | 播放 | 时长(分) | 发布 |", "|---|---|---|---|---|---|"]
        for v in vids[:20]:
            L.append(f"| [{md(v['title'])[:80]}](https://www.youtube.com/watch?v={v['id']}) | {md(v['channel'])} | "
                     f"{md(v['category'])} | {v['views']:,} | {v['minutes']} | {v['published']} |")
        if longf:
            L += ["", f"### 上榜的长视频（≥{LONG_MIN} 分钟，和 Giọng Mây 相关）", "",
                  "| 视频 | 频道 | 播放 | 时长(分) |", "|---|---|---|---|"]
            for v in longf[:15]:
                L.append(f"| [{md(v['title'])[:80]}](https://www.youtube.com/watch?v={v['id']}) | {md(v['channel'])} | "
                         f"{v['views']:,} | {v['minutes']} |")
    else:
        L.append(f"> 没取到：{errs.get('youtube', '无数据')}")
    L.append("")

    L += ["## 4. 每周手动看一眼（没有免费接口）", "",
          "- TikTok 越南热门话题 / 歌曲 / 关键词（需登录，右上角地区选 Vietnam）："
          "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en?countryCode=VN&period=7",
          "- Facebook 广告资料库（越南，按关键词查谁在投广告，例：giọng đọc ai）："
          "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=VN&q=gi%E1%BB%8Dng%20%C4%91%E1%BB%8Dc%20ai",
          ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--days", type=int, default=7, help="window for the 'days in a row' column")
    ap.add_argument("--from-snapshot", action="store_true", help="rebuild the report from the saved snapshot")
    a = ap.parse_args()
    load_env()
    STATE.mkdir(parents=True, exist_ok=True)
    snap_file = STATE / f"{a.date}.json"

    if a.from_snapshot:
        snap = json.loads(snap_file.read_text(encoding="utf-8"))
    else:
        snap = {"date": a.date, "errors": {}}
        jobs = [("trends", google_trends), ("baomoi", baomoi)]
        key = os.environ.get("YOUTUBE_API_KEY", "").strip()
        if key:
            jobs.append(("youtube", lambda: youtube(key)))
        else:
            snap["errors"]["youtube"] = ".env 里没有 YOUTUBE_API_KEY，已跳过"
        for name, fn in jobs:
            try:
                snap[name] = fn()
                print(f"{name}: ok")
            except Exception as e:  # noqa: BLE001 - one source failing must not stop the others
                msg = str(e)
                if key:
                    msg = msg.replace(key, "***")
                snap["errors"][name] = f"{type(e).__name__}: {msg}"[:300]
                print(f"{name}: FAILED {snap['errors'][name]}")
        snap_file.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    out = ROOT / f"report-vn-social-{a.date}.md"
    out.write_text(report(a.date, snap, streaks(a.date, a.days), a.days), encoding="utf-8")
    print("wrote", out.name)
    sys.exit(0 if any(snap.get(k) for k in ("trends", "baomoi", "youtube")) else 1)


if __name__ == "__main__":
    main()
