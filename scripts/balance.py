"""Check AIsa and GoAnyAPI balances (both endpoints are free).

    python scripts/balance.py            # print balances
Writes state/balance.json; if a balance is below its threshold, also writes state/balance_alert.txt
(run-daily.ps1 shows it as a Windows notification) and exits with code 2.

Thresholds (USD) can be set in .env: AISA_MIN_USD (default 5), GOANYAPI_MIN_USD (default 2).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
# rough daily spend with the current setup (global + VN + translation), for "days left"
DAILY_USD = {"aisa": 0.6, "goanyapi": 0.15}


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                               "User-Agent": "new-term-radar-balance"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def aisa() -> float | None:
    k = os.environ.get("AISA_API_KEY", "").strip()
    if not k:
        return None
    body = get(os.environ.get("AISA_API_BASE_URL", "https://api.aisa.one") + "/v1/credits/balance", k)
    # The API answers in micro-USD (available_balance_micros_usd); older answers had available_usd.
    for d in (body, body.get("data") or {}, body.get("balance") if isinstance(body.get("balance"), dict) else {},
              (body.get("data") or {}).get("balance") if isinstance((body.get("data") or {}).get("balance"), dict) else {}):
        if d.get("available_balance_micros_usd") is not None:
            return round(int(d["available_balance_micros_usd"]) / 1e6, 2)
        if d.get("available_usd") is not None:
            return float(d["available_usd"])
    return None


def goany() -> float | None:
    k = os.environ.get("GOANYAPI_API_KEY", "").strip()
    if not k:
        return None
    body = get(os.environ.get("GOANYAPI_BASE_URL", "https://api.goanyapi.com") + "/api/v1/credits/balance", k)
    c = (body.get("data") or {}).get("remainingCredits")
    return round(int(c) / 1000, 3) if c is not None else None   # 1 credit = $0.001


def main() -> int:
    load_env()
    STATE.mkdir(exist_ok=True)
    mins = {"aisa": float(os.environ.get("AISA_MIN_USD", 5)), "goanyapi": float(os.environ.get("GOANYAPI_MIN_USD", 2))}
    result, alerts, lines = {"checked": datetime.now().isoformat(timespec="minutes")}, [], []
    for name, fn, label in (("aisa", aisa, "AIsa"), ("goanyapi", goany, "GoAnyAPI")):
        try:
            usd = fn()
        except Exception as e:
            result[name] = None
            result[name + "_error"] = str(e)[:120]
            lines.append(f"{label}: 查询失败 / lỗi ({str(e)[:80]})")
            continue
        result[name] = usd
        if usd is None:
            lines.append(f"{label}: 未配置 key 或无数据 / chưa cấu hình")
            continue
        days = int(usd / DAILY_USD[name]) if DAILY_USD[name] else None
        lines.append(f"{label}: ${usd:.2f}（约够 {days} 天 / đủ khoảng {days} ngày）")
        if usd < mins[name]:
            alerts.append(f"{label} 余额 ${usd:.2f}，低于 ${mins[name]:.0f}，请充值 / số dư thấp, cần nạp thêm")
    (STATE / "balance.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    alert_file = STATE / "balance_alert.txt"
    if alerts:
        alert_file.write_text("\n".join(alerts), encoding="utf-8")
    elif alert_file.exists():
        alert_file.unlink()
    print("\n".join(lines + (["⚠️ " + a for a in alerts])))
    return 2 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
