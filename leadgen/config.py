"""Search configuration for the NE Wisconsin mortgage lead pull."""

# Every town from the target territory. Each is searched independently so that
# small-town operators aren't buried under Green Bay results.
TARGET_TOWNS = [
    # Brown County core
    "Green Bay, WI",
    "De Pere, WI",
    "Howard, WI",
    "Suamico, WI",
    "Hobart, WI",
    "Ashwaubenon, WI",
    "Bellevue, WI",
    "Allouez, WI",
    "Pulaski, WI",
    "Wrightstown, WI",
    "Denmark, WI",
    "Ledgeview, WI",
    "Lawrence, WI",
    "Greenleaf, WI",
    # Just outside Brown County
    "Casco, WI",
    "Luxemburg, WI",
    "Seymour, WI",
    "Kaukauna, WI",
    "Little Chute, WI",
    "Kimberly, WI",
    "Appleton, WI",
    # Further northeast Wisconsin
    "Sturgeon Bay, WI",
    "Algoma, WI",
    "Kewaunee, WI",
    "Oconto, WI",
    "Oconto Falls, WI",
    "Marinette, WI",
    "Peshtigo, WI",
    "Shawano, WI",
]

# Multiple phrasings because Google returns materially different result sets
# for each, and independent brokers often aren't tagged as "mortgage lender".
SEARCH_TERMS = [
    "mortgage company",
    "mortgage broker",
    "mortgage lender",
    "home loans",
    "loan officer",
]

# Review-count window from the brief: enough traction to be a real business,
# not so much that they're a national brand with an in-house marketing team.
MIN_REVIEWS = 15
MAX_REVIEWS = 350

# Big-brand and depository names to drop. These have corporate marketing
# departments and will never buy a local website build.
EXCLUDE_NAME_PATTERNS = [
    "wells fargo", "chase", "u.s. bank", "us bank", "bank of america",
    "quicken", "rocket mortgage", "loandepot", "guild mortgage",
    "fairway independent", "caliber home", "freedom mortgage",
    "pennymac", "better.com", "navy federal", "usaa",
    "associated bank", "nicolet national bank", "north shore bank",
    "bmo harris", "pnc bank", "citizens bank", "huntington",
    "veterans united", "movement mortgage", "cross country mortgage",
    "prosperity home", "supreme lending", "waterstone mortgage",
]
