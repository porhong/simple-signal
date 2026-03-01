"""
Align structure TF pivots and HTF close/time to chart TF bars.
Semantics: for each chart bar time t, use the last closed structure bar at or before t
for pivots, and that bar's previous structure bar for htfClose/htfTime (Pine close[1], time[1]).
"""
import numpy as np

from pine_logic import compute_structure_pivots


def align_structure_to_chart(
    chart_time: np.ndarray,
    structure_time: np.ndarray,
    structure_high: np.ndarray,
    structure_low: np.ndarray,
    structure_close: np.ndarray,
    rl_bars: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute structure pivots and align to chart bars. All inputs are oldest-first.

    Returns arrays of length len(chart_time):
      phPs, phBi, plPs, plBi, htf_close, htf_time
    """
    phPs_s, phBi_s, plPs_s, plBi_s = compute_structure_pivots(
        structure_high, structure_low, structure_time, rl_bars
    )
    n_chart = len(chart_time)
    n_struct = len(structure_time)

    phPs = np.full(n_chart, np.nan)
    phBi = np.full(n_chart, np.nan)
    plPs = np.full(n_chart, np.nan)
    plBi = np.full(n_chart, np.nan)
    htf_close = np.full(n_chart, np.nan)
    htf_time = np.full(n_chart, np.nan)

    # For each chart bar time t, find largest structure bar index j with structure_time[j] <= t
    struct_t = structure_time
    for i in range(n_chart):
        t = chart_time[i]
        # structure bars are oldest-first; find last (largest index) with time <= t
        j = np.searchsorted(struct_t, t, side="right") - 1
        if j < 0:
            continue
        if j >= n_struct:
            j = n_struct - 1
        phPs[i] = phPs_s[j]
        phBi[i] = phBi_s[j]
        plPs[i] = plPs_s[j]
        plBi[i] = plBi_s[j]
        # Pine: htfClose, htfTime = close[1], time[1] on structure = previous structure bar
        if j > 0:
            htf_close[i] = structure_close[j - 1]
            htf_time[i] = structure_time[j - 1]
        else:
            htf_close[i] = structure_close[0]
            htf_time[i] = structure_time[0]

    return phPs, phBi, plPs, plBi, htf_close, htf_time
