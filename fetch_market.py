from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
import yfinance as yf

try:
    import akshare as ak
except ImportError:  # A-share symbols can still use the yfinance fallback.
    ak = None


SHANGHAI = timezone(timedelta(hours=8))
OUTPUT = Path(os.getenv("MARKET_DATA_OUTPUT", "data/latest.json"))


@dataclass(frozen=True)
class Asset:
    name: str
    symbol: str
    market: str
    currency: str
    yf_symbol: str
    ak_symbol: str | None = None
    ak_kind: str | None = None


ASSETS = [
    Asset("上证指数", "000001.SH", "CN", "CNY", "000001.SS", "sh000001", "index"),
    Asset("深证成指", "399001.SZ", "CN", "CNY", "399001.SZ", "sz399001", "index"),
    Asset("创业板指", "399006.SZ", "CN", "CNY", "399006.SZ", "sz399006", "index"),
    Asset("恒生指数", "^HSI", "HK", "HKD", "^HSI"),
    Asset("恒生科技指数", "^HSTECH", "HK", "HKD", "^HSTECH"),
    Asset("道琼斯工业指数", "^DJI", "US", "USD", "^DJI"),
    Asset("标普500指数", "^GSPC", "US", "USD", "^GSPC"),
    Asset("纳斯达克综合指数", "^IXIC", "US", "USD", "^IXIC"),
    Asset("黄金期货", "GC=F", "COMMODITY", "USD/oz", "GC=F"),
    Asset("铜期货", "HG=F", "COMMODITY", "USD/lb", "HG=F"),
    Asset("WTI原油期货", "CL=F", "COMMODITY", "USD/bbl", "CL=F"),
    Asset("布伦特原油期货", "BZ=F", "COMMODITY", "USD/bbl", "BZ=F"),
    Asset("牧原股份", "002714.SZ", "CN", "CNY", "002714.SZ", "002714", "stock"),
    Asset("紫金矿业", "601899.SH", "CN", "CNY", "601899.SS", "601899", "stock"),
]


def _clean_history(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("empty price history")
    result = frame.copy()
    result.columns = [str(c).lower() for c in result.columns]
    if "date" in result.columns:
        result = result.set_index("date")
    if "close" not in result.columns:
        raise ValueError("price history has no close column")
    result.index = pd.to_datetime(result.index)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["close"]).sort_index()
    if len(result) < 2:
        raise ValueError("need at least two valid closes")
    return result


def _from_akshare(asset: Asset) -> pd.DataFrame:
    if ak is None or not asset.ak_symbol:
        raise ValueError("AKShare source unavailable for this symbol")
    if asset.ak_kind == "index":
        return ak.stock_zh_index_daily_em(symbol=asset.ak_symbol)
    if asset.ak_kind == "stock":
        end = datetime.now(SHANGHAI).date()
        start = end - timedelta(days=10)
        frame = ak.stock_zh_a_hist(
            symbol=asset.ak_symbol,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="",
        )
        return frame.rename(columns={"日期": "date", "收盘": "close"})
    raise ValueError("unknown AKShare asset kind")


def _from_yfinance(asset: Asset) -> pd.DataFrame:
    # Ten calendar days are requested so the five-day observation window still
    # has a prior close after weekends and most holidays.
    end = datetime.now(SHANGHAI).date() + timedelta(days=1)
    start = end - timedelta(days=10)
    frame = yf.download(
        asset.yf_symbol,
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=False,
        progress=False,
        timeout=20,
    )
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return frame


def _quote(asset: Asset) -> dict:
    sources: list[tuple[str, Callable[[Asset], pd.DataFrame]]] = []
    if asset.market == "CN" and asset.ak_symbol:
        sources.append(("akshare", _from_akshare))
    sources.append(("yfinance", _from_yfinance))
    errors = []
    for source_name, loader in sources:
        try:
            history = _clean_history(loader(asset))
            latest = history.iloc[-1]
            previous = history.iloc[-2]
            close = float(latest["close"])
            previous_close = float(previous["close"])
            change_pct = (close / previous_close - 1) * 100
            if not all(math.isfinite(x) for x in (close, previous_close, change_pct)):
                raise ValueError("non-finite price")
            return {
                "name": asset.name,
                "symbol": asset.symbol,
                "market": asset.market,
                "currency": asset.currency,
                "trade_date": history.index[-1].date().isoformat(),
                "close": round(close, 4),
                "previous_close": round(previous_close, 4),
                "change_pct": round(change_pct, 4),
                "source": source_name,
            }
        except Exception as exc:  # continue to fallback and retain diagnostics
            errors.append(f"{source_name}: {type(exc).__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def build_payload() -> dict:
    quotes, errors = {}, {}
    for asset in ASSETS:
        try:
            quotes[asset.symbol] = _quote(asset)
        except Exception as exc:
            errors[asset.symbol] = str(exc)
    if not quotes:
        raise RuntimeError(f"No market data could be fetched: {errors}")
    now = datetime.now(SHANGHAI)
    return {
        "schema_version": "1.0",
        "generated_at": now.isoformat(timespec="seconds"),
        "timezone": "Asia/Shanghai",
        "observation_window": {
            "natural_days": 5,
            "selection": "latest valid trading day; change versus prior valid close",
        },
        "quotes": quotes,
        "errors": errors,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(payload['quotes'])} quotes to {OUTPUT}")
    if payload["errors"]:
        print(f"Warnings: {json.dumps(payload['errors'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
