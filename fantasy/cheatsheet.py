"""Generate the draft-day cheat sheet as a self-contained HTML page.

A cheat sheet you typed by hand goes stale the moment the consensus updates.
This one is built from the same board the live assistant uses, so regenerating
it after a fresh `fetch_data.py` takes a second and can never disagree with what
`draft_day.py` tells you.

    python3 cheatsheet.py              # -> cheatsheet.html
    python3 cheatsheet.py /tmp/x.html
"""

from __future__ import annotations

import html
import os
import sys
from datetime import date

from engine import HERE, build_board, load_league, load_players, snake_picks
from last_season import norm

# How deep to print each position. Enough to cover every pick that matters,
# short enough to stay a sheet rather than a book.
DEPTH = {"RB": 16, "WR": 16, "TE": 9, "QB": 9}


def consensus_date() -> str:
    """When the rankings behind this sheet were actually scraped.

    Read from the same file audit.py reads, not typed into the template. It was
    hardcoded to a date that went stale within a week, which is the worst
    possible bug for this particular artefact: the sheet exists to tell you how
    current your board is, and a correctly-refreshed board would have printed
    one claiming to be two weeks old on draft morning.
    """
    import json

    path = os.path.join(HERE, "data", "projections.meta.json")
    try:
        with open(path) as fh:
            return json.load(fh).get("scrape_date", "") or "unknown"
    except (OSError, ValueError):
        return "unknown"

# What the wait-cost rule does at each pick, from `sim.py plan`.
PLAN = [
    ("6", "1", "Bijan Robinson", "keeper, costs your R1"),
    ("11", "2", "RB 80% · WR 19%", "Jeanty, Taylor, McCaffrey"),
    ("22", "3", "RB 37% · QB 25% · WR 20% · TE 18%", "Allen, Achane, McBride"),
    ("27", "4", "QB 51% · WR 42%", "Jackson, Maye, Flowers"),
    ("38", "5", "WR 57% · RB 26% · QB 12%", "McMillan, Higgins, Wilson"),
    ("43", "6", "WR 52% · RB 27% · QB 19%", "Daniels, Nabers, McConkey"),
    ("54", "7", "WR 60% · RB 23% · QB 14%", "Adams, Burden, Skattebo"),
    ("59", "8", "RB 86%", "Irving, Judkins, Skattebo"),
    ("70", "9", "RB 42% · TE 29% · QB 28%", "Tuten, Fannin, Kraft"),
    ("75", "10", "WR 47% · RB 26% · TE 17%", "Pierce, Pitts, Tuten"),
    ("86", "11", "RB 47% · WR 34%", "Pollard, Stevenson, Hubbard"),
    ("91", "12", "RB 41% · QB 21% · TE 19%", "Harvey, Dart — or an IR stash"),
    ("102", "13", "KICKER", "last two picks, never earlier"),
    ("107", "14", "DEFENSE", "stream both all season"),
]


RULES = [
    ("Take the highest wait cost",
     "Not best available. Value now minus what you'd still get at that position "
     "at your next pick. Backtested over 20,000 drafts across five real seasons: "
     "+30 points a season over drafting straight off the list, and the only "
     "strategy that won all five."),
    ("Don't run a script",
     "RB-heavy was the best plan of 2021 and the worst of 2024. Averaged over "
     "five seasons it is 21 points WORSE than drafting off the list. No fixed "
     "plan survives; the rule wins by reacting. React."),
    ("Assume the K players are gone",
     "Seven teams keep one each, and a keeper costs the round he went last year — "
     "so last season's late breakouts vanish, not this season's best players."),
    ("All four elite WRs go by consensus #6",
     "They will not reach pick 11. Take one if he slides, but don't plan on it."),
    ("Tier-1 QB runs to #69, tier-1 TE to #54",
     "Both wait rounds, not picks. Forcing either at pick 11 is the worst move "
     "on the board."),
    ("Fade the hot, only half-trust the cold",
     "Hot players gave back 91% of the gap between what they scored and what "
     "their usage earned. Cold ones recovered just 31%."),
    ("Kicker and defense are picks 102 and 107",
     "Every round spent earlier is pure loss. One late pick is better spent on a "
     "player who opens on IR — that stash costs you no bench spot."),
]



def display_name(name: str) -> str:
    """Abbreviate the first name when the full one would wrap.

    A wrapped name costs two lines and a beat of reading time; the surname is
    what you are scanning for anyway.
    """
    if len(name) <= 15 or " " not in name:
        return name
    first, rest = name.split(" ", 1)
    return f"{first[0]}. {rest}"


