# Gaffer

A free FPL decision engine for one manager and one mini-league.

It reads your squad, your rivals' squads, Solio Analytics' public projection feed
and the FPL API, then solves five gameweeks at once — transfers, captain, chips,
and whether a hit pays. Output is a single page you open on your phone.

Runs on GitHub Actions and GitHub Pages. Cost: nothing.

## Setup from a phone

You do not need a computer. Everything below works in Safari or Chrome on a
phone, using GitHub Codespaces for the one terminal command.

1. On **github.com**, sign in and create a new **public** repo called
   `fpl-gaffer`. Do not add a README.
2. **Add file → Upload files.** Pick `fpl-gaffer.tar.gz` from your Files app.
   Commit it.
3. Open **github.com/codespaces**, create a codespace on the repo. It is a full
   terminal in the browser.
4. Paste this one command:

   ```
   tar xzf fpl-gaffer.tar.gz --strip-components=1 && rm fpl-gaffer.tar.gz \
     && git add -A && git commit -m "gaffer" && git push
   ```

5. **Settings → Actions → General → Workflow permissions → Read and write.**
6. **Settings → Pages → Deploy from a branch → `main`, folder `/docs`.**
7. **Actions → gaffer → Run workflow.** The first run trains the models, so give
   it about five minutes.

Your page: `https://<you>.github.io/fpl-gaffer/`. Add it to your home screen.

Everything after this — editing `config.yaml`, triggering a run, reading the
plan — is doable from the GitHub mobile app or the website.

The trained models are not in the tarball, because they are binary files and
phones are bad at those. The workflow notices they are missing and trains them
on its first run, then commits them.

## Setup

Check it works first:

```
pip install -r requirements.txt
python preflight.py
```

Then either run `./setup.sh` — which needs the GitHub CLI and a one-time
`gh auth login`, and does everything below by itself — or do it by hand:

1. Push this folder to GitHub. Make it **public** (free Actions minutes).
2. Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/docs`.
3. Settings → Actions → General → Workflow permissions: *Read and write*.
4. Actions tab → `gaffer` → *Run workflow*.

Your page appears at `https://<you>.github.io/<repo>/`. The first Pages build
takes a couple of minutes.

## Every week

1. Make your transfers in the FPL app.
2. **Update `current_squad` in `config.yaml`** and commit. FPL's public API hides
   transfers made for the upcoming deadline, so this is the one thing the tool
   cannot work out for itself.
3. The job wakes on its own and does a full run on deadline day. To force one,
   Actions → Run workflow, and set your free transfers there.
4. Open the page on your phone.

## Weekly rhythm

Deadlines only ever land on a Wednesday, Friday or Saturday. The workflow wakes
on those three mornings, checks the real deadline date from the API, and exits in
about five seconds unless the deadline is *today*. So in practice it does one
full run per gameweek, on deadline morning.

| When | What happens |
|---|---|
| Wed / Fri / Sat 06:00 UTC | Wakes, checks the calendar, exits unless today is deadline day |
| Deadline day | Full solve, rewrites the page, commits it |
| Any time | Actions → Run workflow (set free transfers there), or run it locally |

Each run rewrites `docs/index.html` and `docs/plan.json` and commits them, so the
git history is a record of what the model thought and when — which is how you
find out whether it is any good.

## Telling it your free transfers

You get one a week. Unused ones stack, up to five. A wildcard week spends none of
them. The optimiser models all three rules, but it cannot see how many you are
holding right now — the public API does not expose it.

Set it when you trigger the run:

- Actions → Run workflow → *Free transfers available this week*
- or locally: `python -m gaffer.main --free-transfers 2`
- or `free_transfers:` in `config.yaml` as the fallback

Getting this wrong is the single most common cause of a nonsense plan.

## Planning your own line

`optimise.plan` answers *what should I do*. The planner answers a different
question: *I have decided to do this — does it work, and what does it cost me?*

Most managers already hold a plan in their head. Wildcard after the
international break, Bench Boost on the double. What they lack is something
that checks it against the rules and prices it.

Write it in `config.yaml`:

```yaml
my_plan:
  5:
    out: [Wirtz]
    in:  [Gibbs-White]
  7:
    chip: tc
```

Names, not ids. `chip_plan` is folded in automatically, so a chip locked there
still gets graded even if you never mention it in `my_plan`.

