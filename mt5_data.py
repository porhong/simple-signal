"""
Fetch chart and structure TF bars from MT5. Map timeframe strings to MT5 enums.
"""
from typing import Any

import numpy as np

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

TIMEFRAME_MAP = {
    "1M": None,  # set below
    "5M": None,
    "15M": None,
    "30M": None,
    "1H": None,
    "4H": None,
    "1D": None,
}


def _get_mt5_timeframes() -> dict[str, Any]:
    if mt5 is None:
        return {}
    return {
        "1M": mt5.TIMEFRAME_M1,
        "5M": mt5.TIMEFRAME_M5,
        "15M": mt5.TIMEFRAME_M15,
        "30M": mt5.TIMEFRAME_M30,
        "1H": mt5.TIMEFRAME_H1,
        "4H": mt5.TIMEFRAME_H4,
        "1D": mt5.TIMEFRAME_D1,
    }


def get_timeframe_enum(tf_str: str) -> int:
    """Return MT5 timeframe enum for config string (e.g. '5M' -> TIMEFRAME_M5)."""
    m = _get_mt5_timeframes()
    if tf_str not in m:
        raise ValueError(f"Unknown timeframe: {tf_str}. Valid: {list(m.keys())}")
    return m[tf_str]


def fetch_bars(
    symbol: str,
    timeframe_str: str,
    count: int = 1000,
) -> dict[str, np.ndarray]:
    """
    Fetch bars from MT5. Returns dict with keys: time, open, high, low, close.
    Values are numpy arrays (oldest first). Requires MT5 to be initialized.
    """
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package is not installed")
    tf = get_timeframe_enum(timeframe_str)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        raise RuntimeError(f"MT5 copy_rates_from_pos failed: {err}")

    # MT5 returns newest first (index 0 = current bar). Reverse for chronological (oldest first).
    rates = rates[::-1]
    return {
        "time": np.array(rates["time"], dtype=np.float64),
        "open": np.array(rates["open"], dtype=np.float64),
        "high": np.array(rates["high"], dtype=np.float64),
        "low": np.array(rates["low"], dtype=np.float64),
        "close": np.array(rates["close"], dtype=np.float64),
    }


def initialize_mt5(path: str | None = None, login: int | None = None, server: str | None = None) -> bool:
    """Initialize MT5 terminal. Optional path, login, server from config."""
    if mt5 is None:
        return False
    kwargs = {}
    if path:
        kwargs["path"] = path
    if login is not None:
        kwargs["login"] = login
    if server:
        kwargs["server"] = server
    return mt5.initialize(**kwargs) if kwargs else mt5.initialize()


def shutdown_mt5() -> None:
    if mt5 is not None:
        mt5.shutdown()
