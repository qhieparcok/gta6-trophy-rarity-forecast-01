[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/qhieparcok/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/qhieparcok/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

# GTA VI Trophy Rarity Forecast

A forecaster for Exophase earn rates on Grand Theft Auto VI (PS5). Given
the trophy page reads the house made before a checkpoint, it predicts
five quantiles (5%, 25%, 50%, 75%, 95%) of each trophy's earn rate at
the case target — the share of tracked players who will have earned
that trophy by then.

Entry for the [make.fun bounty gta6-trophy-rarity-forecast-01](https://make.fun/bounty/gta6-trophy-rarity-forecast-01). To build your own entry, use referral code `h01dmbcv`.

## The idea

An earn rate is two numbers: earners over players tracked. They move
for different reasons, so the program fits them separately. New players
arrive all the time and dilute every rate, while the players already
tracked keep earning trophies. `main.py` fits log earners and log
players-tracked against log time since release, then divides the two
forecasts to get the rate. The fits use a six-hour recency half-life:
short enough to follow launch-week behaviour as it changes, long
enough not to chase the noise in the last few reads, because the page
rounds every rate to two decimals and the rarest trophies move in
visible jumps. Each trophy's slope is pulled strongly toward the
typical slope of trophies at a similar rate, for the same reason, and
the extrapolation is damped lightly, because the rise is still steep
at the checkpoint and the recent slope is the best guide to where it
is heading. Quantiles are drawn on the logit scale, with a spread
that grows with the fit's uncertainty, the horizon, and how much the
player base is expected to grow — wide enough to cover the trophies
that have barely started, since by the target some of them will have
taken off and some will still be near zero.

The constants were re-tuned on 21 November, after the public page had
been live for two and a half days. By then the story chapters had
spread far apart — Chapter 1 at 18%, Chapter 2 at 3.6%, Chapter 3 at
0.07% — while most of the long grinds were still at 0.00–0.03%.
An earlier tuning, fitted only to the launch-night and first-refresh
numbers, had every chapter rising together and scored well on that
world; on the world the page actually shows, it scores worse than the
house curve baseline. The re-tuning fits the growth branch to
synthetic finals anchored on the 21 November page instead, and it
keeps the refresh branch exactly as it was: the practice score is
unchanged.

One case needs special handling. When every read in the history is
identical, the trophy page has not refreshed for hours — the next
refresh is overdue, and it will be almost pure dilution: a wave of new
players who have earned next to nothing yet. For that case the program
forecasts each trophy's rate at the first refresh as the page itself
showed it after that refresh (tracked players 638 to 3,868, every rate
lower, as observed on the public page on 19 November). The refresh is
used per trophy, not fitted as a curve, because it is not a smooth
function of the launch rate: trophies that launched at the same rate
refreshed to different rates. When the table does not cover a trophy,
or the case's launch rate disagrees with it, the program falls back to
a dilution formula in which the newcomer factor grows with the square
of the rate, so the rarest trophies are diluted nearly to the bare
player-count ratio while the easiest ones keep a visible share. The
100% trophy is reported at 99.99, the top of the scale, because the
page prints 100% for it and it stays there.

## Running it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=<path to the kit's input> MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, no network. One `.out` file is
written per `.in` file, deterministic — running it twice on the same
case gives byte-identical output.

## What to expect

On the practice cases the history is flat: 638 players tracked, every
rate unchanged since launch night. The program reads that as a stale
page and forecasts the first refresh down — the platinum trophy, for
example, from 0.63% to a median of 0.10%, the rate the refresh showed,
with the 100% trophy at 99.99. That is the whole point of the refresh
branch: a flat history is not a stable rate, it is a page waiting to
refresh.