def likely_keepers(board, league, season):
    """The players most likely off the board before the draft starts.

    Seven other teams keep at most seven players, and a keeper costs the round
    that player went in last year — so the ones that disappear are last season's
    late-round breakouts, not this season's best players.
    """
    try:
        from keepers import candidates
    except ImportError:
        return set()
    played = set(season.rec) if season is not None else None
    rows = [r for r in candidates(board, league, played) if not r["mine"]]
    return {norm(r["player"].name) for r in rows[: league["teams"] - 1]}


def playoff_difficulty(league):
    """Points above average conceded by each team's weeks 15-17 opponents."""
    try:
        import playoffs

        opponents = playoffs.playoff_opponents(league)
        if not opponents:
            return {}, playoffs
        allowed = playoffs.points_allowed(league["scoring"])
        avg = playoffs.league_average(allowed)
        return playoffs.difficulty(allowed, avg, opponents), playoffs
    except (ImportError, OSError):
        return {}, None


def poe_flag(season, name):
    """Regression signal from last season's points over expected."""
    if season is None:
        return "", ""
    d = season.get(name)
    if d is None:
        return "new", "new"
    v = d["poe_pg"]
    if v > 1.5:
        return f"{v:+.1f}", "hot"
    if v < -1.5:
        return f"{v:+.1f}", "cold"
    return f"{v:+.1f}", ""


def position_block(board, season, pos, depth, kept, diff, pmod):
    pool = sorted((p for p in board if p.pos == pos), key=lambda x: -x.vorp)[:depth]
    rows, current_tier = [], None
    for p in pool:
        if p.tier != current_tier:
            current_tier = p.tier
            rows.append(
                f'<tr class="tier-head"><th colspan="5">Tier {current_tier}</th></tr>'
            )
        val, cls = poe_flag(season, p.name)
        chip = f'<span class="chip {cls}">{html.escape(val)}</span>' if val else ""

        gone = norm(p.name) in kept
        mark = '<span class="kept" title="likely kept">K</span>' if gone else ""

        po = ""
        if diff and pmod:
            d = diff.get(pmod.team(p.team), {}).get(p.pos)
            if d is not None:
                pcls = "easy" if d > 1.5 else ("hard" if d < -1.5 else "")
                po = f'<span class="po {pcls}">{d:+.1f}</span>'

        rows.append(
            f'<tr class="{"gone" if gone else ""}">'
            f'<td class="rk">{pos}{p.pos_rank}</td>'
            f'<td class="nm">{html.escape(display_name(p.name))}{mark}</td>'
            f'<td class="num">{p.adp:.0f}</td>'
            f'<td class="po-cell">{po}</td>'
            f'<td class="ly">{chip}</td>'
            "</tr>"
        )
    return (
        f'<section class="pos"><h2>{pos}</h2>'
        '<table><thead><tr>'
        '<th class="rk">#</th><th class="nm">Player</th>'
        '<th class="num">ECR</th><th class="po-cell">Wk15-17</th>'
        '<th class="ly">LY</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>"
    )


