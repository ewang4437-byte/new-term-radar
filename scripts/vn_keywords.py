"""Size a list of keywords for Google Vietnam: monthly searches, difficulty, and how weak page one is.

    python scripts/vn_keywords.py keywords-vn.txt            # asks before spending
    python scripts/vn_keywords.py keywords-vn.txt --yes      # no prompt
    options: --min-volume 50 (only check page one for terms with at least this volume)
             --location 2704 --lang vi   (other countries: e.g. 2840/en for the US)
             --watch everai.vn,giongmay.com   (list every keyword these sites rank for, with the URL)

Output: kw-<name>-YYYY-MM-DD.md and .csv next to the input file, plus -serp.csv with the full
page one of every checked term (position, domain, url, title, kind, rating): which page ranks where.
Costs (Oct 2026): volumes $0.09 per batch, difficulty ~$0.012, page one $0.002 per term,
site ratings $0.002 per new domain (GoAnyAPI, cached 30 days in state-vn).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def verdict(kd, weak: int, has_dr: bool) -> str:
    """Same rule as the radar: 能进 / 一般 / 挤满."""
    if weak >= 3 or (kd is not None and kd < 20):
        return "能进"
    if (weak == 0 or not has_dr) and (kd is None or kd >= 40):
        return "挤满"
    return "一般"


SERP_FIELDS = ["keyword", "volume", "position", "domain", "dr", "kind", "url", "title"]


def serp_rows(rows: list[dict], pages: dict, dr: dict) -> list[dict]:
    """One row per page-one result: which URL holds which position for which keyword."""
    vol = {r["keyword"]: r["volume"] for r in rows}
    out = []
    for kw, p in pages.items():
        for x in p["results"]:
            out.append({"keyword": kw, "volume": vol.get(kw, 0), "position": x.get("position"), "domain": x["domain"],
                        "dr": "" if dr.get(x["domain"]) is None else dr[x["domain"]], "kind": x.get("kind", ""),
                        "url": re.sub(r"[?&]srsltid=[^&#]*", "", x["url"]), "title": x["title"]})   # Google's click tag
    out.sort(key=lambda r: (-r["volume"], r["keyword"], r["position"] or 99))
    return out


def site_sections(serp: list[dict], watch: list[str], serp_file: str, top: int = 15) -> list[str]:
    """Markdown: the sites seen most across page one, then every ranking of the watched sites."""
    if not serp:
        return []
    seen: dict[str, dict] = {}
    for r in serp:
        s = seen.setdefault(r["domain"], {"dr": r["dr"], "kws": set(), "reach": 0})
        if r["keyword"] not in s["kws"]:
            s["kws"].add(r["keyword"]); s["reach"] += r["volume"]
    lines = ["", f"## 首页常见的站(前 {top})", "",
             "出现在几个词的首页、这些词的月搜合计。每个词的完整前十(名次、网址、标题)在 " + serp_file + "。", "",
             "| 站点 | 评分 | 上首页的词数 | 这些词月搜合计 |", "|---|---|---|---|"]
    for d, s in sorted(seen.items(), key=lambda t: (-len(t[1]["kws"]), -t[1]["reach"]))[:top]:
        lines.append(f"| {d} | {s['dr']} | {len(s['kws'])} | {s['reach']} |")
    for w in watch:
        hits = [r for r in serp if r["domain"] == w or r["domain"].endswith("." + w)]
        lines += ["", f"## {w} 排在哪些词", ""]
        if not hits:
            lines.append("这些词的首页里都没有它。")
            continue
        lines += ["| 关键词 | 月搜 | 名次 | 网址 |", "|---|---|---|---|"]
        lines += [f"| {r['keyword']} | {r['volume']} | {r['position']} | {r['url']} |" for r in hits]
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--location", type=int, default=2704)
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--min-volume", type=int, default=50)
    ap.add_argument("--weak-dr", type=int, default=30)
    ap.add_argument("--watch", default="", help="comma-separated domains to list keyword by keyword")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    load_env()
    os.environ["RADAR_LANGUAGE_CODE"] = a.lang
    from radar import competition, goanyapi, usecases  # after env is set

    src = Path(a.file)
    words = list(dict.fromkeys(" ".join(l.lower().split()) for l in src.read_text(encoding="utf-8-sig").splitlines()
                               if l.strip() and not l.lstrip().startswith("#")))
    if not words:
        sys.exit("no keywords in " + a.file)
    est = 0.09 + 0.012 + 0.002 * len(words) + (0.002 * 8 * len(words) if goanyapi.key() else 0)
    print(f"{len(words)} keywords, location {a.location}/{a.lang}. Worst-case cost about ${est:.2f} "
          f"(page one is only checked for terms with >= {a.min_volume} searches).")
    if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
        sys.exit(0)

    spent = 0
    vol, c = usecases.volumes(words, a.location); spent += c
    kd, c = competition.difficulty(words, a.location); spent += c

    rows = []
    for w in words:
        v = (vol.get(w) or {}).get("volume", 0)
        rows.append({"keyword": w, "volume": v, "month": (vol.get(w) or {}).get("month", ""), "kd": kd.get(w),
                     "weak": "", "weakest": "", "kinds": "", "ads": "", "verdict": "量太小" if v < a.min_volume else ""})

    checked = [r for r in rows if r["volume"] >= a.min_volume]
    pages = {}
    for r in checked:
        try:
            pages[r["keyword"]], c = competition.page_one(r["keyword"], a.location); spent += c
        except Exception as e:  # keep going, note it
            r["verdict"] = f"首页查询失败: {e}"[:60]
    domains = sorted({x["domain"] for p in pages.values() for x in p["results"] if x["domain"]})
    dr, c = competition.ratings(domains, ROOT / "state-vn") if domains else ({}, 0); spent += c

    for r in checked:
        p = pages.get(r["keyword"])
        if not p:
            continue
        scored = [(dr.get(x["domain"]), x["domain"]) for x in p["results"] if dr.get(x["domain"]) is not None]
        weak = sum(1 for s, _ in scored if s < a.weak_dr)
        low = min(scored) if scored else None
        kinds = {}
        for x in p["results"]:
            kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
        r.update(weak=weak if scored else "", weakest=f"{low[1]} ({low[0]})" if low else "",
                 kinds=" ".join(f"{k}{n}" for k, n in sorted(kinds.items(), key=lambda t: -t[1])),
                 ads="有" if p["ads"] else "", verdict=verdict(r["kd"], weak, bool(scored)))

    order = {"能进": 0, "一般": 1, "挤满": 2}
    rows.sort(key=lambda r: (order.get(r["verdict"], 3), -r["volume"]))
    stem = src.parent / f"kw-{src.stem}-{date.today().isoformat()}"
    with open(f"{stem}.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
    serp = serp_rows(rows, pages, dr)
    with open(f"{stem}-serp.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=SERP_FIELDS); wr.writeheader(); wr.writerows(serp)
    lines = [f"# 越南关键词检查 {date.today()}", "",
             f"{len(words)} 个词,{len(checked)} 个月搜 ≥ {a.min_volume} 查了首页。花费 ${spent / 1e6:.3f}。", "",
             "| 关键词 | 月搜 | 难度 | 首页弱站数(评分<30) | 最弱的站 | 首页构成 | 广告 | 判断 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['keyword']} | {r['volume']} | {'' if r['kd'] is None else r['kd']} | {r['weak']} | {r['weakest']} | "
                     f"{r['kinds']} | {r['ads']} | {r['verdict']} |")
    lines += ["", "能进 = 首页有 3 个以上评分 < 30 的站,或难度 < 20;挤满 = 没有弱站且难度 ≥ 40;"
              "首页构成:tool 工具页 / list 榜单 / article 文章 / video 视频 / forum 论坛。广告 = 有人花钱买这个点击。"]
    if not goanyapi.key():
        lines.append("没有 GOANYAPI_API_KEY:没有站点评分,只按难度判断。")
    lines += site_sections(serp, [d.strip().lower().removeprefix("www.") for d in a.watch.split(",") if d.strip()],
                           f"{stem.name}-serp.csv")
    Path(f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"done: {stem}.md / .csv, spent ${spent / 1e6:.3f}")


if __name__ == "__main__":
    main()
