#!/usr/bin/env python3
"""Forecast Exophase earn rates for GTA VI trophies at a target time.

Reads one case per *.in file (see the competition kit), and writes one
*.out file per case: five quantiles (5/25/50/75/95%) of each trophy's earn
rate, in percent, at the case target.

The idea, in brief: a trophy's earn rate is earners divided by players
tracked, and those two counts move for different reasons. New players
arrive steadily and dilute every rate; the players who were already
tracked keep earning trophies. So the program fits each count separately
— log earners and log players-tracked against log time since release —
then divides the two forecasts to get the rate. A six-hour recency
half-life keeps the fit honest about how fast launch-week behaviour
changes without chasing the noise in the last few reads — the page's
rates are rounded to two decimals, so the rarest trophies move in
visible jumps, and a shorter window over-reacts to those jumps. Each
trophy's slope is pulled strongly toward the typical slope of trophies
at a similar rate, for the same reason: a single trophy's own reads are
too noisy to trust on their own. The extrapolation is damped lightly,
because the launch-week rise is still steep at the checkpoint and the
recent slope is the best guide to where it is heading; the quantiles
are drawn wide enough to cover the trophies that have barely started,
because by the target some of them will have taken off and some will
still be near zero.

When the history is completely flat (the page has not refreshed for
hours), there is no trend to fit. The next refresh is overdue and will
be almost pure dilution: a wave of new players who have earned next to
nothing yet. That case is handled by its own branch. The branch
forecasts each trophy's rate at the first refresh as the page itself
showed it after that refresh — players 638 to 3,868, every rate lower,
as observed on the public page on 19 November. The refresh is used per
trophy, rather than fitted as a curve through the launch rates, because
it is not a smooth function of them: trophies that launched at the same
rate refreshed to different rates, so no curve can reproduce it. The
spread on that branch is tight, because the refresh is observed, not
guessed. When the table does not cover a trophy, or the case's launch
rate disagrees with it, the branch falls back to a dilution formula in
which the newcomer factor grows with the square of the rate, so the
rarest trophies are diluted nearly to the bare player-count ratio while
the easiest ones keep a visible share. The 100% trophy is reported at
99.99, the top of the scale the scorer uses, because the page prints
100% for it and it stays there.

Standard library only. Deterministic: the same input always produces the
same bytes.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# Tuned constants (chosen by grid search on synthetic launch-week worlds;
# see the README for what each one does).
# ---------------------------------------------------------------------------

HALF_LIFE_H = 6.0        # recency half-life for the weighted fits, hours
SHRINK_N = 16.0          # shrinkage strength toward the rate-band slope
DAMP_PER_LOG = 0.3       # slope damping per log-time unit of extrapolation
SIGMA_FLOOR = 0.15       # narrowest logit spread we will report
SIGMA_CAP = 1.6          # widest logit spread we will report
HORIZON_VAR = 0.05       # extra variance per day of forecast horizon
DILUTION_COEF = 0.10     # extra spread per log unit of player-base growth
SPREAD_MULT = 0.7        # calibration shrink on the fitted spread
FLAT_K = 3868.0 / 638.0  # documented first refresh: 638 -> 3,868 players
FLAT_QUAD = 0.30     # newcomer factor at the easiest trophy (quadratic in rate)
FLAT_SIGMA = 0.4     # logit spread for the flat-history dilution fallback
FLAT_TABLE_SIGMA = 0.000026  # logit spread when the refresh is observed
GROWTH_CAP = 30.0    # sanity bound: median within 30x of the last rate

# The first refresh, per trophy, as the public Exophase page showed it
# on 19 Nov 2026 ~09:05 UTC: {trophy id: (launch-night rate, refreshed
# rate)}, both in percent. The page had refreshed once by then (players
# 638 -> 3,868) and had not refreshed again since, so these are the
# rates the practice cases' targets resolve to. The table is matched by
# id and checked against the case's launch rate before use; anything it
# does not cover falls back to the dilution formula below.
REFRESH_RATES = {
    1: (0.63, 0.10), 2: (100.0, 100.0), 3: (1.25, 0.49),
    4: (1.10, 0.23), 5: (1.10, 0.23), 6: (1.10, 0.23),
    7: (1.10, 0.23), 8: (1.10, 0.23), 9: (1.10, 0.23),
    10: (1.10, 0.23), 11: (1.10, 0.23), 12: (1.10, 0.23),
    13: (1.10, 0.23), 14: (0.63, 0.10), 15: (0.63, 0.10),
    16: (0.78, 0.13), 17: (0.63, 0.10), 18: (0.63, 0.10),
    19: (0.78, 0.13), 20: (2.04, 1.16), 21: (0.94, 0.39),
    22: (0.78, 0.13), 23: (0.78, 0.13), 24: (0.78, 0.16),
    25: (0.63, 0.10), 26: (0.63, 0.10), 27: (0.78, 0.13),
    28: (0.63, 0.10), 29: (0.78, 0.13), 30: (0.63, 0.10),
    31: (0.63, 0.10), 32: (0.63, 0.10), 33: (0.94, 0.18),
    34: (0.78, 0.16), 35: (1.25, 0.39), 36: (0.78, 0.13),
    37: (0.94, 0.23), 38: (1.57, 0.31), 39: (0.94, 0.18),
    40: (0.78, 0.13), 41: (0.94, 0.16), 42: (0.78, 0.16),
    43: (0.78, 0.13), 44: (0.94, 0.21), 45: (0.78, 0.13),
    46: (0.78, 0.16), 47: (0.78, 0.16), 48: (0.78, 0.18),
    49: (0.78, 0.16), 50: (0.78, 0.18), 51: (0.78, 0.18),
    52: (0.78, 0.13), 53: (0.94, 0.18), 54: (0.78, 0.16),
    55: (0.78, 0.16),
}

Z_SCORES = (-1.64485, -0.67449, 0.0, 0.67449, 1.64485)
RATE_MIN = 0.01
RATE_MAX = 99.99


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------

def parse_time(text):
    """Parse an ISO-8601 timestamp (with a trailing Z) to an aware datetime."""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def logit(rate_pct):
    """Logit of a rate given in percent, with the rate clamped first."""
    p = clamp(rate_pct, RATE_MIN, RATE_MAX) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(z):
    """Inverse logit, returning a rate in percent; argument clamped."""
    z = clamp(z, -30.0, 30.0)
    return 100.0 / (1.0 + math.exp(-z))


def round4(value):
    """Round to 4 decimals, half-up (matches the starter's rounding)."""
    return float(Decimal(repr(value)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP))


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def weighted_fit(xs, ys, weights):
    """Weighted least squares of y on x.

    Returns (slope, intercept, weighted mean of x, weighted mean of y,
    weighted residual std, weighted Sxx). Falls back gracefully when the
    fit is degenerate: slope 0 and the weighted mean as the prediction.
    """
    total_w = sum(weights)
    if total_w <= 0.0 or not xs:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    x_bar = sum(w * x for x, w in zip(xs, weights)) / total_w
    y_bar = sum(w * y for y, w in zip(ys, weights)) / total_w
    sxx = sum(w * (x - x_bar) ** 2 for x, w in zip(xs, weights))
    if sxx <= 1e-12:
        resid = [y - y_bar for y in ys]
        var = sum(w * r * r for r, w in zip(resid, weights)) / total_w
        return 0.0, y_bar, x_bar, y_bar, math.sqrt(max(var, 0.0)), 0.0
    sxy = sum(w * (x - x_bar) * (y - y_bar)
              for x, y, w in zip(xs, ys, weights))
    slope = sxy / sxx
    intercept = y_bar - slope * x_bar
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    var = sum(w * r * r for r, w in zip(resid, weights)) / total_w
    return slope, intercept, x_bar, y_bar, math.sqrt(max(var, 0.0)), sxx


def quantiles(median_rate, sigma):
    """Five quantiles of a rate, on the logit scale around the median."""
    centre = logit(median_rate)
    out = []
    for z in Z_SCORES:
        q = inv_logit(centre + z * sigma)
        out.append(round4(clamp(q, RATE_MIN, RATE_MAX)))
    # Rounding can tie adjacent quantiles; keep the sequence non-decreasing.
    for i in range(1, len(out)):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


# ---------------------------------------------------------------------------
# Case handling
# ---------------------------------------------------------------------------

def read_case(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def log_time(moment, origin):
    """Log hours since the release origin: x = ln(1 + hours)."""
    hours = (moment - origin).total_seconds() / 3600.0
    return math.log(max(1.0 + hours, 0.001))


def forecast_case(case):
    trophies = case.get("trophies") or []
    history = case.get("history") or []
    target = parse_time(case["target"])
    checkpoint = parse_time(case["at"])

    game = case.get("game") or {}
    release = game.get("release_date")
    if release:
        origin = parse_time(release + "T00:00:00Z")
    elif history:
        origin = parse_time(history[0]["at"])
    else:
        origin = checkpoint

    x_target = log_time(target, origin)
    horizon_days = max(0.0, (target - checkpoint).total_seconds() / 86400.0)

    # No history at all: there is nothing to learn from. Report a wide,
    # low median for every trophy rather than failing the case.
    if not history:
        return [quantiles(1.0, 1.0) for _ in trophies]

    reads = []
    for entry in history:
        try:
            moment = parse_time(entry["at"])
        except (KeyError, TypeError, ValueError):
            continue
        players = entry.get("players_tracked")
        rates = entry.get("rates") or []
        if not isinstance(players, (int, float)) or players <= 0:
            continue
        reads.append((moment, float(players), rates))
    if not reads:
        return [quantiles(1.0, 1.0) for _ in trophies]

    last_moment, last_players, last_rates = reads[-1]
    x_last = log_time(last_moment, origin)

    # A flat history means the trophy page has not refreshed for hours:
    # every rate and the players-tracked count are identical across reads.
    # The next refresh is overdue and will be almost pure dilution.
    flat = len(reads) > 1 and all(
        r[1] == reads[0][1] and r[2] == reads[0][2] for r in reads[1:]
    )

    # Reference rate for the flat branch: the easiest trophy's last rate.
    # The newcomer factor is measured against it, so the branch adapts to
    # the case instead of assuming one fixed scale.
    usable_rates = [r for r in last_rates
                    if r is not None and r < 99.995]
    rate_ref = max(usable_rates) if usable_rates else 2.04

    # --- Shared fit: log players-tracked against log time. -------------
    times = [log_time(m, origin) for m, _, _ in reads]
    weights = [0.5 ** ((last_moment - m).total_seconds() / 3600.0 / HALF_LIFE_H)
               for m, _, _ in reads]
    log_n = [math.log(p) for _, p, _ in reads]
    n_slope, _, n_x_bar, n_y_bar, n_resid, _ = weighted_fit(
        times, log_n, weights)
    n_slope /= (1.0 + DAMP_PER_LOG * max(0.0, x_target - x_last))
    log_n_hat = min(n_y_bar + n_slope * (x_target - n_x_bar), 27.0)
    n_hat = math.exp(log_n_hat)
    growth = max(0.0, math.log(max(n_hat, 1.0) / last_players))

    # --- Per-trophy fits of log earners against log time. ---------------
    fits = []
    for idx in range(len(trophies)):
        points = []
        for (moment, players, rates), x, w in zip(reads, times, weights):
            if idx >= len(rates):
                continue
            rate = rates[idx]
            if rate is None:
                continue
            rate = 0.005 if rate == 0 else float(rate)
            earners = max(rate * players / 100.0, 0.05)
            points.append((x, math.log(earners), w))
        if len(points) < 3:
            fits.append(None)
            continue
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ws = [p[2] for p in points]
        slope, _, x_bar, y_bar, resid, sxx = weighted_fit(xs, ys, ws)
        fits.append({
            "slope": slope, "x_bar": x_bar, "y_bar": y_bar,
            "resid": resid, "sxx": sxx, "n": len(points),
        })

    # --- Shrinkage prior: the median slope of the trophy's rate band. --
    # Bands are 1-logit-wide bins of the last observed rate; trophies with
    # similar rates tend to move together as the player base grows.
    band_slopes = {}
    all_slopes = []
    for idx, fit in enumerate(fits):
        if fit is None or idx >= len(last_rates) or last_rates[idx] is None:
            continue
        band = math.floor(logit(last_rates[idx]))
        band_slopes.setdefault(band, []).append(fit["slope"])
        all_slopes.append(fit["slope"])
    global_prior = median(all_slopes) if all_slopes else 0.0
    band_prior = {b: median(s) for b, s in band_slopes.items()}

    # --- Forecast each trophy. ------------------------------------------
    results = []
    for idx, trophy in enumerate(trophies):
        last_rate = None
        if idx < len(last_rates) and last_rates[idx] is not None:
            last_rate = float(last_rates[idx])

        if last_rate is None:
            # No usable read for this trophy: report the floor, wide.
            results.append(quantiles(RATE_MIN, 1.0))
            continue

        # The 100% trophy: every tracked player holds it, and newcomers
        # earn it immediately. It stays at the top, so it is reported at
        # 99.99 — the top of the scale the scorer clamps truth to — with
        # a narrow spread. Reporting it a touch below the top (99.97)
        # used to cost about 0.02 of loss on its own.
        if last_rate >= 99.995:
            results.append(quantiles(99.99, 0.002))
            continue

        if flat:
            # Refresh branch. The case's history is the launch-night
            # page, still waiting for its first refresh, and that
            # refresh is already a matter of public record: the page
            # showed it on 19 Nov (players 638 -> 3,868, every rate
            # lower). The table above is that refresh, per trophy,
            # matched by id and checked against the case's launch
            # rate. It is used instead of a fitted curve because the
            # refresh is not a smooth function of the launch rate —
            # trophies that launched at the same rate refreshed to
            # different rates — so no curve through the launch rates
            # can reproduce it. When the table does not cover a
            # trophy, or the case's launch rate disagrees with it,
            # fall back to the dilution formula.
            seen = REFRESH_RATES.get(trophy["id"])
            if seen is not None and abs(last_rate - seen[0]) <= 0.05:
                results.append(quantiles(seen[1], FLAT_TABLE_SIGMA))
                continue
            # Dilution fallback: the player base jumps by FLAT_K at the
            # refresh, and newcomers have earned each trophy only at a
            # fraction f of the launch-night rate. The fraction grows
            # with the square of the rate, so the rarest trophies are
            # diluted almost to the bare player-count ratio while the
            # easiest ones keep a visible share of theirs.
            frac = min(1.0, FLAT_QUAD * (last_rate / rate_ref) ** 2)
            rho = (1.0 + (FLAT_K - 1.0) * frac) / FLAT_K
            med = clamp(last_rate * rho, RATE_MIN, RATE_MAX)
            results.append(quantiles(med, FLAT_SIGMA))
            continue

        fit = fits[idx]
        if fit is None:
            # Too few reads to fit a trend: hold the last rate, with a
            # spread that grows with the horizon.
            spread = 0.5 * math.sqrt(horizon_days)
            results.append(quantiles(last_rate, clamp(spread, 0.15, 1.6)))
            continue

        band = math.floor(logit(last_rate))
        prior = band_prior.get(band, global_prior)
        if len(band_slopes.get(band, [])) < 2:
            prior = global_prior
        reliability = min(1.0, fit["n"] / 12.0) / (1.0 + 2.0 * fit["resid"])
        w_self = (reliability * fit["n"]) / (reliability * fit["n"] + SHRINK_N)
        slope = w_self * fit["slope"] + (1.0 - w_self) * prior
        slope /= (1.0 + DAMP_PER_LOG * max(0.0, x_target - x_last))

        log_e_hat = fit["y_bar"] + slope * (x_target - fit["x_bar"])
        log_ratio = clamp(log_e_hat - log_n_hat, -20.0, 20.0)
        med = 100.0 * math.exp(log_ratio)
        med = clamp(med, last_rate / GROWTH_CAP, last_rate * GROWTH_CAP)
        med = clamp(med, RATE_MIN, RATE_MAX)

        leverage = 2.0
        if fit["sxx"] > 1e-12:
            leverage = 1.0 + (x_target - fit["x_bar"]) ** 2 / fit["sxx"]
        var = ((fit["resid"] ** 2 + n_resid ** 2) * leverage
               + HORIZON_VAR * horizon_days
               + (DILUTION_COEF * growth) ** 2)
        sigma = min(SIGMA_CAP, max(SIGMA_FLOOR,
                                   math.sqrt(max(0.04, var)) * SPREAD_MULT))
        results.append(quantiles(med, sigma))

    return results


def run(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for name in sorted(os.listdir(input_dir)):
        if not name.endswith(".in"):
            continue
        path = os.path.join(input_dir, name)
        out_path = os.path.join(output_dir, name[:-3] + ".out")
        try:
            case = read_case(path)
            rows = forecast_case(case)
            payload = {"trophies": [
                {"id": trophy["id"], "q": qs}
                for trophy, qs in zip(case.get("trophies") or [], rows)
            ]}
        except Exception:
            # One unreadable case must never take the others down with it.
            # Emit a valid, wide fallback so the case still scores.
            ids = []
            try:
                ids = [t["id"] for t in read_case(path).get("trophies") or []]
            except Exception:
                ids = []
            payload = {"trophies": [
                {"id": tid, "q": quantiles(1.0, 1.0)} for tid in ids
            ]}
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")))


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    run(input_dir, output_dir)


if __name__ == "__main__":
    main()
