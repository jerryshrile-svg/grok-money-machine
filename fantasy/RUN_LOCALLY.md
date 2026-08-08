# Running this on your own machine

Everything here is plain Python 3 using only the standard library. No `pip install`,
no virtualenv, no API keys, no accounts. If you can run `python3`, you can run this.

## What you need

- **Python 3.9 or newer.** Check with `python3 --version`.
  - macOS: already installed. If it's ancient, `brew install python3`.
  - Windows: install from [python.org](https://www.python.org/downloads/) and tick
    "Add Python to PATH". Use `py` instead of `python3` in every command below.
  - Linux: `sudo apt install python3` or your distro's equivalent.
- An internet connection for the one-time data download (~37 MB).

## Option A — from the zip

If you have `fantasy-draft-toolkit.zip`, unzip it anywhere and open a terminal
in the resulting `fantasy` folder.

```bash
cd ~/Downloads/fantasy      # or wherever you unzipped it
```

## Option B — from GitHub

```bash
git clone -b claude/fantasy-football-draft-co0mnh \
  https://github.com/jerryshrile-svg/grok-money-machine.git ff
cd ff/fantasy
```

Option B is the better one if you want to pull down any later changes — `git pull`
and you're current.

## First run

Three commands, about a minute total.

```bash
python3 fetch_data.py          # downloads the free public data (~37 MB)
python3 build_projections.py   # builds the board in your exact scoring
python3 verify.py              # checks the code, the data, and every claim
```

`verify.py` should end with *"Everything the documentation claims is currently
measurable and true."* If it doesn't, stop and read what it says — it will name the
thing that's wrong.

## Then, on draft day

```bash
python3 draft_day.py
```

Leave that open in a terminal next to the Yahoo draft window. Type each pick as it
happens; type `me <name>` for your own picks; type `go` when you're on the clock and
it ranks your options by wait cost. `undo` fixes a typo. State auto-saves to
`draft_state.json`, so closing the terminal doesn't lose your draft.

Print your cheat sheet as a backup:

```bash
python3 cheatsheet.py          # writes cheatsheet.html — open it and print
```

## The morning of the draft

The consensus rankings update weekly, so a fresh pull catches every camp injury and
depth-chart change the market has priced in. Costs about five seconds.

```bash
python3 fetch_data.py rankings
python3 build_projections.py
python3 audit.py               # data sanity check
python3 cheatsheet.py          # reprint if anything moved
```

## Do a practice run

Genuinely worth two minutes. Start `draft_day.py`, type ten player names, hit `go`,
look at the table, then `rm draft_state.json` (Windows: `del draft_state.json`) to
wipe it. The point is that the commands stop being something you think about while
the draft clock is running.

## If something goes wrong

| Symptom | Fix |
|---|---|
| `python3: command not found` | Windows uses `py`. Otherwise install Python 3. |
| `fetch_data.py` can't reach GitHub | The committed `data/projections.csv` still drives the whole board. You lose only the `LY` last-season column, and the tool tells you so instead of crashing. |
| Numbers look wrong after editing `league.json` | Re-run `build_projections.py`. Scoring is baked into the board at build time; `engine.py` warns you when the two disagree. |
| Anything else | `python3 verify.py` — it re-measures everything and names what broke. |

## What each file does

See [README.md](README.md) for the full table, and [PLAYBOOK.md](PLAYBOOK.md) for
the strategy reasoning, the measured results, and the things that were tried and
rejected.
