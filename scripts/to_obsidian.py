"""Import today's radar reports into the Obsidian vault.

    python scripts/to_obsidian.py --vault "E:\\obsidian\\knowledge\\40_SEO选题与新词雷达" [--date 2026-10-23]

Writes raw/radar-daily/YYYY/YYYY-MM/<date>-global.md and -vn.md (with frontmatter for Bases)
and appends one line per day to log.md. Safe to run more than once.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TRANSLATE_MODEL = "gpt-4.1-mini"
TRANSLATE_SYSTEM = (
    "Translate this Chinese Markdown section of an SEO keyword report into natural Vietnamese for a Vietnamese "
    "business partner. Keep Markdown structure, tables, links, numbers, dates, emoji and repository names exactly. "
    "Do not translate keywords that are already Vietnamese or English product names. Output only the translation.")
REGIONS = {"global": ("report-{d}.md", "全球"), "vn": ("report-vn-{d}.md", "越南 / Việt Nam"),
           "vn-social": ("report-vn-social-{d}.md", "越南社交热点 / Xu hướng MXH")}


def table_after(text: str, heading: str) -> list[dict]:
    """Rows of the first Markdown table after a heading that contains `heading`."""
    lines = text.splitlines()
    try:
        i = next(k for k, l in enumerate(lines) if l.startswith("#") and heading in l)
    except StopIteration:
        return []
    rows, header = [], None
    for l in lines[i + 1:]:
        if l.startswith("#"):
            break
        if not l.startswith("|"):
            if header:
                break
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if header is None:
            header = cells
        elif not set("".join(cells)) <= set("-: "):
            rows.append(dict(zip(header, cells)))
    return rows


def clean(term: str) -> str:
    return re.sub(r"[*🎬🎙🖼⚡🔎]", "", term).strip()


def summarize(text: str) -> dict:
    uc = table_after(text, "新词表")
    cand = table_after(text, "候选新词")
    cost = re.search(r"AIsa 数据花费[:：]\s*\$([\d.]+)", text)
    return {
        "candidates": len(cand),
        "priority_terms": [clean(r.get("关键词", "")) for r in uc if r.get("决策", "").startswith("优先")],
        "can_enter": [clean(r.get("关键词", "")) for r in uc if r.get("首页竞争", "") == "能进"],
        "top_candidates": [clean(r.get("词", "")) for r in cand[:5]],
        "cost_usd": float(cost.group(1)) if cost else None,
    }


def yaml_list(xs: list[str]) -> str:
    return "[]" if not xs else "\n" + "\n".join(f'  - "{x}"' for x in xs)


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def to_vietnamese(text: str) -> str:
    """Translate section by section (split on ### headings); returns '' if anything fails."""
    from radar import aisa
    parts = re.split(r"(?m)^(?=### )", text)
    out = []
    for part in parts:
        if not part.strip():
            continue
        out.append(aisa.chat(TRANSLATE_MODEL, TRANSLATE_SYSTEM, part, max_tokens=6000).strip())
    return "\n\n".join(out)


def callout(text: str) -> str:
    return "> [!note]- 🇻🇳 Tiếng Việt\n" + "\n".join("> " + l if l else ">" for l in text.splitlines())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=r"E:\obsidian\knowledge\40_SEO选题与新词雷达", help="the 40_SEO选题与新词雷达 folder")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--no-translate", action="store_true")
    a = ap.parse_args()
    load_env()
    vault, d = Path(a.vault), a.date
    out_dir = vault / "raw" / "radar-daily" / d[:4] / d[:7]
    out_dir.mkdir(parents=True, exist_ok=True)

    bal = {}
    bal_file = ROOT / "state" / "balance.json"
    if bal_file.exists():
        try:
            import json
            bal = json.loads(bal_file.read_text(encoding="utf-8"))
        except ValueError:
            bal = {}
    links, prio = [], []
    for region, (pattern, label) in REGIONS.items():
        src = ROOT / pattern.format(d=d)
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8")
        s = summarize(text)
        name = f"{d}-{region}"
        fm = (f"---\ntype: radar-daily\nproject: SEO选题雷达\ndate: {d}\nregion: {region}\n"
              f"candidates: {s['candidates']}\ncost_usd: {s['cost_usd'] if s['cost_usd'] is not None else ''}\n"
              f"priority_terms: {yaml_list(s['priority_terms'])}\ncan_enter: {yaml_list(s['can_enter'])}\n"
              f"top_candidates: {yaml_list(s['top_candidates'])}\n"
              f"aisa_balance_usd: {bal.get('aisa') if bal.get('aisa') is not None else ''}\n"
              f"goanyapi_balance_usd: {bal.get('goanyapi') if bal.get('goanyapi') is not None else ''}\ntags:\n  - radar/daily\n  - radar/{region}\n---\n\n")
        body = f"# 雷达日报 {d}（{label}）\n\n> 自动导入自 `{src.name}`，请勿手改。结论写到 wiki/。\n\n" + text
        if region == "vn" and not a.no_translate:
            try:
                vi = to_vietnamese(text)
                body = (f"# 雷达日报 {d}（{label}）/ Báo cáo radar {d} (Việt Nam)\n\n"
                        f"> 自动导入自 `{src.name}`，请勿手改。越南语译文在下面的折叠块里，中文原文在分隔线之后。\n"
                        f"> Tự động nhập từ `{src.name}`, không sửa tay. Bản tiếng Việt nằm trong khối gấp ngay bên dưới (bấm để mở); bản gốc tiếng Trung ở sau đường kẻ ngang.\n\n"
                        f"{callout(vi)}\n\n---\n\n" + text)
            except Exception as e:  # keep the Chinese report
                body += f"\n\n> 越南语翻译失败 / Dịch thất bại: {e}\n"
        (out_dir / f"{name}.md").write_text(fm + body, encoding="utf-8")
        rel = f"40_SEO选题与新词雷达/raw/radar-daily/{d[:4]}/{d[:7]}/{name}"
        links.append(f"[[{rel}|{label}]]")
        prio += [f"{t}({label})" for t in s["priority_terms"]]

    if not links:
        print("no reports for", d)
        return
    log = vault / "log.md"
    content = log.read_text(encoding="utf-8") if log.exists() else "# 日志\n"
    marker = f"<!-- radar {d} -->"
    money = []
    for k, label, low in (("aisa", "AIsa", 5), ("goanyapi", "GoAnyAPI", 2)):
        if bal.get(k) is not None:
            money.append(f"{label} ${bal[k]:.2f}" + (" ⚠️" if bal[k] < low else ""))
    money_txt = f"；余额 / Số dư：{' · '.join(money)}" if money else ""
    line = (f"- 日报 / Báo cáo：{' · '.join(links)}；优先词 / Từ ưu tiên：{'、'.join(prio) if prio else '无 / không có'}{money_txt} {marker}")
    if marker in content:
        content = re.sub(rf"^- 日报.*{re.escape(marker)}$", line, content, flags=re.M)
    elif f"\n## {d}\n" in content:
        content = content.replace(f"\n## {d}\n", f"\n## {d}\n\n{line}\n", 1)
    else:
        content = content.rstrip() + f"\n\n## {d}\n\n{line}\n"
    log.write_text(content, encoding="utf-8")
    print("imported:", ", ".join(links))


if __name__ == "__main__":
    main()
