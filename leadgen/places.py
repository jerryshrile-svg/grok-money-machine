"""Google Places API (New) client — pulls businesses with review counts."""

import os
import time

import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Exactly the fields we need. Places API bills by field mask, so keeping this
# tight keeps the pull cheap.
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.rating",
        "places.userRatingCount",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.primaryTypeDisplayName",
    ]
    + ["nextPageToken"]
)


class PlacesError(RuntimeError):
    pass


def _api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise PlacesError(
            "GOOGLE_MAPS_API_KEY is not set.\n"
            "Create a key at https://console.cloud.google.com/apis/credentials, "
            "enable the 'Places API (New)', then run:\n"
            "  export GOOGLE_MAPS_API_KEY=your_key_here"
        )
    return key


def verify_credentials():
    """Confirm the key exists and is accepted before starting a long pull."""
    _api_key()
    try:
        search_text("mortgage company in Green Bay, WI", page_limit=1)
    except PlacesError as exc:
        raise PlacesError(
            f"{exc}\n\nThe key is set but the API rejected it. Confirm that "
            "'Places API (New)' is enabled for the project and that any key "
            "restrictions allow server-side use."
        )


def search_text(query, page_limit=3):
    """Run one Text Search, following pagination up to page_limit pages."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _api_key(),
        "X-Goog-FieldMask": FIELD_MASK,
    }
    results = []
    page_token = None

    for _ in range(page_limit):
        body = {"textQuery": query, "maxResultCount": 20}
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)
        if resp.status_code != 200:
            raise PlacesError(f"Places API {resp.status_code} for {query!r}: {resp.text[:300]}")

        data = resp.json()
        results.extend(data.get("places", []))

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        # Google needs a moment before a page token becomes valid.
        time.sleep(2)

    return results


def collect(towns, terms, progress=print):
    """Search every town x term combination and dedupe by place id."""
    by_id = {}
    combos = [(t, term) for t in towns for term in terms]

    for i, (town, term) in enumerate(combos, 1):
        query = f"{term} in {town}"
        progress(f"  [{i}/{len(combos)}] {query}")
        try:
            for place in search_text(query):
                pid = place.get("id")
                if pid and pid not in by_id:
                    place["_found_near"] = town
                    by_id[pid] = place
        except PlacesError as exc:
            progress(f"      ! {exc}")

    return list(by_id.values())
