"""vn_social parsing and report, offline (fixtures shaped like the real feeds on 2026-10-25)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("vn_social", ROOT / "scripts" / "vn_social.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>mùa thu</title><ht:approx_traffic>100+</ht:approx_traffic><pubDate>Sat, 24 Oct 2026 21:10:00 -0700</pubDate>
<ht:news_item><ht:news_item_title>Thu &amp; nắng</ht:news_item_title><ht:news_item_url>https://x.vn/a</ht:news_item_url><ht:news_item_source>VnE</ht:news_item_source></ht:news_item></item>
<item><title>giá vàng</title><ht:approx_traffic>2,000+</ht:approx_traffic><pubDate>x</pubDate></item>
</channel></rss>"""

ART = lambda i, cl=None, hot=False: {"id": i, "contentId": i, "title": f"Tin {i}", "url": f"/tin-c{i}.epi" + ("#|hotnews|index0" if hot else ""),
                                      "publisher": {"name": "Báo A"}, **({"cluster": {"name": cl, "url": "/t.epi", "total": 50}} if cl else {})}
NEXT = {"props": {"pageProps": {"resp": {"data": {"content": {"sections": [
    {"title": "", "items": [ART(1, "#Tô Lâm", True), ART(2, "#Bão số 9")]},
    {"title": "#Lifestyle", "items": [ART(3, "#Tô Lâm"), ART(1, "#Tô Lâm", True)]}]},
    "sidebar": [{"items": [ART(4)]}]}}}}}
PAGE = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(NEXT)}</script></html>'


def test_parse_trends():
    t = vs.parse_trends(RSS)
    assert [x["term"] for x in t] == ["mùa thu", "giá vàng"]
    assert t[1]["traffic_n"] == 2000 and t[0]["news"][0]["title"] == "Thu & nắng"


def test_parse_baomoi_dedupes_and_counts_clusters():
    b = vs.parse_baomoi(PAGE)
    assert len(b["stories"]) == 4
    assert b["clusters"][0] == {"name": "#Tô Lâm", "url": "https://baomoi.com/t.epi", "total": 50, "on_home": 2}
    assert [s["hot"] for s in b["stories"]][:2] == [True, False]


def test_iso_minutes():
    assert vs.iso_minutes("PT1H10M30S") == 70.5 and vs.iso_minutes("PT45S") == 0.75 and vs.iso_minutes("") == 0


def test_yt_keywords_counts_each_channel_once():
    v = [{"channel": "A", "title": "x #Truyen", "tags": ["truyện ma"]}, {"channel": "A", "title": "y", "tags": ["truyện ma"]},
         {"channel": "B", "title": "z", "tags": ["Truyện ma".lower()]}]
    assert vs.yt_keywords(v)["truyện ma"] == 2 and vs.yt_keywords(v)["truyen"] == 1


def test_report_and_streaks(tmp_path, monkeypatch):
    monkeypatch.setattr(vs, "STATE", tmp_path)
    (tmp_path / "2026-10-24.json").write_text(json.dumps({"trends": [{"term": "Giá vàng"}], "baomoi": {"clusters": [{"name": "#Tô Lâm"}]}}), encoding="utf-8")
    snap = {"trends": vs.parse_trends(RSS), "baomoi": vs.parse_baomoi(PAGE), "errors": {"youtube": "no key"},
            "youtube": None}
    md = vs.report("2026-10-25", snap, vs.streaks("2026-10-25", 7), 7)
    assert "| giá vàng | 2,000+ | 2天 |" in md and "| mùa thu | 100+ | 🆕 |" in md
    assert "#Tô Lâm" in md and "2天" in md.split("Báo Mới")[1] and "no key" in md
