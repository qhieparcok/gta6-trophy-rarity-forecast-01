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
forecasts to get the rate. The fits use a six-hour recency half-life,
because launch-week behaviour changes fast; each trophy's slope is
pulled toward the typical slope of trophies at a similar rate; and the
extrapolation is damped hard, because a slope that held for a few
hours should not be trusted a week out. Quantiles are drawn on the
logit scale, with a spread that grows with the fit's uncertainty, the
horizon, and how much the player base is expected to grow.

One case needs special handling. When every read in the history is
identical, the trophy page has not refreshed for hours — the next
refresh is overdue, and it will be almost pure dilution: a wave of new
players who have earned next to nothing yet. For that case the program
forecasts the rate down by a dilution factor instead of holding it
flat. How much each trophy keeps depends on how easy it is: the
newcomer factor grows with the square of the rate, so the rarest
trophies are diluted nearly to the bare player-count ratio (the
documented first refresh took tracked players from 638 to 3,868),
while the easiest ones keep a visible share. The platinum trophy is
the exception in the other direction: the trophy every tracked player
already holds stays at the top.

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
example, from 0.63% to a median near 0.12%, with the 100% trophy
unchanged. That is the whole point of the dilution branch: a flat
history is not a stable rate, it is a page waiting to refresh.
