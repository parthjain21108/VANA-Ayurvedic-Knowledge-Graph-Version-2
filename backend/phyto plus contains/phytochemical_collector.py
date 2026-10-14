import argparse
import json
import os
import random
import re
import time
import unicodedata
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://cb.imsc.res.in/imppat"
CACHE_FILE = "imppat_cache_v3.json"

# External IMPPAT lookup aliases only. Output identity remains the requested
# canonical/input scientific name.
IMPPAT_LOOKUP_ALIASES = {
    "abroma augustum": ("Abroma augusta", "Ambroma augusta"),
}

OUTPUT_COLUMNS = [
    "plant_part_id",
    "plant_name",
    "plant_part",
    "imppat_id",
    "phytochemical_name",
    "source_url",
    "source",
    "references",
    "association_level",
    "confidence",
    "evidence",
]

ALIASES = {
    "leaves": "leaf",
    "roots": "root",
    "stems": "stem",
    "barks": "bark",
    "fruits": "fruit",
    "seeds": "seed",
    "flowers": "flower",
    "rhizomes": "rhizome",
    "wholeplant": "whole plant",
    "whole plant": "whole plant",
    "aerial parts": "aerial part",
    "aerial part": "aerial part",
    "wood": "wood",
}


def clean(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    value = str(value).replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", value).strip()


def normalize_part(value):
    value = clean(value).lower()
    return ALIASES.get(value, value)


def normalize_plant(value):
    value = clean(value).lower()
    value = re.sub(r"\s+", " ", value)
    return value


def normalize_compound_name(value):
    """Normalize Unicode compatibility forms, whitespace, and case only.

    Do not strip punctuation or stereochemical marks: fuzzy normalization could
    merge chemically distinct compounds.
    """
    value = unicodedata.normalize("NFKC", clean(value))
    return re.sub(r"\s+", " ", value).strip().casefold()


CURRENT_ID_RE = re.compile(r"\b(IMPPAT\d+_PHYID\d+)\b", re.IGNORECASE)
LEGACY_ID_RE = re.compile(r"\b(IMPHY\d+)\b", re.IGNORECASE)
MIN_CATALOGUE_IDS = 10000


def fetch_current_catalogue(session):
    """Read the live IMPPAT 3.0 name/ID dropdown once per collector run."""
    url = f"{BASE_URL}/"
    print(f"      GET current IMPPAT 3.0 catalogue: {url}")
    html = fetch(session, url)
    if not html:
        raise RuntimeError(
            "Could not fetch the live IMPPAT homepage; refusing to publish "
            "a mapping that may contain legacy identifiers."
        )

    soup = BeautifulSoup(html, "html.parser")
    by_name = {}
    catalogue_ids = set()
    for option in soup.find_all("option"):
        value = clean(option.get("value", ""))
        match = CURRENT_ID_RE.search(value)
        if not match:
            continue
        compound_id = match.group(1).upper()
        compound_name = clean(option.get_text(" ", strip=True))
        if not compound_name or compound_name.casefold() == "choose from dropdown":
            continue
        catalogue_ids.add(compound_id)
        key = normalize_compound_name(compound_name)
        by_name.setdefault(key, set()).add(compound_id)

    if len(catalogue_ids) < MIN_CATALOGUE_IDS:
        raise RuntimeError(
            "The live IMPPAT homepage did not expose the expected current "
            f"phytochemical catalogue (found {len(catalogue_ids)} IDs; "
            f"expected at least {MIN_CATALOGUE_IDS}). Refusing to publish."
        )

    unique_names = sum(1 for ids in by_name.values() if len(ids) == 1)
    ambiguous_names = sum(1 for ids in by_name.values() if len(ids) > 1)
    print(
        f"      Live catalogue: {len(catalogue_ids)} current IDs; "
        f"{unique_names} unique names; {ambiguous_names} ambiguous names"
    )
    return by_name, catalogue_ids


def reconcile_record_ids(records, catalogue_by_name, catalogue_ids):
    """Return resolved records, unresolved audit rows, and resolution counts."""
    resolved = []
    unresolved = []
    counts = {"already_current": 0, "legacy_upgraded": 0}

    for source_record in records:
        record = dict(source_record)
        original_id = clean(record.get("imppat_id", "")).upper()
        name = clean(record.get("phytochemical_name", ""))
        candidates = set()
        reason = ""

        if CURRENT_ID_RE.fullmatch(original_id):
            if original_id in catalogue_ids:
                record["imppat_id"] = original_id
                counts["already_current"] += 1
                resolved.append(record)
                continue
            reason = "Current-format ID is absent from the live catalogue"
        elif LEGACY_ID_RE.fullmatch(original_id):
            candidates = catalogue_by_name.get(normalize_compound_name(name), set())
            if len(candidates) == 1:
                record["imppat_id"] = next(iter(candidates))
                counts["legacy_upgraded"] += 1
                resolved.append(record)
                continue
            if not candidates:
                reason = "No exact compound-name match in the live catalogue"
            else:
                reason = "Compound name maps to multiple current IDs"
        else:
            reason = "Missing or unrecognized IMPPAT identifier format"

        unresolved.append({
            "plant_name": clean(record.get("plant_name", "")),
            "plant_part": clean(record.get("plant_part", "")),
            "legacy_or_unknown_id": original_id,
            "phytochemical_name": name,
            "candidate_current_ids": "; ".join(sorted(candidates)),
            "reason": reason,
        })

    return resolved, unresolved, counts


def split_references(value):
    value = clean(value)

    if not value:
        return set()

    # IMPPAT references are usually comma-separated,
    # but preserve DOI/ISBN tokens.
    parts = re.split(r"\s*,\s*", value)

    return {
        p.strip().lower()
        for p in parts
        if p.strip()
    }


def load_cache(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache, path):
    tmp = path + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(tmp, path)


def create_session():
    s = requests.Session()

    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })

    return s