The report then does three things the solver does not.

**It validates.** A plan that sprints past the budget in GW9 is worse than no
plan, because you find out at 19:29 on a Friday. Every rule the game enforces
is checked at the gameweek it breaks — squad shape, the three-per-club limit,
budget, selling prices, chips already spent, the twenty-transfer cap, and the
GW19 expiry on the first set of chips. **All** breaks are reported, not just
the first: you want to know whether it is one mistake or five before you start
fixing.

**It prices the gap.** Your plan against the solver's own line, in points, over
the same horizon. "Bench Boost in GW9 instead of GW7" stops being a matter of
taste and becomes a number.

**It sweeps the chips.** Every free week in the horizon is tried for every chip
you still hold, and the table says where yours sits, where the best week is,
and what moving it is worth. That sweep is exact — every placement evaluated,
none sampled. The limit is the horizon itself: if the right week for a Bench
Boost is GW30 and you are planning five weeks ahead, nothing here can see it,
and the report says so rather than pretending otherwise.

Evaluation continues past a violation so the rest of the plan stays readable.
When that happens the numbers are indicative, and the page tells you.

## The models

`python -m gaffer.learn` trains on 84,577 player-gameweeks from 2023-24, 2024-25
and 2025-26 (vaastav/Fantasy-Premier-League on GitHub, free). Validated with
grouped cross-validation by gameweek so there is no leakage across time.

| Model | Predicts | Score |
|---|---|---|
| minutes | plays 60+ next week | AUC 0.943 |
| price | rises or falls tonight | AUC 0.979 |
| defcon | hits the DefCon threshold | AUC 0.919 |
| ceiling | scores 10+ next week — the captaincy question | AUC 0.848 |
| cleansheet | keeps a clean sheet | AUC 0.829 |
| points | next gameweek's points | MAE 1.003 |
| bonus | bonus points | MAE 0.148 |
| herd | next week's net transfers as a share of owners | MAE 0.045 |
| injury_return | minutes in the week back from an absence | MAE 13.0 min |
| rotation | minutes under fixture congestion | MAE 14.4 min |

Expected points and ceiling rank players differently, and that matters: the
Triple Captain chip only cares about the tail. `ceiling` predicts P(10+ points)
so the armband is chosen on haul probability rather than on an average.

It is wired in three places. `projections.py` predicts it per player per
gameweek — a double gameweek is P(haul in either match), not the second fixture
overwriting the first. `optimise.py` adds it to the Triple Captain term, so the
chip goes to the player who can actually spike; the tilt is small on purpose
(`ceiling_weight`, default 6.0) because a ceiling model that outvoted expected
points would hand the chip to a cheap lottery ticket. And the report names the
tail, including when a *different* player in your eleven has a bigger one —
worth the armband only if you need variance rather than points.

Set `ceiling_weight: 0` to choose the armband on expected points alone.

`injury_return` answers the question a fitness flag does not: he is available,
but does he play 20 minutes or 90? `rotation` keys off rest days between league
fixtures, which is the observable fingerprint of a midweek European tie.

Set pieces are handled in `setpieces.py` as a calculator rather than a model —
the historical dataset has no set-piece order column, so there is nothing to
train on, but FPL publishes `penalties_order`, `direct_freekicks_order` and
`corners_and_indirect_freekicks_order` directly. That is the label everyone else
is trying to predict.

`herd` is the mini-league model. It predicts who the crowd buys next, which is
what turns a differential into a template pick and what moves prices.

The points model beats the naive "he'll score what he's been averaging" baseline
(MAE 1.082) — but only by 7%. That is the honest state of the art on two games of
new-season data, and it is why the projections lean on Solio for the upcoming
gameweek and on the local model only beyond it.

The minutes model is wired into `projections.py` automatically once trained.
Retrain monthly; more data is the only thing that improves it.

## Positional profile

`styles.py` answers where a player does his work, not just how much. Two forwards
on the same expected goals are not the same asset: one shoots from the edge of
the box, the other from six yards, and only the second repeats.

Understat's shot-location data would be ideal, but the site now renders
client-side and no longer ships its JSON in the HTML, so it is not reliably
scrapable. The metrics are derived instead from Opta's ICT components, which FPL
publishes directly and which already encode shot location:

