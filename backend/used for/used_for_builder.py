#!/usr/bin/env python3

import argparse
import re
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

OUTPUT_COLUMNS = [
    "Source",
    "Source Id",
    "Type",
    "Destination",
    "Destination Id",
    "Label",
    "Description",
]

AUDIT_COLUMNS = [
    "plant_part_id",
    "plant_name",
    "plant_part",
    "therapeutic_use",
    "reason",
]


# ============================================================
# HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def clean_id(value):
    return clean(value).upper()


def normalize(value):
    """
    Normalize text only for matching.
    Does not change the actual stored value.
    """
    value = clean(value)

    if not value:
        return ""

    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def require_columns(
    dataframe,
    required,
    filename,
):
    missing = [
        column
        for column in required
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"{filename} is missing required columns:\n"
            + "\n".join(
                f"  {column}"
                for column in missing
            )
            + "\n\nAvailable columns:\n"
            + "\n".join(
                f"  {column}"
                for column in dataframe.columns
            )
        )


# ============================================================
# LOAD THERAPEUTIC RAW DATA
# ============================================================

def load_fi3(path):
    """Load raw PlantPart -> therapeutic-use associations.

    Current collector format carries a MeSH ID in its own ``mesh_id`` column
    and the human-readable concept in ``therapeutic_use``. Legacy files may
    lack ``mesh_id`` and embed the ID in an identifier bundle in
    ``therapeutic_use``. Both formats are supported.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Therapeutic raw file not found:\n{path}"
        )

    df = pd.read_excel(path)
    df.columns = [str(column).strip() for column in df.columns]

    required = [
        "plant_part_id",
        "plant_name",
        "plant_part",
        "therapeutic_use",
    ]
    require_columns(df, required, path.name)

    # Preserve explicit MeSH IDs from the current collector. Only the legacy
    # format lacks this column; it is supported by the fallback in
    # build_relationships().
    columns = required + (["mesh_id"] if "mesh_id" in df.columns else [])
    df = df[columns].copy()
    if "mesh_id" not in df.columns:
        df["mesh_id"] = ""

    for column in df.columns:
        df[column] = df[column].map(clean)

    df = df[
        (df["plant_part_id"] != "")
        & (df["plant_name"] != "")
        & (df["plant_part"] != "")
        & (df["therapeutic_use"] != "")
    ].copy()

    return df.reset_index(drop=True)


# ============================================================
# LOAD THERAPEUTIC MAPPING
# ============================================================

def load_fi5(path):
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Therapeutic mapping file not found:\n{path}"
        )

    df = pd.read_excel(path)

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    required = [
        "plant_part_id",
        "therapeutic_use",
        "mesh_id",
    ]

    require_columns(
        df,
        required,
        path.name,
    )

    df = df[
        [
            "plant_part_id",
            "therapeutic_use",
            "mesh_id",
        ]
    ].copy()

    for column in df.columns:
        df[column] = df[column].map(clean)

    df = df[
        (df["plant_part_id"] != "")
        & (df["therapeutic_use"] != "")
        & (df["mesh_id"] != "")
    ].copy()

    df["plant_part_id_key"] = (
        df["plant_part_id"].map(clean_id)
    )

    df["mesh_id_key"] = (
        df["mesh_id"].map(clean_id)
    )

    return df.reset_index(drop=True)


# ============================================================
# BUILD LOOKUP
# ============================================================

def build_therapeutic_lookup(fi5):
    """
    Build the authoritative lookup using the actual relationship
    identity:

        PlantPart ID + MeSH ID -> resolved therapeutic use

    The current collector supplies mesh_id explicitly. Legacy raw files may
    instead embed a MeSH ID in an identifier bundle in therapeutic_use; that
    compatibility handling lives in build_relationships(). In neither format
    do we match associations by fuzzy or name-only text.
    """

    lookup = {}

    duplicate_keys = 0

    for _, row in fi5.iterrows():

        plant_part_id = clean_id(
            row["plant_part_id"]
        )

        mesh_id = clean_id(
            row["mesh_id"]
        )

        therapeutic_use = clean(
            row["therapeutic_use"]
        )

        if not plant_part_id:
            continue

        if not mesh_id:
            continue

        key = (
            plant_part_id,
            mesh_id,
        )

        if key in lookup:

            existing = lookup[key]

            if existing != therapeutic_use:
                print(
                    "\nWARNING:"
                )

                print(
                    f"Multiple therapeutic names found "
                    f"for PlantPart={plant_part_id}, "
                    f"MeSH={mesh_id}"
                )

                print(
                    f"Existing: {existing}"
                )

                print(
                    f"New:      {therapeutic_use}"
                )

                print(
                    "Keeping the first name."
                )

            duplicate_keys += 1
            continue

        lookup[key] = therapeutic_use

    print()
    print(
        f"Resolved PlantPart/MeSH mappings: "
        f"{len(lookup)}"
    )

    if duplicate_keys:
        print(
            f"Duplicate mapping rows ignored: "
            f"{duplicate_keys}"
        )

    return lookup


# ============================================================
# BUILD USED_FOR RELATIONSHIPS
# ============================================================

def build_relationships(
    fi3,
    therapeutic_lookup,
):
    relationships = []
    unresolved = []
    seen = set()

    # Reverse index for current-schema rows that have a readable therapeutic
    # concept but no raw MeSH ID. The resolved mapping is authoritative here.
    # Match only by the same PlantPart ID and exact normalized concept label;
    # do not guess by plant, fuzzy text, or a global name-only match.
    name_to_mesh_ids = {}
    for (mapped_plant_part_id, mapped_mesh_id), mapped_use in therapeutic_lookup.items():
        name_key = (clean_id(mapped_plant_part_id), normalize(mapped_use))
        name_to_mesh_ids.setdefault(name_key, set()).add(clean_id(mapped_mesh_id))

    print()
    print("Building PlantPart -> TherapeuticUse relationships...")

    for _, row in fi3.iterrows():
        plant_part_id = clean(row["plant_part_id"])
        plant_name = clean(row["plant_name"])
        plant_part = clean(row["plant_part"])
        raw_therapeutic_use = clean(row["therapeutic_use"])
        explicit_mesh_id = clean(row.get("mesh_id", ""))

        def record_unresolved(reason):
            unresolved.append({
                "plant_part_id": plant_part_id,
                "plant_name": plant_name,
                "plant_part": plant_part,
                "therapeutic_use": raw_therapeutic_use,
                "reason": reason,
            })

        if not plant_part_id:
            record_unresolved("Missing plant_part_id")
            continue

        if not raw_therapeutic_use:
            record_unresolved("Missing therapeutic_use")
            continue

        # Current collector format: use mesh_id as the authoritative ID.
        # Do not derive an ID from a readable concept name if this field is
        # populated but malformed; report it for audit instead.
        if explicit_mesh_id:
            explicit_match = re.fullmatch(
                r"(?:MESH\s*:\s*)?(D\d{6})",
                explicit_mesh_id,
                flags=re.IGNORECASE,
            )
            if not explicit_match:
                record_unresolved(
                    f"Invalid explicit mesh_id value: {explicit_mesh_id!r}"
                )
                continue
            mesh_id = explicit_match.group(1).upper()
        else:
            # Backward compatibility for legacy rows whose therapeutic_use
            # field was an identifier bundle such as
            # 'MESH:D015746, UMLS:C0007681, ICD-11:...'.
            mesh_match = re.search(
                r"\b(?:MESH\s*:\s*)?(D\d{6})\b",
                raw_therapeutic_use,
                flags=re.IGNORECASE,
            )
            if mesh_match:
                mesh_id = mesh_match.group(1).upper()
            else:
                # Current raw data can contain a human-readable therapeutic
                # concept with a blank mesh_id. If the resolved mapping has an
                # exact normalized label for this same PlantPart, use its
                # MeSH ID. Refuse ambiguous matches rather than guessing.
                concept_key = (
                    clean_id(plant_part_id),
                    normalize(raw_therapeutic_use),
                )
                candidate_mesh_ids = name_to_mesh_ids.get(concept_key, set())
                if len(candidate_mesh_ids) == 1:
                    mesh_id = next(iter(candidate_mesh_ids))
                elif len(candidate_mesh_ids) > 1:
                    record_unresolved(
                        "Ambiguous resolved mapping for exact PlantPart + "
                        "therapeutic-use concept: "
                        + ", ".join(sorted(candidate_mesh_ids))
                    )
                    continue
                else:
                    record_unresolved(
                        "No MeSH ID found in mesh_id column or legacy "
                        "identifier bundle, and no exact PlantPart + "
                        "therapeutic-use concept mapping"
                    )
                    continue

        # Relationship identity remains (PlantPart ID, MeSH ID); no fuzzy or
        # name-only matching is introduced.
        key = (clean_id(plant_part_id), clean_id(mesh_id))
        therapeutic_use = therapeutic_lookup.get(key)

        if not therapeutic_use:
            record_unresolved(
                "No matching resolved PlantPart + MeSH mapping"
            )
            continue

        if key in seen:
            continue
        seen.add(key)

        relationships.append({
            "Source": "PlantPart",
            "Source Id": plant_part_id,
            "Type": "USED_FOR",
            "Destination": "TherapeuticUse",
            "Destination Id": mesh_id,
            "Label": "used_for",
            "Description": "Plant part is associated with the respective therapeutic use",
        })

    result = pd.DataFrame(relationships, columns=OUTPUT_COLUMNS)
    audit = pd.DataFrame(unresolved, columns=AUDIT_COLUMNS)
    return result, audit


# ============================================================
# FINAL VALIDATION
# ============================================================

def final_validation(
    result,
    expected_minimum=0,
):
    # expected_minimum is the count of distinct resolved (PlantPart ID, MeSH
    # ID) pairs in the authoritative mapping. If fewer edges are generated,
    # fail instead of treating a partial result as a successful build.
    if len(result) < expected_minimum:
        raise ValueError(
            "USED_FOR completeness validation failed: generated "
            f"{len(result)} relationships but {expected_minimum} distinct "
            "resolved PlantPart/MeSH mappings were available. "
            "Check the unresolved audit and raw mapping schema."
        )

    if result.empty:
        print("\nWARNING: No USED_FOR relationships were generated.")
        return

    if not (result["Source"] == "PlantPart").all():
        raise ValueError("USED_FOR contains invalid Source values.")

    if not (result["Destination"] == "TherapeuticUse").all():
        raise ValueError("USED_FOR contains invalid Destination values.")

    if not (result["Type"] == "USED_FOR").all():
        raise ValueError("USED_FOR contains invalid Type values.")

    invalid_mesh_ids = result[
        ~result["Destination Id"].astype(str).str.fullmatch(r"D\d{6}", na=False)
    ]
    if not invalid_mesh_ids.empty:
        raise ValueError(
            "USED_FOR contains Destination Id values that are not valid-format MeSH IDs."
        )

    duplicates = result[
        result.duplicated(
            subset=["Source Id", "Destination Id", "Type"],
            keep=False,
        )
    ]
    if not duplicates.empty:
        raise ValueError("Duplicate USED_FOR relationships found.")

    print("\nUSED_FOR validation: PASSED")


# ============================================================
# SAVE EXCEL
# ============================================================

def save_excel(
    dataframe,
    output_file,
):
    output_file = Path(
        output_file
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe.to_excel(
        output_file,
        index=False,
        engine="openpyxl",
    )


# ============================================================
# MAIN BUILD
# ============================================================

def build(
    input_file,
    mapping_file,
    output_file,
    audit_file=None,
):

    input_file = Path(
        input_file
    )

    mapping_file = Path(
        mapping_file
    )

    output_file = Path(
        output_file
    )

    if audit_file:
        audit_file = Path(
            audit_file
        )
    else:
        audit_file = (
            output_file.parent
            / "UsedFor_unresolved.xlsx"
        )

    print(
        "=" * 72
    )

    print(
        "USED_FOR RELATIONSHIP BUILDER"
    )

    print(
        "=" * 72
    )

    print()
    print(
        f"Raw therapeutic input:\n"
        f"  {input_file}"
    )

    print(
        f"Therapeutic mapping:\n"
        f"  {mapping_file}"
    )

    print(
        f"Output:\n"
        f"  {output_file}"
    )

    fi3 = load_fi3(
        input_file
    )

    fi5 = load_fi5(
        mapping_file
    )

    print()
    print(
        f"Raw rows:     {len(fi3)}"
    )

    print(
        f"Mapping rows: {len(fi5)}"
    )

    therapeutic_lookup = (
        build_therapeutic_lookup(
            fi5
        )
    )

    if not fi3.empty and not therapeutic_lookup:
        result = pd.DataFrame(columns=OUTPUT_COLUMNS)
        _, unresolved = build_relationships(fi3, therapeutic_lookup)
        save_excel(result, output_file)
        if not unresolved.empty:
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            save_excel(unresolved, audit_file)
        raise ValueError(
            "Raw therapeutic-use associations exist, but the resolved mapping "
            "contains zero usable PlantPart/MeSH pairs. Refusing to treat an "
            "all-zero USED_FOR build as success. See the unresolved audit: "
            f"{audit_file}"
        )

    result, unresolved = build_relationships(fi3, therapeutic_lookup)

    # Save outputs and the unresolved audit before validation can raise. This
    # preserves diagnostic evidence for a rejected partial build.
    save_excel(result, output_file)
    if not unresolved.empty:
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        save_excel(unresolved, audit_file)

    final_validation(
        result,
        expected_minimum=len(therapeutic_lookup),
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print(
        "=" * 72
    )

    print(
        "FINAL RESULT"
    )

    print(
        "=" * 72
    )

    print(
        f"USED_FOR relationships: "
        f"{len(result)}"
    )

    print(
        f"Unresolved rows:         "
        f"{len(unresolved)}"
    )

    print(
        f"Output:                  "
        f"{output_file}"
    )

    if not unresolved.empty:

        print(
            f"Audit:                   "
            f"{audit_file}"
        )

    else:

        print(
            "Audit:                   none"
        )

    print()
    print(
        "Done."
    )


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Build PlantPart -> TherapeuticUse "
            "USED_FOR relationships."
        )
    )

    parser.add_argument(
        "--file",
        required=True,
        help=(
            "Therapeutic_uses_raw.xlsx"
        ),
    )

    parser.add_argument(
        "--mapping",
        required=True,
        help=(
            "Therapeutic_Use_Mapping.xlsx"
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help=(
            "Used_For.xlsx"
        ),
    )

    parser.add_argument(
        "--audit",
        default=None,
        help=(
            "Optional unresolved audit Excel file. "
            "Defaults to UsedFor_unresolved.xlsx"
        ),
    )

    args = parser.parse_args()

    build(
        args.file,
        args.mapping,
        args.output,
        args.audit,
    )


if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:

        print(
            "\nStopped by user."
        )

        raise SystemExit(130)

    except Exception as exc:

        print()
        print(
            "=" * 72
        )

        print(
            "USED_FOR BUILDER FAILED"
        )

        print(
            "=" * 72
        )

        print(
            exc
        )

        raise SystemExit(1)