def build(board, league, season) -> str:  # noqa: C901
    picks = snake_picks(league["my_draft_slot"], league["teams"], league["rounds"])
    keeper_picks = {
        k["pick_overall"] for k in league.get("keepers", []) if k.get("pick_overall")
    }
    pick_chips = "".join(
        f'<li class="{"keeper" if p in keeper_picks else ""}">{p}</li>' for p in picks
    )

    # RB and WR carry the draft, so they get their own columns. TE and QB are
    # short lists and stack into the third, which also kills the dead space
    # under them.
    kept = likely_keepers(board, league, season)
    diff, pmod = playoff_difficulty(league)
    blk = lambda pos: position_block(  # noqa: E731
        board, season, pos, DEPTH[pos], kept, diff, pmod
    )
    blocks = (
        blk("RB") + blk("WR")
        + '<div class="stack">' + blk("TE") + blk("QB") + "</div>"
    )

    plan_rows = "".join(
        f"<tr><td class='num'>{pk}</td><td class='num rd'>{rd}</td>"
        f"<td>{html.escape(mix)}</td><td class='dim'>{html.escape(who)}</td></tr>"
        for pk, rd, mix, who in PLAN
    )

    rule_items = "".join(
        f"<li><b>{html.escape(t)}</b><span>{html.escape(d)}</span></li>"
        for t, d in RULES
    )

    printed = date.today().isoformat()
    scraped = consensus_date()
    return f"""<title>Draft Day — 8-Team 0.5 PPR, Pick 6</title>
<style>
:root {{
  --ground:#EFF3F6; --surface:#FFFFFF; --ink:#0C1216; --muted:#5A6771;
  --line:#CFD8DF; --soft:#E7EDF1;
  --accent:#A6331B; --hot:#8A5A0C; --cold:#0B6154;
  --hot-bg:#F7EBD6; --cold-bg:#D9EEE9;
}}
@media (prefers-color-scheme:dark) {{
  :root {{
    --ground:#0D1216; --surface:#151B21; --ink:#E3EAEF; --muted:#8B97A2;
    --line:#2B343C; --soft:#1E262D;
    --accent:#E4735A; --hot:#D6A24A; --cold:#4FBFA8;
    --hot-bg:#2C2415; --cold-bg:#12302B;
  }}
}}
:root[data-theme="light"] {{
  --ground:#EFF3F6; --surface:#FFFFFF; --ink:#0C1216; --muted:#5A6771;
  --line:#CFD8DF; --soft:#E7EDF1;
  --accent:#A6331B; --hot:#8A5A0C; --cold:#0B6154;
  --hot-bg:#F7EBD6; --cold-bg:#D9EEE9;
}}
:root[data-theme="dark"] {{
  --ground:#0D1216; --surface:#151B21; --ink:#E3EAEF; --muted:#8B97A2;
  --line:#2B343C; --soft:#1E262D;
  --accent:#E4735A; --hot:#D6A24A; --cold:#4FBFA8;
  --hot-bg:#2C2415; --cold-bg:#12302B;
}}

html, body {{
  --mono: ui-monospace, "SF Mono", SFMono-Regular, "JetBrains Mono", Menlo,
          Consolas, "Liberation Mono", monospace;
}}

* {{ box-sizing:border-box; }}
body {{
  margin:0; padding:28px 20px 64px;
  background:var(--ground); color:var(--ink);
  font-family:var(--mono);
  font-size:13px; line-height:1.45;
  -webkit-font-smoothing:antialiased;
}}
.sheet {{ max-width:1180px; margin:0 auto; display:flex; flex-direction:column; gap:22px; }}

header {{ display:flex; flex-wrap:wrap; align-items:flex-end; gap:12px 24px;
  border-bottom:2px solid var(--ink); padding-bottom:12px; }}
h1 {{ margin:0; font-size:26px; font-weight:700; letter-spacing:-.02em;
  text-wrap:balance; }}
h1 em {{ font-style:normal; color:var(--accent); }}
.meta {{ color:var(--muted); font-size:11.5px; letter-spacing:.04em;
  text-transform:uppercase; margin-left:auto; text-align:right; }}

.rule {{ background:var(--surface); border:1px solid var(--line);
  border-left:4px solid var(--accent); padding:14px 18px; }}
.rule b {{ display:block; font-size:15px; letter-spacing:-.01em; }}
.rule span {{ color:var(--muted); }}

.picks {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
.picks h3 {{ margin:0; font-size:11.5px; letter-spacing:.08em;
  text-transform:uppercase; color:var(--muted); }}
.picks ul {{ display:flex; gap:6px; flex-wrap:wrap; list-style:none; margin:0; padding:0; }}
.picks li {{ background:var(--surface); border:1px solid var(--line);
  padding:4px 10px; font-variant-numeric:tabular-nums; font-weight:600; }}
.picks li.keeper {{ background:var(--accent); border-color:var(--accent);
  color:#fff; }}

.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:14px; }}
@media (min-width:980px) {{
  .grid {{ grid-template-columns:1fr 1fr 1fr; align-items:start; }}
}}
.stack {{ display:flex; flex-direction:column; gap:14px; }}
.pos {{ background:var(--surface); border:1px solid var(--line); break-inside:avoid; }}
.pos h2 {{ margin:0; padding:9px 12px; font-size:12px; letter-spacing:.12em;
  text-transform:uppercase; border-bottom:1px solid var(--line);
  background:var(--soft); }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums;
  font-size:12px; table-layout:fixed; }}
th, td {{ text-align:left; padding:3.5px 7px; }}
thead th {{ font-size:10px; letter-spacing:.05em; text-transform:uppercase;
  color:var(--muted); font-weight:500; border-bottom:1px solid var(--soft);
  white-space:nowrap; }}
tbody tr:not(.tier-head):hover {{ background:var(--soft); }}
.tier-head th {{ font-size:10px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--accent); font-weight:700; padding:9px 8px 3px;
  border-top:1px solid var(--line); }}
.pos tbody tr:first-child th {{ border-top:none; }}
.rk {{ color:var(--muted); width:34px; font-size:10.5px; }}
.nm {{ font-weight:600; letter-spacing:-.015em; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.num {{ text-align:right; width:34px; }}
.po-cell {{ width:56px; text-align:right; }}
.po {{ font-size:10.5px; color:var(--muted); }}
.po.easy {{ color:var(--cold); font-weight:600; }}
.po.hard {{ color:var(--hot); font-weight:600; }}
.kept {{ display:inline-block; margin-left:5px; padding:0 3px; font-size:9px;
  font-weight:700; border-radius:2px; background:var(--accent); color:#fff;
  vertical-align:1px; }}
tr.gone .nm, tr.gone .rk, tr.gone .num {{ opacity:.45; }}
.ly {{ width:46px; text-align:right; }}
.chip {{ display:inline-block; padding:1px 5px; font-size:10.5px; font-weight:600;
  border-radius:2px; color:var(--muted); }}
.chip.hot {{ background:var(--hot-bg); color:var(--hot); }}
.chip.cold {{ background:var(--cold-bg); color:var(--cold); }}

.lower {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:16px; }}
.panel {{ background:var(--surface); border:1px solid var(--line); break-inside:avoid; }}
.panel h2 {{ margin:0; padding:9px 12px; font-size:12px; letter-spacing:.12em;
  text-transform:uppercase; border-bottom:1px solid var(--line); background:var(--soft); }}
.panel .body {{ padding:4px 0 8px; }}
.plan td {{ border-bottom:1px solid var(--soft); font-size:12px; }}
.plan .rd {{ color:var(--muted); }}
.plan .dim {{ color:var(--muted); font-size:11px; }}
.scroll {{ overflow-x:auto; }}

.rules {{ list-style:none; margin:0; padding:6px 12px 10px; }}
.rules li {{ padding:7px 0; border-bottom:1px solid var(--soft); }}
.rules li:last-child {{ border-bottom:none; }}
.rules b {{ display:block; }}
.rules span {{ color:var(--muted); font-size:11.5px; }}

footer {{ color:var(--muted); font-size:11.5px; border-top:1px solid var(--line);
  padding-top:12px; display:flex; flex-wrap:wrap; gap:6px 18px; }}
footer code {{ color:var(--ink); background:var(--soft); padding:1px 5px; }}

@media print {{
  @page {{ margin:12mm; }}
  body {{ background:#fff; padding:0; font-size:10.5px; }}
  .pos, .panel, .rule {{ border-color:#bbb; }}
  tbody tr:hover {{ background:none; }}
}}
@media (max-width:520px) {{
  body {{ padding:18px 12px 40px; }}
  h1 {{ font-size:21px; }}
  .meta {{ margin-left:0; text-align:left; }}
}}
</style>

<div class="sheet">
<header>
  <h1>Draft Day &mdash; <em>pick 6 of 8</em></h1>
  <div class="meta">0.5 PPR &middot; snake &middot; 14 rounds<br>consensus {scraped} &middot; sheet {printed}</div>
</header>

<div class="rule">
  <b>Take the highest wait cost, not the best player available.</b>
  <span>Value now minus what you'd still expect at that position at your next pick.
  In the terminal that is <code>go</code>.</span>
</div>

<div class="picks">
  <h3>Your picks</h3>
  <ul>{pick_chips}</ul>
</div>

<div class="grid">{blocks}</div>

<div class="lower">
  <section class="panel">
    <h2>Round plan</h2>
    <div class="body scroll">
      <table class="plan">
        <thead><tr><th class="num">Pick</th><th class="num rd">Rd</th>
        <th>What the rule takes</th><th>Likeliest</th></tr></thead>
        <tbody>{plan_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <h2>Hold these in your head</h2>
    <ul class="rules">{rule_items}</ul>
  </section>
</div>

<footer>
  <span><span class="kept">K</span> likely kept by another team &mdash; assume gone.</span>
  <span><b>Wk15-17</b> = playoff schedule, points vs average. Tiebreaker only.</span>
  <span><b>LY</b> = 2025 points over expected/game.
  <span class="chip hot">+3.4</span> fade &middot;
  <span class="chip cold">-2.6</span> partial bounce.</span>
  <span><code>go</code> recommend &middot; <code>me &lt;name&gt;</code> your pick &middot;
  <code>why &lt;name&gt;</code> 2025 card &middot; <code>undo</code></span>
</footer>
</div>"""


def main() -> int:
    league = load_league()
    board = build_board(league, load_players())
    try:
        from last_season import Season

        season = Season(league["scoring"])
    except OSError:
        season = None
        print("note: 2025 data missing, LY column omitted (run fetch_data.py)")

    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "cheatsheet.html")
    with open(out, "w") as fh:
        fh.write(build(board, league, season))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
