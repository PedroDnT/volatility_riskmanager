Got it. Here’s a tight, actionable plan to make your system less conservative (and more profitable) while staying disciplined. I’ll point to where to change code, give code snippets, and include a checklist to verify your GARCH (“CARCH”) math.

⸻

0) What you’ll change (quick map)
	•	Risk per trade: add dynamic risk (2% → 2–4% by regime).
	•	Stops/targets: widen SL a bit; push TP further; add ATR trailing stop.
	•	Scale-outs: partial profit at R multiples.
	•	Volatility source: blend HAR + ATR + GARCH with outlier clamp.
	•	Portfolio layer: correlation-aware risk cap.
	•	GARCH sanity checks: stationarity, returns, scaling, horizon, sample size.

⸻

1) Settings – add knobs (settings.toml)

Add a new section so you can tune without code changes:

[risk]
base_target_pct = 0.025         # was 0.02; start 2.5%
min_target_pct = 0.015
max_target_pct = 0.040
use_dynamic = true

[stops]
# baseline multipliers by leverage *before* regime multipliers
# (slightly wider SL, higher TP)
k_sl_lev20 = 1.0
k_sl_lev15 = 1.2
k_sl_lev10 = 1.5
k_sl_low   = 1.8

m_tp_lev20 = 2.6
m_tp_lev15 = 3.0
m_tp_lev10 = 3.5
m_tp_low   = 4.0

# trailing & scale-out
atr_trail_mult_initial = 2.0
atr_trail_mult_late    = 1.5
scaleout_r1 = 1.5       # take partial at 1.5R
scaleout_r2 = 3.0       # take more at 3.0R
scaleout_frac1 = 0.4    # 40% at R1
scaleout_frac2 = 0.3    # 30% at R2
leave_runner_frac = 0.3 # 30% trails until stop

[vol]
blend_w_garch = 0.30
blend_w_har   = 0.40
blend_w_atr   = 0.30
garch_har_outlier_ratio = 2.0    # if garch > 2x har → downweight GARCH
horizon_hours = 4                # keep consistent with your timeframe

[portfolio]
corr_lookback_days = 60
corr_threshold = 0.7
cluster_risk_cap_pct = 0.5       # max fraction of total risk per highly-correlated cluster


⸻

2) Volatility blending & outlier clamp

File: garch_vol_triggers.py

Add a small utility that turns annualized vols into horizon vols and blends them:

import numpy as np

HOURS_PER_YEAR = 365 * 24

def _ann_to_horizon_sigma(sig_ann: float, horizon_hours: int) -> float:
    # annualized stdev → horizon stdev (sqrt rule)
    return float(sig_ann) * np.sqrt(horizon_hours / HOURS_PER_YEAR)

def blended_sigma_h(sigma_ann_garch, sigma_ann_har, atr_abs, price, cfg):
    # Convert HAR/GARCH annualized to horizon
    sigH_garch = _ann_to_horizon_sigma(sigma_ann_garch, cfg.vol.horizon_hours)
    sigH_har   = _ann_to_horizon_sigma(sigma_ann_har,   cfg.vol.horizon_hours)

    # ATR as % converted to absolute horizon move (keep simple: ATR is already horizon-like)
    # We’ll express ATR as abs move; it’s fine to blend as absolute sigmas:
    sigH_atr = atr_abs

    # Outlier clamp: if GARCH >> HAR, shrink GARCH weight
    w_g, w_h, w_a = cfg.vol.blend_w_garch, cfg.vol.blend_w_har, cfg.vol.blend_w_atr
    if sigma_ann_har and sigma_ann_garch and (sigma_ann_garch > cfg.vol.garch_har_outlier_ratio * sigma_ann_har):
        w_g = w_g * 0.3  # reduce GARCH impact if it spikes
        # renormalize weights
        s = w_g + w_h + w_a
        w_g, w_h, w_a = w_g/s, w_h/s, w_a/s

    # Final blended horizon sigma (absolute)
    sigH_blend = w_g*sigH_garch + w_h*sigH_har + w_a*sigH_atr
    return sigH_blend

Use this blended_sigma_h(...) where you currently pick a single model. If the advanced models fail, fall back to sigH_blend = atr_abs.

⸻

3) Dynamic risk by regime (trend/breakout filter)

File: position_risk_manager.py (or wherever you assemble per-symbol analysis)

