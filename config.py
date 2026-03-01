"""
Load and validate config from config.json. Optional env override for secrets.
When built as .exe (PyInstaller), default config path is the directory containing the executable.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any


def _get_default_config_dir() -> Path:
    """Directory for config.json: exe dir when frozen, else script dir."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()

VALID_CHART_TIMEFRAMES = ("1M", "5M", "15M", "30M", "1H", "4H", "1D")
VALID_SIGNAL_TYPES = ("BoS", "MSS")
RL_BARS_BY_TIMEFRAME = {
    "1M": 1,
    "5M": 1,
    "15M": 2,
    "30M": 2,
    "1H": 3,
    "4H": 4,
    "1D": 5,
}


class ConfigError(Exception):
    """Raised when config is invalid or missing required fields."""


DEFAULT_CONFIG: dict[str, Any] = {
    "symbol": "EURUSD",
    "chart_timeframe": "5M",
    "structure_timeframe": "",
    "sma_length": 25,
    "signal_type": "BoS",
    "rl_bars": None,
    "poll_interval_seconds": 60,
    "telegram": {
        "bot_token": "YOUR_BOT_TOKEN",
        "chat_id": "YOUR_CHAT_ID",
    },
    "mt5": {},
}


def init_default_config(path: Path) -> None:
    """Write default config.json to path if parent dir exists or can be created."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)


def _default_rl_bars(chart_timeframe: str) -> int:
    if chart_timeframe not in RL_BARS_BY_TIMEFRAME:
        raise ConfigError(f"chart_timeframe must be one of {VALID_CHART_TIMEFRAMES}")
    return RL_BARS_BY_TIMEFRAME[chart_timeframe]


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load config from JSON file. Apply defaults and validate.
    Optional env overrides: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
    """
    path = Path(config_path) if config_path else _get_default_config_dir() / "config.json"
    path = path.resolve()
    created = False
    if not path.exists():
        init_default_config(path)
        created = True

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # Required
    symbol = raw.get("symbol")
    if not symbol or not isinstance(symbol, str):
        raise ConfigError("config must have a non-empty string 'symbol'")

    chart_timeframe = raw.get("chart_timeframe", "5M")
    if chart_timeframe not in VALID_CHART_TIMEFRAMES:
        raise ConfigError(f"chart_timeframe must be one of {VALID_CHART_TIMEFRAMES}")

    structure_timeframe = raw.get("structure_timeframe", "")
    if structure_timeframe and structure_timeframe not in VALID_CHART_TIMEFRAMES:
        raise ConfigError(
            f"structure_timeframe must be empty or one of {VALID_CHART_TIMEFRAMES}"
        )

    sma_length = raw.get("sma_length", 25)
    if not isinstance(sma_length, int) or sma_length < 1:
        raise ConfigError("sma_length must be an integer >= 1")

    signal_type = raw.get("signal_type", "BoS")
    if signal_type not in VALID_SIGNAL_TYPES:
        raise ConfigError(f"signal_type must be one of {VALID_SIGNAL_TYPES}")

    rl_bars = raw.get("rl_bars")
    if rl_bars is None:
        rl_bars = _default_rl_bars(chart_timeframe)
    elif not isinstance(rl_bars, int) or rl_bars < 1:
        raise ConfigError("rl_bars must be a positive integer or null")

    poll_interval_seconds = raw.get("poll_interval_seconds", 60)
    if not isinstance(poll_interval_seconds, (int, float)) or poll_interval_seconds <= 0:
        raise ConfigError("poll_interval_seconds must be a positive number")

    telegram = raw.get("telegram")
    if not isinstance(telegram, dict):
        raise ConfigError("config must have a 'telegram' object")
    bot_token = (
        os.environ.get("TELEGRAM_BOT_TOKEN") or telegram.get("bot_token") or ""
    )
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or telegram.get("chat_id") or ""
    if not bot_token or not chat_id:
        msg = (
            "Created default config at " + str(path) + ". "
            if created
            else ""
        ) + (
            "telegram.bot_token and telegram.chat_id are required. "
            "Edit config.json or set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )
        raise ConfigError(msg)
    if bot_token.strip() == "YOUR_BOT_TOKEN" or str(chat_id).strip() == "YOUR_CHAT_ID":
        msg = (
            "Created default config at " + str(path) + ". "
            if created
            else ""
        ) + "Replace YOUR_BOT_TOKEN and YOUR_CHAT_ID in config.json with your Telegram bot token and chat ID."
        raise ConfigError(msg)
    telegram_config = {"bot_token": bot_token, "chat_id": str(chat_id).strip()}

    mt5 = raw.get("mt5")
    if mt5 is None:
        mt5 = {}
    if not isinstance(mt5, dict):
        raise ConfigError("mt5 must be an object")

    return {
        "symbol": symbol.strip(),
        "chart_timeframe": chart_timeframe,
        "structure_timeframe": structure_timeframe if structure_timeframe else chart_timeframe,
        "sma_length": sma_length,
        "signal_type": signal_type,
        "rl_bars": rl_bars,
        "poll_interval_seconds": int(poll_interval_seconds),
        "telegram": telegram_config,
        "mt5": mt5,
    }
