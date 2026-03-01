"""
Entrypoint: load config and run the SwiftEdge alert bot.
When built as .exe, default config is next to the executable.
Send /status in Telegram to get bot status and config.
"""
import sys
from pathlib import Path

from bot import run_bot
from config import ConfigError, load_config, _get_default_config_dir


def main() -> None:
    config_path = _get_default_config_dir() / "config.json"
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    try:
        cfg = load_config(config_path)
        print(f"Config loaded: {cfg['symbol']} {cfg['chart_timeframe']}", flush=True)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)
    run_bot(config_path)


if __name__ == "__main__":
    main()
