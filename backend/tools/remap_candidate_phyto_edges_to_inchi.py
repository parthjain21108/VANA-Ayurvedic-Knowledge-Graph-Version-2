#!/usr/bin/env python3
"""Safely copy a Master output folder and remap current-IMPPAT edge IDs to InChIKey.

This is a compatibility bridge for the already-created candidate run. It never
modifies the source run. It aborts unless the current Phytochemicals table has
nonblank unique InChIKeys and unique current IMPPAT IDs, and every edge maps 1:1.
"""
from __future__ import annotations
import argparse, csv, shutil
from pathlib import Path

EDGE_FIELDS = {
    "CONTAINS.csv": "Destination Id",
    "HAS_BIOACTIVITY.csv": "Source Id",
}

def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader=csv.DictReader(f)
        return (reader.fieldnames or []), list(reader)

def write_csv(path: Path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer=csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
        writer.writeheader(); writer.writerows(rows)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args=parser.parse_args()
    src=args.source.resolve(); dst=args.destination.resolve()
    if not src.is_dir(): raise SystemExit(f"STOP: source output missing: {src}")
    if dst.exists(): raise SystemExit(f"STOP: destination already exists; refusing overwrite: {dst}")
    columns, phyto=read_csv(src/"Phytochemicals.csv")
    for field in ("imppat_id","inchi_key"):
        if field not in columns: raise SystemExit(f"STOP: Phytochemicals.csv missing {field}")
    def norm(x): return str(x or "").strip()
    imppat_to_inchi={}
    seen_inchi=set(); seen_ids=set()
    for row in phyto:
        imp=norm(row["imppat_id"]).upper(); inch=norm(row["inchi_key"]).upper()
        if not imp.startswith("IMPPAT") or not imp or not inch or inch in {"NA","N/A","NAN","NONE","NULL"}:
            raise SystemExit(f"STOP: blank/invalid mapping row: imppat_id={imp!r}, inchi_key={inch!r}")
        if imp in seen_ids: raise SystemExit(f"STOP: duplicate IMPPAT ID in phytochemicals: {imp}")
        if inch in seen_inchi: raise SystemExit(f"STOP: duplicate InChIKey violates VANA identity contract: {inch}")
        seen_ids.add(imp); seen_inchi.add(inch); imppat_to_inchi[imp]=norm(row["inchi_key"])
    shutil.copytree(src,dst)
    changed={}
    try:
        for filename, col in EDGE_FIELDS.items():
            path=dst/filename
            fields, rows=read_csv(path)
            if col not in fields: raise RuntimeError(f"{filename} missing {col}")
            missing=[]
            for row in rows:
                value=norm(row[col]).upper()
                if not value or value not in imppat_to_inchi:
                    missing.append(value)
                else:
                    row[col]=imppat_to_inchi[value]
            if missing:
                raise RuntimeError(f"{filename} has {len(missing)} unmapped endpoints; examples={missing[:5]}")
            write_csv(path,fields,rows)
            changed[filename]=len(rows)
        # Ensure output endpoint sets now resolve to the unique InChIKey node set.
        keyset={norm(r["inchi_key"]).upper() for r in phyto}
        for filename,col in EDGE_FIELDS.items():
            _, rows=read_csv(dst/filename)
            bad=[norm(r[col]) for r in rows if norm(r[col]).upper() not in keyset]
            if bad: raise RuntimeError(f"{filename} post-remap endpoint validation failed: {bad[:5]}")
        print("REMAPPED CANDIDATE CREATED (source left untouched)")
        print(f"source={src}"); print(f"destination={dst}")
        print(f"Phytochemicals={len(phyto)}; unique InChIKeys={len(seen_inchi)}; IMPPAT IDs={len(seen_ids)}")
        for name,count in changed.items(): print(f"{name}: {count} rows remapped")
    except BaseException:
        shutil.rmtree(dst,ignore_errors=True)
        raise
if __name__=="__main__": main()