- **shot quality** — expected goals per unit of threat. High means his attempts
  come from inside the box; low means he shoots from distance
- **attacking share** — his slice of his own team's expected goal involvement,
  so you can tell a focal point from a passenger
- threat, creativity and influence per 90, plus xG90, xA90, defensive actions
  per 90 and expected goals conceded per 90

## Elite manager tracking

`elite.py` computes what the world's best managers own, captain and chip. FPL
Focal publishes this, but their page renders client-side with no open endpoint —
and it does not need one. League 314 is the global Overall league, so its top
pages are the best managers in the world and their picks are public.

Elite ownership minus overall ownership is the signal. A player at 74% among the
best and 31% overall is a crowd that has not caught up.

## Every recommendation shows its working

`explain.py` attaches the numbers behind each decision: projected points, start
probability, shot quality, attacking share, defensive actions, set-piece value,
league and pack and elite ownership, and price direction. A solver you cannot
argue with is one you cannot correct.

## Extra data now flowing in

- xG, xA, xGI and per-90 versions, straight from the FPL API
- Expected goals conceded per 90, per player and per team
- Raw defensive actions: clearances, blocks, interceptions, tackles, recoveries —
  which lets the gaffer compute DefCon trigger probability from a Poisson tail
  rather than guessing
- Net transfer flow and ownership per gameweek, historical — the raw material
  for modelling herd behaviour and price movement
- Solio's projections for the upcoming gameweek
- Your mini-league's 42 squads, for effective ownership

## The wildcard

A wildcard is not a transfer, so it does not come out of the transfer model.
`wildcard.py` gives it its own solve, for one reason above all others: the
weekly model's candidate pool is the top hundred and thirty players by
projected points, and a rebuild is decided by the players who are *not* on that
list. Three premiums only fit if four-pound defenders carry them, and the
cheapest player in a top-130 pool costs five and a half.

So the pool is stratified — the best few in every position and price band, plus
the cheapest players in the game outright — which guarantees the enablers exist
before the solver starts arguing about money. Three other differences:

- **The horizon is longer** (`wildcard_horizon`, default eight weeks). You are
  buying a fixture run, not a weekend.
- **Chips you have committed to are known, not decisions.** A Bench Boost in a
  known week is simply a week where the bench pays full price. That removes
  every bilinear term from the model, which is what pays for the bigger pool.
- **Nothing is bought or sold after the draft.** Assuming you will also make
  perfect transfers afterwards flatters every squad by about the same amount
  and hides the differences between them — the only thing this is measuring.

It runs whenever `chip_plan.wc` falls inside the horizon, or on demand:

```
python -m gaffer.main --wildcard 6
```

`wildcard_keep` and `wildcard_ban` in `config.yaml` force players in or out.
Both are the argument, not the override: forcing a pick costs points, and the
report prints what it cost.

Every drafted player comes with the nearest alternative you could have
afforded and the gap between them, over the whole horizon, holding the other
fourteen fixed. A gap near zero is a coin toss — take the player you want to
watch.

The budget is your bank plus the selling value of all fifteen. If the wildcard
is weeks away, that assumes you make no transfers in between; the page says so
rather than hiding it.

## The value of waiting

The optimiser scores every future gameweek with today's projections, so left
alone it always prefers acting immediately. That is wrong for a wildcard: playing
it in Gameweek 3 means betting on fifteen players from two matches of evidence,
while playing it after an international break means knowing who is fit and which
hot streaks were real.

`timing.py` supplies the counterweight — a credit for playing a chip later,
rising with matches played and jumping after an international break. Breaks are
detected from the calendar (a gap of 10+ days between deadlines), not hardcoded.

None of it is measured from data. It is a judgement, exposed as `info_value` in
config rather than buried in an assumption, and `timing.breakeven()` reports how
large it would have to be to change your decision. Argue about that number
instead of the projections.

## Injured and flagged players

Anyone injured, suspended or transferred out is barred from the starting eleven
outright, so the solver decides on its own merits whether they still deserve a
squad slot. The report lists them with a verdict: sell if they do not return
inside the planning horizon, hold if they do.

## Form and real team strength

Two things a season total hides:

- **Form.** FPL's `form` field is points per match over the last 30 days. Against
  the season rate it says whether a player is trending up or down. Weighted by
  `form_weight`.