def fetch(session, url, retries=4):
    for attempt in range(retries):
        try:
            r = session.get(
                url,
                timeout=35,
            )

            if r.status_code == 200:
                return r.text

            if r.status_code in (
                429,
                500,
                502,
                503,
                504,
            ):
                wait = (
                    min(20, 2.5 * (attempt + 1))
                    + random.uniform(0.3, 1.2)
                )

                print(
                    f"      HTTP {r.status_code}; "
                    f"retry in {wait:.1f}s"
                )

                time.sleep(wait)
                continue

            print(f"      HTTP {r.status_code}")
            return None

        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(
                    f"      request failed: {exc}"
                )
                return None

            wait = (
                min(15, 2.5 * (attempt + 1))
                + random.uniform(0.3, 1.2)
            )

            print(
                f"      request error; "
                f"retry in {wait:.1f}s"
            )

            time.sleep(wait)

    return None


def _header_text(value):
    value = clean(value).casefold().replace("_", " ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _find_header_index(headers, candidates, *, contains=True):
    normalized = [_header_text(h) for h in headers]
    wanted = [_header_text(c) for c in candidates]

    for candidate in wanted:
        for index, header in enumerate(normalized):
            if header == candidate:
                return index

    if contains:
        for candidate in wanted:
            for index, header in enumerate(normalized):
                if candidate and candidate in header:
                    return index
    return None


def _find_imppat_id(row, values, id_idx):
    candidates = []
    if id_idx is not None and id_idx < len(values):
        candidates.append(values[id_idx])
    candidates.extend(values)
    for cell in row.find_all(["td", "th"]):
        candidates.append(cell.get_text(" ", strip=True))
        for link in cell.find_all("a", href=True):
            candidates.append(link.get("href", ""))

    # Prefer any current ID found in text or a detail-link href over a legacy
    # display value elsewhere in the same row.
    for pattern in (CURRENT_ID_RE, LEGACY_ID_RE):
        for candidate in candidates:
            match = pattern.search(clean(candidate))
            if match:
                return match.group(1).upper()
    return ""


def _same_plant(left, right):
    left_norm = normalize_plant(left)
    right_norm = normalize_plant(right)
    if left_norm == right_norm:
        return True
    # Some IMPPAT rows append taxonomic authors. Compare the binomial only
    # when both names clearly start with the same two words.
    left_words = left_norm.split()
    right_words = right_norm.split()
    return len(left_words) >= 2 and len(right_words) >= 2 and left_words[:2] == right_words[:2]


def parse_phytochemical_table_details(html, requested_plant=""):
    """Return (records, table_recognized) from IMPPAT plant-association HTML.

    IMPPAT has used header rows at different positions in its HTML tables and
    slightly different column labels. Search the first five rows (matching the
    plant-part collector) and tolerate common header variants. The boolean is
    important: an unrecognized table must not be cached as a valid empty result.
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []
    table_recognized = False
    malformed_rows = 0

    for table in soup.find_all("table"):
        parsed_rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if cells:
                parsed_rows.append((tr, [
                    clean(cell.get_text(" ", strip=True)) for cell in cells
                ]))
        if len(parsed_rows) < 2:
            continue

        header_row_index = None
        indexes = None
        for row_index, (_header_tag, headers) in enumerate(parsed_rows[:5]):
            header_text = " ".join(_header_text(h) for h in headers)
            part_idx = _find_header_index(headers, ["plant part"])
            if part_idx is None or not any(token in header_text for token in ("phytochemical", "imphy", "imppat")):
                continue

            plant_idx = _find_header_index(
                headers,
                ["indian medicinal plant", "plant name"],
            )
            if plant_idx is None:
                plant_idx = _find_header_index(headers, ["plant"], contains=False)

            id_idx = _find_header_index(
                headers,
                [
                    "imppat phytochemical identifier",
                    "imppat phytochemical id",
                    "imppat id",
                    "imphy identifier",
                    "imphy id",
                    "phytochemical identifier",
                    "phytochemical id",
                ],
            )
            if id_idx is None:
                for idx, header in enumerate(headers):
                    h = _header_text(header)
                    if "imppat" in h and "phytochemical" in h and not any(x in h for x in ("name", "compound")):
                        id_idx = idx
                        break
            name_idx = _find_header_index(
                headers,
                ["phytochemical name", "name of phytochemical", "compound name"],
            )
            if name_idx is None:
                for idx, header in enumerate(headers):
                    h = _header_text(header)
                    if "phytochemical" in h and not any(x in h for x in ("id", "identifier", "imppat")):
                        name_idx = idx
                        break
            if id_idx is None and name_idx is None:
                continue
            if name_idx is None:
                continue

            header_row_index = row_index
            indexes = (plant_idx, part_idx, id_idx, name_idx, headers)
            table_recognized = True
            break

        if header_row_index is None or indexes is None:
            continue

        plant_idx, part_idx, id_idx, name_idx, header_values = indexes
        ref_idx = _find_header_index(header_values, ["references", "reference", "citation"])
        for row_tag, row in parsed_rows[header_row_index + 1:]:
            if part_idx >= len(row) or name_idx >= len(row):
                continue
            if [_header_text(value) for value in row] == [_header_text(value) for value in header_values]:
                continue
            row_plant = row[plant_idx] if plant_idx is not None and plant_idx < len(row) else requested_plant
            if requested_plant and row_plant and not _same_plant(row_plant, requested_plant):
                continue

            row_text = " ".join(clean(value) for value in row if clean(value))
            if re.search(r"no data available|no matching records|no records found", row_text, flags=re.I):
                continue

            imppat_id = _find_imppat_id(row_tag, row, id_idx)
            compound_name = clean(row[name_idx])
            if not imppat_id or not compound_name:
                # A data-shaped row in a recognized association table that
                # cannot yield a compound ID/name is a parser/schema problem,
                # not evidence that the plant has no phytochemicals.
                if row_text:
                    malformed_rows += 1
                continue

            references = clean(row[ref_idx]) if ref_idx is not None and ref_idx < len(row) else ""
            records.append({
                "plant_name": clean(row_plant or requested_plant),
                "plant_part": clean(row[part_idx]),
                "imppat_id": imppat_id,
                "phytochemical_name": compound_name,
                "references": references,
            })

    # Avoid duplicates caused by responsive/desktop copies of the same table.
    deduped = []
    seen = set()
    for record in records:
        key = (
            normalize_plant(record["plant_name"]),
            normalize_part(record["plant_part"]),
            record["imppat_id"],
            normalize_plant(record["phytochemical_name"]),
            clean(record["references"]),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(record)
    return deduped, table_recognized, malformed_rows


def parse_phytochemical_table(html, requested_plant=""):
    """Backward-compatible records-only wrapper used by tests/tools."""
    records, _recognized, _malformed = parse_phytochemical_table_details(html, requested_plant)
    return records


def get_plant_records(session, plant_name, cache):
    key = normalize_plant(plant_name)
    cached = cache.get(key)
    if isinstance(cached, list) and cached:
        return cached
    if key in cache:
        # Previous releases cached parser failures as []. Do not treat those
        # negatives as authoritative; delete and retry the live page.
        cache.pop(key, None)

    # Preserve canonical identity in output while allowing documented IMPPAT
    # lookup-name variants for Abroma (the canonical/input name is not rewritten).
    lookup_names = [plant_name]
    lookup_names.extend(IMPPAT_LOOKUP_ALIASES.get(key, ()))

    saw_html = False
    recognized_any = False
    malformed_total = 0

    for lookup_name in lookup_names:
        encoded = quote(lookup_name, safe="")
        urls = [
            f"{BASE_URL}/phytochemical/{encoded}",
            f"{BASE_URL}/basicsearch/{encoded}",
        ]
        for url in urls:
            print(f"      GET {url}")
            html = fetch(session, url)
            if not html:
                continue
            saw_html = True
            records, table_recognized, malformed_rows = parse_phytochemical_table_details(
                html, requested_plant=lookup_name
            )
            recognized_any = recognized_any or table_recognized
            malformed_total += malformed_rows
            if records:
                for record in records:
                    # Preserve the user/canonical input plant name; the alias
                    # only controls the external IMPPAT lookup.
                    record["plant_name"] = plant_name
                cache[key] = records
                return records
            if not table_recognized:
                print("      IMPPAT phytochemical table/header not recognized; trying fallback URL/name")
            else:
                print("      IMPPAT table recognized but no usable IMPHY rows; trying fallback URL/name")

    # A successful HTTP response with no recognizable association table is
    # not equivalent to a plant with no IMPPAT data. Fail the collector so the
    # orchestrator cannot merge a misleading partial graph.
    if saw_html and not recognized_any:
        raise RuntimeError(
            f"IMPPAT returned HTML for {plant_name!r}, but no recognizable "
            "plant-part/phytochemical association table was found. "
            "Refusing to treat a parser mismatch as zero phytochemicals."
        )
    if malformed_total:
        raise RuntimeError(
            f"IMPPAT association table for {plant_name!r} contained "
            f"{malformed_total} data-shaped row(s) with no usable IMPHY ID/name. "
            "Refusing to cache a potentially incomplete phytochemical mapping."
        )

    # Intentionally do not cache an empty result: it may be a transient HTTP
    # or lookup issue rather than a scientifically empty page.
    return []


def get_explicit(
    records,
    requested_part,
):
    requested = normalize_part(
        requested_part
    )

    return [
        r
        for r in records
        if normalize_part(
            r["plant_part"]
        ) == requested
    ]


def get_blank(records):
    return [
        r
        for r in records
        if not normalize_part(
            r["plant_part"]
        )
    ]


def infer_from_shared_reference(
    explicit_records,
    blank_record,
):
    """
    Conservative inference:

    A blank plant-level association is promoted
    to a requested part ONLY when its IMPPAT
    reference set overlaps a part-specific
    association for the same plant and compound.

    This does not invent a part from the
    compound name.
    """

    blank_refs = split_references(
        blank_record["references"]
    )

    if not blank_refs:
        return []

    candidates = []

    for r in explicit_records:
        if (
            r["imppat_id"]
            != blank_record["imppat_id"]
        ):
            continue

        refs = split_references(
            r["references"]
        )

        overlap = blank_refs & refs

        if overlap:
            candidates.append(
                (r, overlap)
            )

    return candidates


def build(
    input_file,
    output_file,
    include_inferred=True,
):
    print("=" * 78)
    print(
        "IMPPAT PLANT-PART PHYTOCHEMICAL "
        "COLLECTOR — WIDE / CONSERVATIVE"
    )
    print("=" * 78)

    df = pd.read_excel(
        input_file
    )

    required = [
        "plant_part_id",
        "plant_name",
        "plant_part",
        "source_name",
    ]

    missing = [
        c
        for c in required
        if c not in df.columns
    ]

    if missing:
        raise ValueError(
            "Missing columns: "
            + ", ".join(missing)
        )

    df = df.copy()

    for c in required:
        df[c] = df[c].map(clean)

    print(
        f"Plant-part rows: {len(df)}"
    )

    plants = (
        df["plant_name"]
        .drop_duplicates()
        .tolist()
    )

    print(
        f"Unique plants: {len(plants)}"
    )

    session = create_session()

    # A versioned cache forces a fresh association scrape after the previous
    # parser may have cached a non-empty but incomplete legacy-ID table. V2 is
    # left intact; cached V3 records are reconciled against the live catalogue
    # on every run.
    catalogue_by_name, catalogue_ids = fetch_current_catalogue(session)
    cache = load_cache(CACHE_FILE)

    rows = []
    unmatched = []
    inferred_rows = []
    plant_level_candidates = []
    id_reconciliation_audit = []
    id_resolution_counts = {"already_current": 0, "legacy_upgraded": 0}
    checkpoint_file = output_file + ".partial.xlsx"
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    for n, plant in enumerate(
        plants,
        1,
    ):
        print(
            f"\n[{n}/{len(plants)}] {plant}"
        )

        records = get_plant_records(
            session,
            plant,
            cache,
        )

        save_cache(
            cache,
            CACHE_FILE,
        )

        records, id_audit, id_counts = reconcile_record_ids(
            records, catalogue_by_name, catalogue_ids
        )
        id_reconciliation_audit.extend(id_audit)
        for counter_name, counter_value in id_counts.items():
            id_resolution_counts[counter_name] += counter_value

        if not records:
            print(
                "    IMPPAT records: 0"
            )

            plant_rows = df[
                df["plant_name"]
                .map(normalize_plant)
                == normalize_plant(plant)
            ]

            for _, pr in plant_rows.iterrows():
                unmatched.append({
                    "plant_part_id":
                        pr["plant_part_id"],
                    "plant_name":
                        plant,
                    "plant_part":
                        pr["plant_part"],
                    "reason":
                        "No IMPPAT plant "
                        "phytochemical "
                        "page/records",
                })

            continue

        plant_records = [
            r
            for r in records
            if normalize_plant(
                r["plant_name"]
            )
            == normalize_plant(plant)
        ]

        explicit = [
            r
            for r in plant_records
            if normalize_part(
                r["plant_part"]
            )
        ]

        blanks = [
            r
            for r in plant_records
            if not normalize_part(
                r["plant_part"]
            )
        ]

        print(
            f"    IMPPAT records: "
            f"{len(plant_records)}"
        )

        print(
            f"    Explicit part records: "
            f"{len(explicit)}"
        )

        print(
            f"    Plant-level records: "
            f"{len(blanks)}"
        )

        plant_rows = df[
            df["plant_name"]
            .map(normalize_plant)
            == normalize_plant(plant)
        ]

        for _, pr in plant_rows.iterrows():
            requested_part = pr[
                "plant_part"
            ]

            exact = get_explicit(
                plant_records,
                requested_part,
            )

            print(
                f"      {requested_part}: "
                f"exact={len(exact)}"
            )

            exact_keys = set()

            for r in exact:
                key = (
                    pr["plant_part_id"],
                    r["imppat_id"],
                    normalize_part(
                        requested_part
                    ),
                )

                exact_keys.add(key)

                rows.append({
                    "plant_part_id":
                        pr["plant_part_id"],

                    "plant_name":
                        plant,

                    "plant_part":
                        requested_part,

                    "imppat_id":
                        r["imppat_id"],

                    "phytochemical_name":
                        r["phytochemical_name"],

                    "source_url":
                        (
                            f"{BASE_URL}/phytochemical/"
                            f"{quote(plant, safe='')}"
                        ),

                    "source":
                        "IMPPAT",

                    "references":
                        r["references"],

                    "association_level":
                        "explicit_part",

                    "confidence":
                        "HIGH",

                    "evidence":
                        (
                            "IMPPAT explicitly lists "
                            "plant part "
                            f"'{requested_part}'"
                        ),
                })

            # Examine plant-level records
            # rather than discarding them.
            for b in blanks:
                candidates = (
                    infer_from_shared_reference(
                        plant_records,
                        b,
                    )
                )

                # Only promote if the shared
                # reference points to THIS
                # requested part.
                for matched, overlap in candidates:

                    if (
                        normalize_part(
                            matched["plant_part"]
                        )
                        != normalize_part(
                            requested_part
                        )
                    ):
                        continue

                    key = (
                        pr["plant_part_id"],
                        b["imppat_id"],
                        normalize_part(
                            requested_part
                        ),
                    )

                    if key in exact_keys:
                        continue

                    if not include_inferred:
                        continue

                    inferred_rows.append({
                        "plant_part_id":
                            pr["plant_part_id"],

                        "plant_name":
                            plant,

                        "plant_part":
                            requested_part,

                        "imppat_id":
                            b["imppat_id"],

                        "phytochemical_name":
                            b["phytochemical_name"],

                        "source_url":
                            (
                                f"{BASE_URL}/phytochemical/"
                                f"{quote(plant, safe='')}"
                            ),

                        "source":
                            "IMPPAT",

                        "references":
                            b["references"],

                        "association_level":
                            "reference_inferred",

                        "confidence":
                            "MEDIUM",

                        "evidence":
                            (
                                "Plant-level IMPPAT "
                                "association shares "
                                "reference(s) with "
                                f"explicit '{requested_part}' "
                                "association: "
                                f"{'; '.join(sorted(overlap))}"
                            ),
                    })

            if not exact and not any(
                x["plant_part_id"]
                == pr["plant_part_id"]
                for x in inferred_rows
            ):
                unmatched.append({
                    "plant_part_id":
                        pr["plant_part_id"],

                    "plant_name":
                        plant,

                    "plant_part":
                        requested_part,

                    "reason":
                        "No explicit part match; "
                        "no reference-supported "
                        "inference",
                })

        # Preserve all plant-level records
        # for audit instead of silently assigning them.
        for b in blanks:
            plant_level_candidates.append({
                "plant_name":
                    plant,

                "plant_part":
                    "",

                "imppat_id":
                    b["imppat_id"],

                "phytochemical_name":
                    b["phytochemical_name"],

                "source_url":
                    (
                        f"{BASE_URL}/phytochemical/"
                        f"{quote(plant, safe='')}"
                    ),

                "references":
                    b["references"],

                "reason":
                    "IMPPAT associates compound "
                    "with plant but gives no "
                    "plant part",
            })

        # Checkpoint every plant.
        checkpoint = pd.DataFrame(
            rows + inferred_rows,
            columns=OUTPUT_COLUMNS,
        )

        checkpoint = (
            checkpoint.drop_duplicates()
        )

        checkpoint.to_excel(
            checkpoint_file,
            index=False,
        )

    audit_path = os.path.splitext(output_file)[0] + "_id_reconciliation_audit.xlsx"
    audit_df = pd.DataFrame(
        id_reconciliation_audit,
        columns=[
            "plant_name", "plant_part", "legacy_or_unknown_id",
            "phytochemical_name", "candidate_current_ids", "reason",
        ],
    )
    audit_df.to_excel(audit_path, index=False)

    if id_reconciliation_audit:
        raise RuntimeError(
            f"IMPPAT ID reconciliation found {len(id_reconciliation_audit)} "
            f"unresolved ID/name combination(s). See {os.path.abspath(audit_path)}. "
            "No final mapping was published; the partial checkpoint is retained "
            f"at {os.path.abspath(checkpoint_file)}."
        )

    # Final main mapping; this is written only after identifier validation passes.
    result = pd.DataFrame(
        rows + inferred_rows,
        columns=OUTPUT_COLUMNS,
    )

    if not result.empty:
        result = (
            result.drop_duplicates(
                subset=[
                    "plant_part_id",
                    "imppat_id",
                    "association_level",
                ]
            )
            .sort_values(
                [
                    "plant_part_id",
                    "phytochemical_name",
                ]
            )
            .reset_index(drop=True)
        )

    result.to_excel(
        output_file,
        index=False,
    )
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    # Audit sheets are separate files so
    # the main mapping stays clean.
    pd.DataFrame(
        unmatched
    ).to_excel(
        os.path.splitext(
            output_file
        )[0] + "_unmatched.xlsx",
        index=False,
    )

    pd.DataFrame(
        inferred_rows,
        columns=OUTPUT_COLUMNS,
    ).to_excel(
        os.path.splitext(
            output_file
        )[0] + "_inferred.xlsx",
        index=False,
    )

    pd.DataFrame(
        plant_level_candidates
    ).drop_duplicates().to_excel(
        os.path.splitext(
            output_file
        )[0] + "_plant_level_candidates.xlsx",
        index=False,
    )

    exact_count = len(rows)

    inferred_count = len(
        inferred_rows
    )

    unique_compounds = (
        result["imppat_id"].nunique()
        if not result.empty
        else 0
    )

    print("\n" + "=" * 78)
    print("DONE")
    print("=" * 78)

    print(
        f"Explicit part mappings : "
        f"{exact_count}"
    )

    print(
        f"Reference-inferred     : "
        f"{inferred_count}"
    )

    print(
        f"Total main mappings    : "
        f"{len(result)}"
    )

    print(
        f"Unique phytochemicals  : "
        f"{unique_compounds}"
    )
    print(
        f"Already-current IDs   : {id_resolution_counts['already_current']} record(s)"
    )
    print(
        f"Legacy IDs upgraded   : {id_resolution_counts['legacy_upgraded']} record(s)"
    )
    print(
        f"ID reconciliation audit: {os.path.abspath(audit_path)} (0 unresolved)"
    )

    print(
        f"Unmatched plant-parts  : "
        f"{len(unmatched)}"
    )

    print(
        f"Plant-level candidates : "
        f"{len(plant_level_candidates)}"
    )

    print(
        f"Main output            : "
        f"{os.path.abspath(output_file)}"
    )

    print("=" * 78)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--file",
        required=True,
    )

    parser.add_argument(
        "--output",
        default="Phytochemical_Mapping.xlsx",
    )

    parser.add_argument(
        "--no-inferred",
        action="store_true",
        help=(
            "Disable conservative "
            "reference-supported inference"
        ),
    )

    args = parser.parse_args()

    build(
        args.file,
        args.output,
        include_inferred=not args.no_inferred,
    )


if __name__ == "__main__":
    main()