Add a simple regime score (works on 4h):
	•	Momentum: EMA(20) > EMA(50) → +1, else 0
	•	Breakout: Close > Donchian(20) high (long) or < low (short) → +1
	•	Trend strength: ADX(14) > 20 → +1

Then map to a multiplier: 0.8, 1.0, 1.2, 1.4 for scores 0..3. Clamp to [min_target_pct, max_target_pct].

def risk_target_pct_dynamic(base, min_p, max_p, score):
    mult_map = {0:0.8, 1:1.0, 2:1.2, 3:1.4}
    rt = base * mult_map.get(score, 1.0)
    return float(np.clip(rt, min_p, max_p))

Use this risk_target_pct in your size formula:

optimal_size = (risk_target_pct * notional_or_equity) / SL_distance

(Keep your existing convention; if you risk % of position notional, apply it consistently.)

⸻

4) Wider SL, farther TP, and a real trailing stop

File: garch_vol_triggers.py (in sl_tp_and_size())
	1.	Select baseline k/m by leverage from settings.
	2.	Apply regime multiplier (e.g., if strong trend, allow slightly wider SL and higher TP):
	•	k_sl_eff = k_sl_base * (1.0 + 0.1*score)
	•	m_tp_eff = m_tp_base * (1.0 + 0.2*score)
	3.	Compute SL/TP distances using blended horizon sigma:

SL_distance_abs = k_sl_eff * sigmaH_blend
TP_distance_abs = m_tp_eff * sigmaH_blend

(If you previously multiplied by price, keep consistent: if sigmaH_blend is an absolute move, do not multiply by price again.)
	4.	ATR trailing stop helper:

def compute_trailing_stop(entry, direction, atr, cfg, r_unrealized):
    # tighten trail after larger R
    trail_mult = cfg.stops.atr_trail_mult_late if r_unrealized >= 2.0 else cfg.stops.atr_trail_mult_initial
    if direction == "long":
        return max(entry - atr * trail_mult, 0.0)
    else:
        return entry + atr * trail_mult

Call this during reporting to propose a trailing stop once unrealized R ≥ 1.0.

⸻

5) Partial profit-taking (scale-out ladder)

In the same SL/TP function or reporting stage, compute R unit:

R = SL_distance_abs
TP1 = entry ± scaleout_r1 * R
TP2 = entry ± scaleout_r2 * R

Sign depends on long/short. Recommend:
	•	Close scaleout_frac1 at TP1
	•	Close scaleout_frac2 at TP2
	•	Leave leave_runner_frac with trailing stop

Print these levels in the report so you can execute manually.

⸻

6) Portfolio correlation & cluster cap

File: position_risk_manager.py
	1.	Pull last N days (cfg.portfolio.corr_lookback_days) of 4h returns for all symbols in open positions.
	2.	Compute correlation matrix; build clusters by simple rule: symbols with |ρ| ≥ corr_threshold belong to the same cluster.
	3.	Sum proposed risk in % per cluster; if a cluster exceeds cluster_risk_cap_pct of your total risk budget, proportionally scale down sizes in that cluster.
	4.	Show a line in the report:
	•	“Cluster [BTC, ETH, SOL] risk capped from 6.0% → 4.0% (ρ≥0.7)”

This lets you take a bit more risk in uncorrelated names while keeping total portfolio risk sane.

⸻

7) GARCH (“CARCH”) sanity & correctness checklist

File: garch_vol_triggers.py

Add a validator you call every time you fit/forecast:

def validate_garch_result(returns, res, sigma_ann, horizon_hours):
    issues = []

    # A) Input returns should be log returns, zero-mean-ish
    if np.isnan(returns).any() or np.isinf(returns).any():
        issues.append("NaN/Inf in returns")
    if np.abs(np.mean(returns)) > 5e-3:  # heuristic on 4h log-ret
        issues.append("Large mean in returns; did you use raw prices?")

    # B) Parameter constraints
    params = getattr(res, "params", {})
    omega = params.get("omega", None)
    alpha = params.get("alpha[1]", params.get("alpha", None))
    beta  = params.get("beta[1]",  params.get("beta",  None))
    if omega is not None and omega <= 0: issues.append("omega <= 0")
    if alpha is not None and alpha < 0:  issues.append("alpha < 0")
    if beta  is not None and beta  < 0:  issues.append("beta < 0")
    if alpha is not None and beta is not None and (alpha + beta) >= 1.0:
        issues.append("alpha+beta >= 1 (non-stationary)")

    # C) Horizon scaling sanity (annualized → horizon)
    sigH = _ann_to_horizon_sigma(sigma_ann, horizon_hours)
    if (sigH <= 0) or (sigH > 0.50):  # 50% move over 4h is extreme
        issues.append(f"Horizon sigma out of range: {sigH:.3f}")

    # D) Sample size
    if len(returns) < 500:
        issues.append("Too few points (<500) for stable GARCH fit")

    return issues

