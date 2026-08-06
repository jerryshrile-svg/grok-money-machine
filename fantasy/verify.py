"""The verifier. Does the current state match what we claim about it?

This project's failures all had the same shape: a change was made, a number was
reported, and nothing independently checked that the number was true. The board
spent weeks with a value ordering that lost to the consensus list. A headline
figure was quoted for days that turned out to be sampling noise. A "fix" for
backup quarterbacks shipped on intuition and was measured afterwards.

Every one of those was caught by a verifier — a test, an audit, a backtest — and
none of them were caught by care or attention. So the verifier is the artefact,
not the habit.

What this does: re-measures every claim the documentation makes and reports
whether it still holds. Any claim that cannot be re-measured does not belong in
the documentation.

    python3 verify.py          # fast: tests, data, and the cheap claims
    python3 verify.py --full   # adds the backtest, several minutes

Exit code is non-zero if anything fails, so it can gate a commit.
"""

from __future__ import annotations

import subprocess
import sys

HERE = __file__.rsplit("/", 1)[0]

# Gaps between where this is and where it needs to be. Kept here rather than in
# prose so it is read every time the verifier runs, instead of once.
OPEN_GAPS = [
    ("The other seven keepers are unknown",
     "worth about -45 lineup points, larger than either lever gains. "
     "Nothing to build; ask the league."),
    ("The in-season waiver tool is not built",
     "worth about +28 a season on measured numbers. Needs week-1 usage data, "
     "so it is deliberately after the draft, not before."),
    ("Opponents are modelled generically",
     "your leaguemates' real tendencies would sharpen every survival estimate. "
     "Needs their draft history."),
]


def run(cmd, label):
    """Run a checker and report whether it passed."""
    proc = subprocess.run(
        [sys.executable, *cmd], cwd=HERE, capture_output=True, text=True
    )
    ok = proc.returncode == 0
    detail = ""
    if not ok:
        tail = [ln for ln in (proc.stdout + proc.stderr).strip().split("\n") if ln]
        detail = tail[-1] if tail else f"exit {proc.returncode}"
    return label, ok, detail


def check_tests():
    """Run the invariant tests, reporting the count they actually ran.

    The count was hardcoded at 55 and was 59 within a day. A verifier that
    states a stale number about itself has no standing to check anyone else's.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "test_toolkit"],
        cwd=HERE, capture_output=True, text=True,
    )
    text = proc.stdout + proc.stderr
    count = ""
    for line in text.split("\n"):
        if line.startswith("Ran ") and " test" in line:
            count = line.split()[1]
            break
    label = f"code: {count or '?'} invariant tests"
    if proc.returncode == 0:
        return label, True, ""
    tail = [ln for ln in text.strip().split("\n") if ln]
    return label, False, tail[-1] if tail else "tests failed"


def check_audit():
    return run(["audit.py"], "data: board, keepers, freshness, stale state")


def check_regression_claim():
    """The fade signal should be markedly more reliable than the buy signal."""
    proc = subprocess.run(
        [sys.executable, "validate.py"], cwd=HERE, capture_output=True, text=True
    )
    if proc.returncode != 0:
        return "claim: hot players regress harder than cold ones recover", False, \
               "validate.py failed"
    text = proc.stdout
    try:
        hot = int(text.split("gave back")[1].split("%")[0])
        cold = int(text.split("recovered only")[1].split("%")[0])
    except (IndexError, ValueError):
        return "claim: hot players regress harder than cold ones recover", False, \
               "could not parse validate.py output"
    ok = hot > cold * 1.5
    return ("claim: hot regress harder than cold recover "
            f"({hot}% vs {cold}%)", ok, "" if ok else "asymmetry no longer holds")


def check_backtest_claim(n=120):
    """The rule must still beat drafting straight off the consensus list."""
    proc = subprocess.run(
        [sys.executable, "backtest.py", "all", str(n)],
        cwd=HERE, capture_output=True, text=True,
    )
    label = "claim: wait-cost beats the consensus list"
    if proc.returncode != 0:
        return label, False, "backtest failed to run"
    parsed = parse_backtest_summary(proc.stdout)
    if parsed is None:
        return label, False, "could not find the across-seasons summary"
    mean, se = parsed
    ok = mean > 2 * se
    return (f"{label} ({mean:+.0f} ± {se:.0f} a season)", ok,
            "" if ok else "edge is no longer distinguishable from noise")


SUMMARY_MARKER = "Across all seasons"


def parse_backtest_summary(text: str):
    """Pull the pooled edge and its standard error out of backtest output.

    Anchored on the across-seasons summary, not on the first matching row. The
    per-season blocks use a different column layout, and reading those gave a
    figure of +1590 — the raw points column — which made the check pass on a
    comparison it was never making.
    """
    if SUMMARY_MARKER not in text:
        return None
    tail = text.split(SUMMARY_MARKER, 1)[1]
    for line in tail.split("\n"):
        if not line.startswith("Wait-cost"):
            continue
        parts = line.split()
        # e.g. Wait-cost (live tool)  +30  2  5/5  real
        try:
            return float(parts[3]), float(parts[4])
        except (IndexError, ValueError):
            return None
    return None


def main() -> int:
    full = "--full" in sys.argv
    checks = [check_tests, check_audit, check_regression_claim]
    if full:
        checks.append(check_backtest_claim)
    else:
        print("(fast mode — pass --full to re-measure the backtest too)\n")

    results = []
    for check in checks:
        label, ok, detail = check()
        results.append((label, ok, detail))
        mark = " ok " if ok else "FAIL"
        print(f"  [{mark}] {label}")
        if detail:
            print(f"         {detail}")

    failed = [r for r in results if not r[1]]

    print("\nOpen gaps between here and winning the league:")
    for title, why in OPEN_GAPS:
        print(f"  - {title}\n      {why}")

    if failed:
        print(f"\n{len(failed)} check(s) failed. The documentation currently "
              "claims something that isn't true.")
        return 1
    print("\nEverything the documentation claims is currently measurable and true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
