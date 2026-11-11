"""Monthly visits of competitor sites via GoAnyAPI (needs GOANYAPI_API_KEY in .env).

    python scripts/traffic.py                         # default list: Vietnamese voice / TTS competitors
    python scripts/traffic.py vbee.vn voiceai.vn ...  # your own list

Writes traffic-YYYY-MM-DD.md (+ .json with the raw answers) next to this repo's reports.
Cost: a few GoAnyAPI credits per domain (well under $0.10 for the default list).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT = ["vbee.vn", "voiceai.vn", "studio.voiceai.vn", "ausynclab.io", "lucylab.io", "vivibe.app",
           "ttsfree.com", "luvvoice.com", "ttsmaker.com", "narakeet.com", "fpt.ai", "elevenlabs.io"]


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    load_env()
    from radar import goanyapi
    if not goanyapi.key():
        sys.exit("no GOANYAPI_API_KEY in .env")
    domains = sys.argv[1:] or DEFAULT
    raw, rows, spent = {}, [], 0
    for d in domains:
        try:
            data, cost = goanyapi.call("traffic", domain=d, month=3)
            spent += cost
        except goanyapi.GoAnyError as e:
            rows.append((d, "error: " + str(e)[:60], "", "", "")); print(d, "error", e); continue
        raw[d] = data
        months = sorted((data.get("EstimatedMonthlyVisits") or {}).items())
        series = [(m[:7], int(float(v))) for m, v in months if v not in (None, "")]
        top = data.get("TopCountryShares") or data.get("CountryShares") or []
        vn = ""
        if isinstance(top, list):
            for c in top:
                if str(c.get("CountryCode", c.get("Country", ""))).upper() in ("VN", "704"):
                    vn = f"{float(c.get('Value', c.get('Share', 0))) * 100:.0f}%"
        src = data.get("TrafficSources") or {}
        search = src.get("Search") if isinstance(src, dict) else None
        rows.append((d, " → ".join(f"{m}: {v:,}" for m, v in series) or "no data",
                     f"{series[-1][1]:,}" if series else "", vn,
                     f"{float(search) * 100:.0f}%" if isinstance(search, (int, float)) else ""))
        print(d, rows[-1][1])
    out = ROOT / f"traffic-{date.today().isoformat()}"
    (Path(str(out) + ".json")).write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# 竞品流量 / Lưu lượng đối thủ {date.today()}", "", "来源：GoAnyAPI traffic（估算值）", "",
             "| 域名 | 近 3 个月访问量 | 最近一月 | 越南占比 | 搜索来源占比 |", "|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows]
    lines += ["", f"花费 / Chi phí: ${spent / 1e6:.3f}"]
    Path(str(out) + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved {out}.md, spent ${spent / 1e6:.3f}")


if __name__ == "__main__":
    main()
