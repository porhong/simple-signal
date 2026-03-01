"""
Main loop: fetch chart + structure bars from MT5, align, run Pine logic,
send Telegram alert on new BUY/SELL signals only.
"""
import sys
import time
from pathlib import Path
from typing import Any

import requests

from align_bars import align_structure_to_chart
from config import load_config
from mt5_data import fetch_bars, initialize_mt5, shutdown_mt5
from pine_logic import run_state_machine


def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def get_telegram_updates(
    bot_token: str, offset: int | None = None, timeout: int = 5
) -> tuple[int, list[tuple[str, str]]]:
    """
    Poll for incoming messages. Returns (next_offset, [(chat_id, text), ...]).
    Only returns updates from the last offset; pass 0 or None for first run.
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params: dict[str, Any] = {"timeout": timeout}
    if offset is not None and offset > 0:
        params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=timeout + 5)
        if r.status_code != 200:
            return offset or 0, []
        data = r.json()
        if not data.get("ok"):
            return offset or 0, []
        updates = data.get("result") or []
    except Exception:
        return offset or 0, []

    next_offset = offset or 0
    out: list[tuple[str, str]] = []
    for u in updates:
        next_offset = max(next_offset, u.get("update_id", 0) + 1)
        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if chat_id and text:
            out.append((chat_id, text))
    return next_offset, out


def _format_status_reply(cfg: dict[str, Any], mt5_connected: bool = True) -> str:
    """Build status message for Telegram (config redacted, under 4096 chars)."""
    lines = [
        "SwiftEdge status",
        "—",
        f"Symbol: {cfg['symbol']}",
        f"Chart TF: {cfg['chart_timeframe']}",
        f"Structure TF: {cfg['structure_timeframe'] or '(same)'}",
        f"SMA length: {cfg['sma_length']}",
        f"Signal type: {cfg['signal_type']}",
        f"Poll: {cfg['poll_interval_seconds']}s",
        f"Bot token: {_redact(cfg['telegram']['bot_token'])}",
        f"Chat ID: {_redact(str(cfg['telegram']['chat_id']))}",
        "—",
        f"MT5: {'connected' if mt5_connected else 'not connected'}",
        "Bot: running",
    ]
    return "\n".join(lines)


def run_once(cfg: dict[str, Any]) -> tuple[bool, bool]:
    """
    Fetch data, align, run state machine. Returns (buy_signal_on_last_bar, sell_signal_on_last_bar).
    """
    symbol = cfg["symbol"]
    chart_tf = cfg["chart_timeframe"]
    structure_tf = cfg["structure_timeframe"]
    sma_length = cfg["sma_length"]
    signal_type = cfg["signal_type"]
    rl_bars = cfg["rl_bars"]

    count = 1000
    chart = fetch_bars(symbol, chart_tf, count)
    if structure_tf == chart_tf:
        structure = {k: v.copy() for k, v in chart.items()}
    else:
        structure = fetch_bars(symbol, structure_tf, count)

    phPs, phBi, plPs, plBi, htf_close, htf_time = align_structure_to_chart(
        chart["time"],
        structure["time"],
        structure["high"],
        structure["low"],
        structure["close"],
        rl_bars,
    )
    # Aligned arrays length = len(chart_time); chart bars might be more than structure alignment
    n = len(chart["time"])
    buy_signals, sell_signals = run_state_machine(
        sma_length,
        signal_type,
        chart["time"],
        chart["high"],
        chart["low"],
        chart["close"],
        phPs[:n],
        phBi[:n],
        plPs[:n],
        plBi[:n],
        htf_close[:n],
        htf_time[:n],
    )
    last_buy = buy_signals[-1] if buy_signals else False
    last_sell = sell_signals[-1] if sell_signals else False
    return last_buy, last_sell


def _redact(s: str, show_tail: int = 4) -> str:
    """Redact string for display, show last show_tail chars."""
    if not s or len(s) <= show_tail:
        return "***"
    return "*" * (len(s) - show_tail) + s[-show_tail:]


def run_status(config_path: str | Path | None = None) -> None:
    """Print bot status and current config (secrets redacted). Does not start the loop."""
    import json as _json

    cfg = load_config(config_path)
    symbol = cfg["symbol"]
    chart_tf = cfg["chart_timeframe"]
    structure_tf = cfg["structure_timeframe"]
    poll = cfg["poll_interval_seconds"]

    # Build display config (redact token and chat_id)
    display_cfg = {
        "symbol": cfg["symbol"],
        "chart_timeframe": cfg["chart_timeframe"],
        "structure_timeframe": structure_tf or "(same as chart)",
        "sma_length": cfg["sma_length"],
        "signal_type": cfg["signal_type"],
        "rl_bars": cfg["rl_bars"],
        "poll_interval_seconds": poll,
        "telegram": {
            "bot_token": _redact(cfg["telegram"]["bot_token"]),
            "chat_id": _redact(str(cfg["telegram"]["chat_id"])),
        },
        "mt5": cfg.get("mt5") or {},
    }

    print("--- SwiftEdge status ---", flush=True)
    print(_json.dumps(display_cfg, indent=2), flush=True)
    print("------------------------", flush=True)

    mt5_ok = False
    data_ok = False
    last_buy = False
    last_sell = False

    mt5_opts = cfg.get("mt5") or {}
    if initialize_mt5(
        path=mt5_opts.get("path"),
        login=mt5_opts.get("login"),
        server=mt5_opts.get("server"),
    ):
        mt5_ok = True
        try:
            last_buy, last_sell = run_once(cfg)
            data_ok = True
        except Exception as e:
            print(f"Data check error: {e}", file=sys.stderr, flush=True)
        shutdown_mt5()
    else:
        print("MT5: not connected (is MetaTrader 5 running?)", file=sys.stderr, flush=True)

    print(
        f"MT5: {'OK' if mt5_ok else 'FAIL'} | "
        f"Data: {'OK' if data_ok else 'FAIL'} | "
        f"Last bar: buy={last_buy} sell={last_sell}",
        flush=True,
    )
    if mt5_ok and data_ok:
        print("Bot status: WORKING (run without /status to start the alert loop).", flush=True)
    else:
        print("Bot status: NOT WORKING (fix MT5 or config and try again).", flush=True)


def run_bot(config_path: str | Path | None = None) -> None:
    """Load config, init MT5, loop: poll, run logic, send Telegram on new signals."""
    cfg = load_config(config_path)
    poll = cfg["poll_interval_seconds"]
    telegram = cfg["telegram"]
    symbol = cfg["symbol"]
    chart_tf = cfg["chart_timeframe"]

    print("Initializing MT5...", flush=True)
    mt5_opts = cfg.get("mt5") or {}
    if not initialize_mt5(
        path=mt5_opts.get("path"),
        login=mt5_opts.get("login"),
        server=mt5_opts.get("server"),
    ):
        print("MT5 initialization failed. Is MetaTrader 5 running?", file=sys.stderr)
        raise RuntimeError("MT5 initialization failed")
    print("MT5 OK.", flush=True)
    print(f"Bot started. Symbol={symbol} TF={chart_tf} Poll={poll}s. Press Ctrl+C to stop.", flush=True)

    last_buy = False
    last_sell = False
    loop_count = 0
    last_update_id = 0
    configured_chat_id = str(telegram["chat_id"])

    try:
        while True:
            try:
                # Handle Telegram /status command
                last_update_id, updates = get_telegram_updates(
                    telegram["bot_token"], offset=last_update_id, timeout=0
                )
                for chat_id, text in updates:
                    if text == "/status" and chat_id == configured_chat_id:
                        reply = _format_status_reply(cfg, mt5_connected=True)
                        send_telegram(reply, telegram["bot_token"], chat_id)

                buy_signal, sell_signal = run_once(cfg)
                if buy_signal and not last_buy:
                    msg = f"SwiftEdge BUY signal on {symbol} (TF={chart_tf})."
                    ok = send_telegram(msg, telegram["bot_token"], telegram["chat_id"])
                    print(f"[BUY] {msg} Telegram={'OK' if ok else 'FAIL'}", flush=True)
                if sell_signal and not last_sell:
                    msg = f"SwiftEdge SELL signal on {symbol} (TF={chart_tf})."
                    ok = send_telegram(msg, telegram["bot_token"], telegram["chat_id"])
                    print(f"[SELL] {msg} Telegram={'OK' if ok else 'FAIL'}", flush=True)
                last_buy = buy_signal
                last_sell = sell_signal
                loop_count += 1
                ts = time.strftime("%H:%M:%S")
                if buy_signal or sell_signal:
                    pass  # already printed above
                else:
                    print(f"[{ts}] Check #{loop_count} - no signal", flush=True)
            except Exception as e:
                err_msg = f"SwiftEdge bot error: {e}"
                print(err_msg, file=sys.stderr, flush=True)
                send_telegram(err_msg, telegram["bot_token"], telegram["chat_id"])
            time.sleep(poll)
    finally:
        shutdown_mt5()
        print("Bot stopped.", flush=True)
