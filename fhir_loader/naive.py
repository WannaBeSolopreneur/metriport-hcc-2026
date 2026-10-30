"""Baseline: a faithful re-implementation of the file access pattern in Metriport's
packages/data-transformation/fhir-to-csv/src/parseNdjsonBundle/parseNdjsonBundle.py
(commit e1f26d5, lines 30 to 87).

For each patient NDJSON file it:
1. reads the file until it finds the Patient resource, to get the patient id,
2. for each of the 28 base resource types, reads the whole file again, json-parses every
   line, and writes the matching resources to a temp NDJSON file,
3. parses that temp file into a per-patient CSV (QUOTE_ALL, like parseFhir.py),
4. deletes the temp file.

Only Patient, Condition and Encounter are flattened here, with the same flatteners the
single-pass loader uses, so the comparison isolates the cost of re-reading the file.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from fhir_loader.flatten import COLUMNS, FLATTENERS
from fhir_loader.resource_types import RESOURCE_TYPES


def parse_file(input_path: Path, out_dir: Path, types=RESOURCE_TYPES) -> dict[str, list[dict]]:
    patient_id = None
    with open(input_path) as infile:
        for line in infile:
            try:
                resource = json.loads(line).get("resource", {})
            except json.JSONDecodeError:
                continue
            if resource.get("resourceType") == "Patient" and resource.get("id"):
                patient_id = resource["id"].removeprefix("Patient/")
                break

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list[dict]] = {t: [] for t in FLATTENERS}
    for resource_type in types:
        filtered = out_dir / f"temp_{resource_type.lower()}.ndjson"
        with open(input_path) as infile, open(filtered, "w") as outfile:
            for line in infile:
                try:
                    resource = json.loads(line).get("resource", {})
                except json.JSONDecodeError:
                    continue
                if resource.get("resourceType") == resource_type:
                    if resource_type == "Binary" and patient_id:
                        resource["patient_id"] = patient_id
                    outfile.write(json.dumps(resource) + "\n")
        if resource_type in FLATTENERS:
            flatten = FLATTENERS[resource_type]
            with (
                open(filtered, encoding="utf-8-sig") as f,
                open(out_dir / f"{resource_type.lower()}.csv", "w", newline="") as csvfile,
            ):
                writer = csv.writer(csvfile, escapechar="\\", quoting=csv.QUOTE_ALL)
                writer.writerow(COLUMNS[resource_type])
                for line in f:
                    row = flatten(json.loads(line))
                    rows[resource_type].append(row)
                    writer.writerow(list(row.values()))
        os.remove(filtered)
    return rows


def run(files: list[Path], out_dir: Path, types=RESOURCE_TYPES) -> dict[str, list[dict]]:
    all_rows: dict[str, list[dict]] = {t: [] for t in FLATTENERS}
    for path in files:
        got = parse_file(path, out_dir / path.stem, types)
        for t, r in got.items():
            all_rows[t].extend(r)
    return all_rows