Also check these implementation details:
	•	Returns: use log(close).diff() (not raw % or prices).
	•	Scaling: if your GARCH library returns daily sigma, don’t re-annualize twice. Standardize: decide that all sigmas in your code are annualized until the last step, then convert to horizon with sqrt(h).
	•	Horizon: use the same horizon_hours everywhere.
	•	Error handling: if validate_garch_result() returns issues or the model fails, fallback to HAR/ATR.
	•	(If you actually meant Component-GARCH / CGARCH): confirm the model type in your code. For CGARCH you should see separate long-run and short-run components; if not, you’re using vanilla GARCH(1,1). If you do want CGARCH, add a new function (e.g., cgarch_sigma_ann_and_sigma_H) and keep the same validation (stationarity, horizon scaling), then plug it into the blender just like GARCH.

⸻

8) Wire-up changes in your pipeline
	•	garch_vol_triggers.py
	•	Add blended_sigma_h, validate_garch_result, compute_trailing_stop.
	•	Modify sl_tp_and_size(...) to use:
	1.	sigma_ann_garch, sigma_ann_har, atr_abs
	2.	sigmaH_blend = blended_sigma_h(...)
	3.	new k_sl_eff, m_tp_eff
	4.	size from dynamic risk_target_pct
	5.	compute TP1/TP2 and trail suggestion
	•	position_risk_manager.py
	•	Add regime scoring, dynamic risk target, and print them.
	•	After per-position proposals, run portfolio correlation, scale down sizes, and annotate the report.
	•	atr_sl_gpt.py
	•	Ensure ATR calculation returns absolute ATR on the same timeframe as entries (e.g., 4h).
	•	Expose both ATR absolute and ATR% of price (for display).
	•	get_position.py
	•	No logic change; ensure leverage, notional, entry side are available for SL/TP math.

⸻

9) Output/reporting (make the behavior visible)

For each position, add lines like:

Regime score: 3 (EMA20>EMA50, breakout, ADX>20)
Risk target: 3.5% (base 2.5% × 1.4)
Vol blend (H=4h): 0.0073 abs | comp: GARCH 0.30 / HAR 0.40 / ATR 0.30
SL k: 1.5 → SL dist: 1.09% | TP m: 3.5 → TP dist: 2.54% | R:R ≈ 2.33
Scale-outs: 40% @ 1.5R, 30% @ 3.0R, 30% trailing (2.0→1.5×ATR)
GARCH checks: OK (α+β=0.92, sample=1200, horizon σ=0.9%)
Portfolio cap: Cluster[BTC, ETH, SOL] risk cut 6.2%→4.0% (ρ≥0.7)


⸻

10) Quick backtest/safety checks (recommended)
	•	Re-run on last 6–12 months of 4h data for top symbols.
	•	Compare:
	•	Profit factor, max DD, MAR, % stopped-out before 1R, average R per winner.
	•	If stop-outs are still frequent, bump k_sl +0.1; if winners capped too early, raise m_tp or loosen trail.
	•	Save an “old vs new” CSV for transparency.

⸻

Done-in-10 checklist
	•	Add new config keys (risk/stops/vol/portfolio).
	•	Implement blended_sigma_h() and swap into SL/TP path.
	•	Add regime score → dynamic risk_target_pct.
	•	Update leverage table (wider k_sl, higher m_tp), apply regime multipliers.
	•	Implement TP ladder and ATR trailing.
	•	Add GARCH validator; fallback to HAR/ATR if issues.
	•	Add correlation cap at portfolio level.
	•	Enhance report with all new signals.
	•	Backtest & tune (small increments).

If you want, paste your current sl_tp_and_size() and I’ll mark exactly what to change line-by-line.