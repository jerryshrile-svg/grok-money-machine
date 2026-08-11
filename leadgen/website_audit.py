"""Audit a business website for the signals that make it a website-services lead.

Three outcomes matter for the pitch:
  NO_WEBSITE  - nothing listed on Google at all
  BROKEN      - domain dead, times out, TLS failure, or serves an error page
  OUTDATED    - loads fine but shows concrete staleness signals
  CURRENT     - modern and responsive; not a lead
"""

import datetime
import re
import socket
import ssl

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"

CURRENT_YEAR = datetime.date.today().year

PARKED_MARKERS = [
    "this domain is for sale", "buy this domain", "domain for sale",
    "parked free", "godaddy.com/domainsearch", "future home of",
    "under construction", "coming soon", "sedoparking", "hugedomains",
    "account suspended", "default web site page", "index of /",
]


def _signal(sig, weight, note):
    return {"signal": sig, "weight": weight, "note": note}


def audit(url, timeout=15):
    """Return a dict describing the website's condition."""
    if not url or not url.strip():
        return {
            "status": "NO_WEBSITE",
            "score": 100,
            "http_code": "",
            "signals": [],
            "summary": "No website listed on Google Business Profile",
        }

    url = url.strip()
    signals = []

    # ---- reachability -------------------------------------------------
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": UA}, allow_redirects=True
        )
    except requests.exceptions.SSLError as exc:
        return _broken(url, f"TLS/certificate failure: {str(exc)[:120]}")
    except (socket.gaierror, requests.exceptions.ConnectionError) as exc:
        return _broken(url, f"Domain unreachable / DNS failure: {str(exc)[:120]}")
    except requests.exceptions.Timeout:
        return _broken(url, f"Timed out after {timeout}s")
    except requests.exceptions.RequestException as exc:
        return _broken(url, f"Request failed: {str(exc)[:120]}")

    code = resp.status_code
    if code >= 400:
        return _broken(url, f"Returns HTTP {code}", http_code=code)

    html = resp.text or ""
    low = html.lower()

    # Parked / placeholder pages count as broken for sales purposes.
    for marker in PARKED_MARKERS:
        if marker in low:
            return _broken(url, f"Parked/placeholder page ({marker!r})", http_code=code)

    if len(html.strip()) < 600:
        return _broken(url, "Page is essentially empty", http_code=code)

    # ---- staleness signals --------------------------------------------
    # Mobile responsiveness is the single strongest tell and the easiest sell.
    if not re.search(r'<meta[^>]+name=["\']viewport["\']', low):
        signals.append(_signal("Not mobile responsive", 30,
                               "No viewport meta tag - renders desktop-width on phones"))

    if not resp.url.lower().startswith("https://"):
        signals.append(_signal("No HTTPS", 25,
                               "Served over plain HTTP - browsers flag a financial "
                               "site 'Not secure'"))

    # Stale copyright is a strong "nobody maintains this" indicator.
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)[^0-9]{0,40}(\d{4})", low)]
    if years:
        newest = max(years)
        age = CURRENT_YEAR - newest
        if age >= 2:
            signals.append(_signal(f"Copyright {newest}", min(10 + age * 5, 30),
                                   f"Footer copyright is {age} years stale"))

    if re.search(r"<frameset|<frame\s", low):
        signals.append(_signal("Frameset layout", 30, "Pre-2000s frame-based HTML"))

    # Table-based layout: look for layout-ish tables, not data tables.
    if re.search(r'<table[^>]*(?:cellpadding|cellspacing|border=)', low):
        signals.append(_signal("Table-based layout", 25,
                               "Uses HTML tables for page layout"))

    if re.search(r"<(font|center|marquee|blink)\b", low):
        signals.append(_signal("Deprecated HTML tags", 20,
                               "Uses <font>/<center>/<marquee> - long-obsolete markup"))

    if re.search(r"\.swf|shockwave-flash|<embed[^>]+flash", low):
        signals.append(_signal("Flash content", 35,
                               "Flash has been dead since 2020 - content is invisible"))

    m = re.search(r"jquery[.-](\d+)\.(\d+)[.\d]*(?:\.min)?\.js", low)
    if m and int(m.group(1)) < 3:
        signals.append(_signal(f"jQuery {m.group(1)}.{m.group(2)}", 20,
                               "Ancient jQuery with known security advisories"))

    for builder, label in [
        ("frontpage", "Microsoft FrontPage"),
        ("dreamweaver", "Adobe Dreamweaver"),
        ("generator\" content=\"wordpress 3", "WordPress 3.x"),
        ("generator\" content=\"wordpress 4", "WordPress 4.x"),
    ]:
        if builder in low:
            signals.append(_signal(f"Built with {label}", 30,
                                   f"{label} - long past end of life"))
            break

    if "bgcolor=" in low or re.search(r'<body[^>]+text=["\']#', low):
        signals.append(_signal("Inline body styling", 15,
                               "Presentational HTML attributes instead of CSS"))

    score = min(sum(s["weight"] for s in signals), 95)

    if score >= 25:
        status = "OUTDATED"
        summary = "; ".join(s["signal"] for s in signals)
    elif signals:
        status = "MINOR_ISSUES"
        summary = "; ".join(s["signal"] for s in signals)
    else:
        status = "CURRENT"
        summary = "Modern and responsive - low priority"

    return {
        "status": status,
        "score": score,
        "http_code": code,
        "signals": signals,
        "summary": summary,
    }


def _broken(url, reason, http_code=""):
    return {
        "status": "BROKEN",
        "score": 90,
        "http_code": http_code,
        "signals": [_signal("Broken website", 90, reason)],
        "summary": reason,
    }