- **Measured team strength.** Fixture difficulty ratings are a preseason label on
  a five-point scale, and they do not move when a side starts scoring three a
  game. `team_strength()` computes attack and defence from expected goals created
  and conceded, and blends it with the FDR by `strength_weight`. Chelsea's attack
  currently reads 1.56 against a league average of 1.00, and the projections now
  reflect that.

## Defensive modelling

Attacking returns are lumpy. Defensive returns are close to a Poisson process
driven by two numbers — how much a team concedes and how good the opponent's
attack is — which makes them the most forecastable points in the game.

`defence.py` computes, per team per gameweek:

- **expected goals conceded**, from measured expected goals against, shrunk
  toward the league average and then calibrated against Solio's published match
  odds for the teams it covers
- **clean sheet probability** as the Poisson zero
- **concede cost** as the expected value of floor(goals / 2), because FPL charges
  a point per two goals conceded, not half a point per goal
- **defensive contribution probability** as a Poisson tail against the real
  thresholds — 10 actions for defenders, 12 for everyone else

Goalkeepers and defenders are then projected from components rather than from a
scaled points rate: appearance, clean sheet, concede cost, saves, defensive
contribution, expected goals and assists, bonus. Midfielders get the one-point
clean sheet and their defensive contribution added on top.

Validated against Solio's published clean sheet odds: **mean absolute error 5.1
percentage points** across the teams it covers. Arsenal exact, Brentford within
one, Man City within four.

The shrinkage is the part that matters. Two matches of data will cheerfully tell
you a side concedes 0.39 expected goals a game, and an uncalibrated model then
hands out 68% clean sheet odds no bookmaker would offer. The same shrinkage now
applies to attack strength, which had Manchester United at 2.05 times league
average off two games and now reads 1.26.

## Calibration and rotation

Two corrections that matter more than any model change.

**Calibration.** Solio publishes projections for the upcoming gameweek only —
but that is enough. If our numbers run high against theirs on the sixty players
they cover this week, they run high on everyone next week too. `calibrate.py`
fits the median ratio on the overlap and scales everything else by it. The
current correction is **×0.94 on 51 shared players**, which is to say the local
model was running about 6% hot and now does not.

**Rotation.** A projection that assumes ninety minutes is wrong for exactly the
players you most want to captain. The Premier League fixture API knows nothing
about European football, so `european_teams` and `european_weeks` are declared
in config — check the UEFA calendar and keep them current, because a wrong list
is worse than an empty one. Domestic midweek rounds are inferred from the
calendar and hit everybody.

The effect is not cosmetic: Haaland's GW7 projection against Ipswich falls from
14.9 to 12.3 once the Champions League ties either side of it are priced in.

## The minimum-gain threshold

`min_transfer_gain` is the number a transfer must beat before it is recommended.
Set it to 1.5 and the solver stops proposing swaps worth half a point. Wildcard
weeks are exempt, because their moves are free — but on a wildcard some
individual swaps are deliberate downgrades that release money for a bigger
upgrade elsewhere, and the report says so rather than presenting them as good
moves on their own.

## The app

`docs/index.html` is an interactive page. It reads `docs/data.json`, which the
solve writes, and runs entirely in the browser — no framework, no build step, no
CDN. GitHub Pages serves static files, and a dependency that 404s on a Friday
evening is worse than no dependency.

Five views:

- **Team** — your eleven laid out on a pitch by position, captain and flags
  marked, projection on every card. Tap a player to open him in Compare.
- **Wildcard** — the drafted fifteen on a pitch, with a week switcher so you
  can see the line-up in every gameweek of the rebuild rather than only the
  first. Who is sold, who is bought, who survives; the projected run as a bar
  per gameweek with the chip weeks marked; and the closest calls — for each
  drafted player, the nearest alternative you could afford and what taking him
  would cost.
- **Players** — every player in the pool, filterable by position, club, price,
  availability and your own squad, sortable on any column. Tap a row to compare.
- **Compare** — any two players across sixteen metrics, normalised so the longer
  bar is always the better number, plus their projections over the horizon and
  the same numbers as a table.
- **Plan** — the five-week line, chip weeks, and what moving a chip is worth.

