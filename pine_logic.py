"""
Pure Python implementation of TrendCraft ICT SwiftEdge logic:
SMA, pivots (on provided series), BOS/MSS state machine, buy/sell and trendState.
No I/O; accepts aligned chart + structure data.
"""
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


def sma(series: np.ndarray, length: int) -> np.ndarray:
    """Rolling mean; first (length-1) values are NaN."""
    out = np.full_like(series, np.nan, dtype=float)
    for i in range(length - 1, len(series)):
        out[i] = np.mean(series[i - length + 1 : i + 1])
    return out


def compute_structure_pivots(
    high: np.ndarray, low: np.ndarray, time: np.ndarray, rl_bars: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute pivot high/low on structure TF. Same as Pine ta.pivothigh(rlBars, rlBars).
    Pivot at bar (i - rl_bars) is confirmed at bar i.
    Returns: phPs, phBi, plPs, plBi (same length as high; use NaN for invalid).
    """
    n = len(high)
    phPs = np.full(n, np.nan)
    phBi = np.full(n, np.nan)
    plPs = np.full(n, np.nan)
    plBi = np.full(n, np.nan)

    for i in range(rl_bars, n - rl_bars):
        pivot_bar = i - rl_bars
        left_start = max(0, pivot_bar - rl_bars)
        right_end = min(n, pivot_bar + rl_bars + 1)
        # Pivot high: high[pivot_bar] is max of window
        window_high = high[left_start:right_end]
        if len(window_high) > 0 and high[pivot_bar] >= np.max(window_high):
            phPs[i] = high[pivot_bar]
            phBi[i] = time[pivot_bar]
        # Pivot low: low[pivot_bar] is min of window
        window_low = low[left_start:right_end]
        if len(window_low) > 0 and low[pivot_bar] <= np.min(window_low):
            plPs[i] = low[pivot_bar]
            plBi[i] = time[pivot_bar]

    return phPs, phBi, plPs, plBi


@dataclass
class Piv:
    pp: float
    pi: float  # time of pivot bar


def _nan_equal(a: float, b: float) -> bool:
    if np.isnan(a) and np.isnan(b):
        return True
    if np.isnan(a) or np.isnan(b):
        return False
    return a == b


def run_state_machine(
    sma_length: int,
    signal_type: str,
    times: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    phPs: np.ndarray,
    phBi: np.ndarray,
    plPs: np.ndarray,
    plBi: np.ndarray,
    htf_close: np.ndarray,
    htf_time: np.ndarray,
) -> Tuple[List[bool], List[bool]]:
    """
    Run BOS/MSS state machine bar-by-bar. Returns (buy_signals, sell_signals) per bar.
    All arrays must have the same length (number of chart bars).
    """
    n = len(close)
    sma_low = sma(low, sma_length)
    sma_high = sma(high, sma_length)

    def is_na(x: float) -> bool:
        return np.isnan(x) or (isinstance(x, float) and x != x)

    # State (Pine var)
    bull = False
    nPh1 = np.nan
    nPl1 = np.nan
    pH: Piv | None = None
    pL: Piv | None = None
    nPh: Piv | None = None
    nPl: Piv | None = None
    mss_bull_var = False
    mss_bear_var = False
    last_bos_bull_level = np.nan
    last_bos_bear_level = np.nan
    last_mss_bull_level = np.nan
    last_mss_bear_level = np.nan
    trend_state = 0
    last_break_time: float | None = None
    nPh_prev: Piv | None = None
    nPl_prev: Piv | None = None

    buy_signals: List[bool] = []
    sell_signals: List[bool] = []

    for i in range(n):
        phPs_i = phPs[i] if i < len(phPs) else np.nan
        phBi_i = phBi[i] if i < len(phBi) else np.nan
        plPs_i = plPs[i] if i < len(plPs) else np.nan
        plBi_i = plBi[i] if i < len(plBi) else np.nan
        htf_close_i = htf_close[i] if i < len(htf_close) else np.nan
        htf_time_i = htf_time[i] if i < len(htf_time) else np.nan

        # Update nPh from structure pivot
        if not is_na(phPs_i):
            nPh = Piv(phPs_i, phBi_i)
            if pH is None:
                pH = Piv(phPs_i, phBi_i)
        else:
            nPh = nPh  # keep previous

        if not is_na(plPs_i):
            nPl = Piv(plPs_i, plBi_i)
            if pL is None:
                pL = Piv(plPs_i, plBi_i)
        else:
            nPl = nPl

        bos_bull = False
        bos_bear = False
        mss_bull = False
        mss_bear = False
        temp_bos_bull_level = np.nan
        temp_mss_bull_level = np.nan
        temp_bos_bear_level = np.nan
        temp_mss_bear_level = np.nan

        high_cond = high[i] if bull else htf_close_i
        time_high_cond = times[i] if bull else htf_time_i

        # nPl1 update
        if (not is_na(plPs_i) and bull and plPs_i > nPl1) or is_na(nPl1) or (
            not is_na(plPs_i) and plPs_i < nPl1
        ):
            nPl1 = plPs_i if not is_na(plPs_i) else nPl1

        # Break high
        break_high_cond = pH is not None and high_cond > pH.pp
        if break_high_cond:
            if bull:
                bos_bull = True
                temp_bos_bull_level = pH.pp
                if not mss_bull_var:
                    pass  # lin.shift().delete() - skip drawing
                mss_bull_var = False
            else:
                mss_bull = True
                temp_mss_bull_level = pH.pp
                mss_bull_var = True

            bull = True
            mss_bear_var = False
            pH = None
            pL = None
            if not is_na(nPl1) and nPl is not None:
                pL = Piv(nPl.pp, nPl.pi)
            last_break_time = time_high_cond

        low_cond = htf_close_i if bull else low[i]
        time_low_cond = htf_time_i if bull else times[i]

        # nPh1 update
        if (not is_na(phPs_i) and not bull and phPs_i < nPh1) or is_na(nPh1) or (
            not is_na(phPs_i) and phPs_i > nPh1
        ):
            nPh1 = phPs_i if not is_na(phPs_i) else nPh1

        # Break low
        break_low_cond = pL is not None and low_cond < pL.pp
        if break_low_cond:
            if not bull:
                bos_bear = True
                temp_bos_bear_level = pL.pp
                if not mss_bear_var:
                    pass
                mss_bear_var = False
            else:
                mss_bear = True
                temp_mss_bear_level = pL.pp
                mss_bear_var = True

            bull = False
            mss_bull_var = False
            pH = None
            pL = None
            if not is_na(nPh1) and nPh is not None:
                pH = Piv(nPh.pp, nPh.pi)
            last_break_time = time_low_cond

        # Swing updates (Pine: lin.size() > 0 -> we use last_break_time is not None)
        if (
            last_break_time is not None
            and pH is not None
            and nPh is not None
            and nPh_prev is not None
            and not bull
            and nPh.pp != nPh_prev.pp
            and nPh.pi <= last_break_time
        ):
            pH = Piv(nPh.pp, nPh.pi)

        if (
            last_break_time is not None
            and pL is not None
            and nPl is not None
            and nPl_prev is not None
            and bull
            and nPl.pp != nPl_prev.pp
            and nPl.pi <= last_break_time
        ):
            pL = Piv(nPl.pp, nPl.pi)

        # Reset broken pivots
        if nPh is not None and high[i] > nPh.pp:
            nPh = None
        if nPl is not None and low[i] < nPl.pp:
            nPl = None

        # Store previous for next bar
        nPh_prev = nPh
        nPl_prev = nPl

        # Last levels from temp
        if bos_bull and not is_na(temp_bos_bull_level):
            last_bos_bull_level = temp_bos_bull_level
        if bos_bear and not is_na(temp_bos_bear_level):
            last_bos_bear_level = temp_bos_bear_level
        if mss_bull and not is_na(temp_mss_bull_level):
            last_mss_bull_level = temp_mss_bull_level
        if mss_bear and not is_na(temp_mss_bear_level):
            last_mss_bear_level = temp_mss_bear_level

        # SMA position
        sma_hi = sma_high[i]
        sma_lo = sma_low[i]
        is_above_both = (
            not is_na(sma_hi)
            and not is_na(sma_lo)
            and close[i] > sma_hi
            and close[i] > sma_lo
        )
        is_below_both = (
            not is_na(sma_hi)
            and not is_na(sma_lo)
            and close[i] < sma_hi
            and close[i] < sma_lo
        )
        is_between = (
            not is_na(sma_hi)
            and not is_na(sma_lo)
            and close[i] > sma_lo
            and close[i] < sma_hi
        )

        # Crossover: prev_close < level <= close
        prev_close = close[i - 1] if i > 0 else np.nan
        if signal_type == "BoS":
            buy_level = last_bos_bull_level
            sell_level = last_bos_bear_level
        else:
            buy_level = last_mss_bull_level
            sell_level = last_mss_bear_level

        crossover_buy = (
            not is_na(buy_level)
            and not is_na(prev_close)
            and prev_close < buy_level
            and close[i] >= buy_level
        )
        crossunder_sell = (
            not is_na(sell_level)
            and not is_na(prev_close)
            and prev_close > sell_level
            and close[i] <= sell_level
        )

        buy_condition = crossover_buy and is_above_both
        sell_condition = crossunder_sell and is_below_both

        buy_signal = buy_condition and trend_state != 1
        sell_signal = sell_condition and trend_state != -1

        if buy_signal:
            trend_state = 1
        if sell_signal:
            trend_state = -1
        if is_between:
            trend_state = 0

        buy_signals.append(buy_signal)
        sell_signals.append(sell_signal)

    return buy_signals, sell_signals
