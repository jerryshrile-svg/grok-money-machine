# NE Wisconsin Mortgage Prospect Finder

Generates a ranked spreadsheet of mortgage companies across northeast Wisconsin
that are likely to need website work — the ones with **no website, a broken
website, or a visibly outdated one**, filtered to businesses with **15–350
Google reviews**.

## Why this is a script

Review counts and website condition can't be researched by hand at any useful
scale, and neither can be guessed. The review window comes from the Google
Places API; the website verdict comes from actually loading each site and
looking at the markup. Both are measured, not estimated.

## Setup

1. Create an API key at <https://console.cloud.google.com/apis/credentials>
2. Enable **Places API (New)** on the same project
3. Install dependencies and run:

```bash
pip3 install requests openpyxl
export GOOGLE_MAPS_API_KEY=your_key_here
python3 leadgen/build_spreadsheet.py
```

Output: `NE_Wisconsin_Mortgage_Prospects.xlsx` in the repo root.

Expect the run to take 10–20 minutes — it searches 29 towns × 5 search terms,
then loads every surviving candidate's website. Cost is a few dollars at most
under the Places API free tier.

## What the spreadsheet contains

Rows are sorted best-opportunity first, and color-coded (red = hottest).

| Column | Notes |
|---|---|
| Priority | 1 = pitch first |
| Business Name / City / Address / Phone | From Google Business Profile |
| Website Status | `No Website`, `Broken`, or `Outdated` |
| **Website URL** | Clickable — opens the site directly |
| Google Reviews / Rating | Live from Places |
| **Why They Need Us** | The specific defects found — your opening line |
| **Google Maps Link** | Clickable — opens the listing |
| Opportunity Score | 0–100, drives the sort |

## How ranking works

Website condition dominates, and review count scales it. A dead site at a
200-review firm outranks a dead site at a 16-review firm, because reviews prove
the business is active enough to afford the work.

```
score = website_score × (0.70 + 0.30 × (reviews / 350))
```

Website scores: no website `100` · broken/parked `90` · outdated `25–95`
depending on how many defects stack up.

## Defects it detects

**Broken** — dead DNS, connection failure, timeout, TLS/certificate error,
HTTP 4xx/5xx, parked-domain and "coming soon" placeholders, empty pages.

**Outdated** — no mobile viewport (the strongest and easiest sell), no HTTPS,
stale footer copyright, table-based layout, framesets, `<font>`/`<center>`
tags, Flash embeds, jQuery 1.x/2.x, FrontPage/Dreamweaver, end-of-life
WordPress, inline `bgcolor` styling.

Sites that come back clean are dropped — they aren't leads.

## Tuning

Everything adjustable lives in `config.py`:

- `TARGET_TOWNS` — the 29 towns searched
- `SEARCH_TERMS` — query phrasings
- `MIN_REVIEWS` / `MAX_REVIEWS` — currently 15 and 350
- `EXCLUDE_NAME_PATTERNS` — national brands and banks, which have in-house
  marketing and won't buy

If you get fewer than 50 rows, widen the review window or add towns — that
means the territory genuinely doesn't hold 50 businesses meeting every
criterion, and padding the list would only waste your calls.