The old server-rendered page is still written, as `report.html`. It needs no
JavaScript and is what you fall back to if the app breaks.

### Why the engine got more useful without getting smarter

The solver already computed a twenty-five field card for every player — shot
quality, attacking share, DefCon probability, four kinds of ownership, price
direction. It exported that for the two players in a transfer and threw the
other seven hundred away, which is why the page could only ever show you the
move it had already decided on. `webdata.py` writes all of it. The page is now a
client of the data rather than a rendering of one conclusion.

### Charts

Inline SVG, built in the page. The palette is a validated categorical set —
adjacent-pair colourblind separation and contrast were checked with a script,
not by eye — and both light and dark are selected rather than flipped. Every bar
carries its number, because light-mode aqua sits below 3:1 against the surface
and a label has to carry the value when colour cannot. Every chart has a table
beside it or beneath it.

Labels sit above their bars rather than in a left gutter: a gutter wide enough
for "Defensive actions per 90" leaves no room for the bar on a phone, and
truncating the label loses the thing you most need to read.

## The dials

- `rivalry` (0–1) — how hard to chase differentials. 0 is pure expected points,
  1 ignores expected points to be different. Raise it when you are behind.
- `rival_depth` — how many teams above you count as the pack you are hunting.
- `hit_threshold` — points a hit must gain across the horizon before it is
  recommended.
- `decay` — how much less a gameweek five weeks out counts than this one.
- `solio_weight` — how much to trust Solio over the local model.

## Rules the optimiser encodes

Checked against the official rules page and the 2026/27 change notes.

- Squad of 15 (2/5/5/3), £100.0m budget, max 3 per club, valid formation each week
- **Selling price**: you keep half of any rise, rounded down to £0.1m. Buy at 7.5,
  now worth 7.8, you sell for 7.6. No protection against falls
- **Free transfers**: one a week, stack to a maximum of five, −4 per extra transfer
- **Saved free transfers are retained across a Wildcard or Free Hit week** — they
  do not reset, and they do not gain the usual +1 either
- **Hard cap of 20 transfers** in any single gameweek unless a chip is played
- **Chips**: two sets. Wildcard, Free Hit, Triple Captain, Bench Boost in each half.
  One chip per gameweek. The first set expires at the GW19 deadline, 13:30 GMT on
  Saturday 2 January, and cannot be carried over
- **Defensive contributions**: 2 points at 10 CBIT for defenders, 12 CBIRT for
  midfielders and forwards. Unchanged for 2026/27
- **Deadlines** are 90 minutes before the first kick-off and can move, but never
  within 24 hours of the scheduled time — which is why the job re-reads the
  calendar rather than trusting a fixed cron
- **Prices change at midnight UK time**
- No AFCON this season, so there is no December free-transfer top-up

## Tests

```
python -m pytest tests -q
```

Eighty-four of them, covering the planner, the wildcard drafter, the page they
render, and the ceiling model's wiring. They run on
a synthetic squad — no network, no API, no solver — because the rules they
check are exactly the ones that are expensive to get wrong and impossible to
spot by eye on a Friday evening.

Two workflows run them, and both are needed. `tests.yml` fires on every push
and pull request, so a branch is checked before it is merged. `gaffer.yml`
runs them again immediately before the solve, because the code that matters is
the code on `main` on deadline morning, not the code that passed review a week
earlier.

### A note on the other eight models

`minutes` and `ceiling` are loaded. The remaining eight — `price`, `defcon`,
`cleansheet`, `bonus`, `herd`, `injury_return`, `rotation`, `points` — are
trained, scored and committed, and still read by nothing. They are not wired in
yet, and the README should not imply otherwise.

## What it does not do

- **It does not submit transfers.** FPL has no official write API, and a wrong
  automated move at 19:29 on a Friday costs more than a button press saves.
- It does not know about suspensions, press conferences, or your gut.
- It does not model double or blank gameweeks (none are scheduled yet).

## Known limitations in this version

- The Bench Boost term is a crude approximation, not a proper 15-man solve.
- The solver will occasionally sell a player and buy him back two weeks later.
  Add a churn penalty (a small cost on every transfer) to stop it.
- Projections beyond the first gameweek come from the local model only, because
  Solio's public feed only publishes the upcoming gameweek.

Treat every output as an argument, not an instruction.
