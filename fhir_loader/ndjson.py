"""Read FHIR NDJSON lines safely, and count everything that is skipped.

Both loaders use this, so they read exactly the same resources from the same file.

A line can be:
- a bundle entry, {"fullUrl": ..., "resource": {...}}, which is what Metriport writes,
- a plain resource, {"resourceType": ...}, which other NDJSON exports write,
- blank, broken JSON, bad UTF-8, or JSON that is not an object. These are skipped and counted.

A UTF-8 byte order mark (BOM) is removed at the start of a file and at the start of any line,
for example when files were joined together.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("fhir_loader")

BOM = "\ufeff"


@dataclass
class LoadStats:
    files: int = 0
    lines: int = 0
    resources: int = 0
    blank_lines: int = 0
    bom_lines: int = 0
    bad_json_lines: int = 0
    bad_utf8_lines: int = 0
    non_object_lines: int = 0
    unwrapped_lines: int = 0
    entries_without_resource: int = 0
    resources_without_type: int = 0
    rows: dict[str, int] = field(default_factory=dict)
    conditions: int = 0
    conditions_without_icd10: int = 0
    icd10_codings: int = 0
    duplicate_icd10_codings: int = 0
    who_icd10_codings_skipped: int = 0

    @property
    def skipped_lines(self) -> int:
        return (
            self.blank_lines
            + self.bad_json_lines
            + self.bad_utf8_lines
            + self.non_object_lines
            + self.entries_without_resource
            + self.resources_without_type
        )

    def as_dict(self) -> dict:
        return {**asdict(self), "skipped_lines": self.skipped_lines}

    def log_summary(self) -> None:
        """Log one warning per kind of problem. Silent when the input was clean."""
        checks = [
            (self.bad_json_lines, "lines were not valid JSON and were skipped"),
            (self.bad_utf8_lines, "lines were not valid UTF-8 and were skipped"),
            (self.non_object_lines, "lines were JSON but not an object and were skipped"),
            (self.entries_without_resource, "entries had no 'resource' object and were skipped"),
            (self.resources_without_type, "resources had no resourceType and were skipped"),
            (
                self.unwrapped_lines,
                'lines were plain resources, not wrapped as {"resource": ...}. '
                "They were read as resources",
            ),
            (
                self.conditions_without_icd10,
                "Conditions had no usable ICD-10 code. They are kept with an empty "
                "icd10_code and get no HCC",
            ),
            (
                self.who_icd10_codings_skipped,
                "codings used WHO ICD-10 (http://hl7.org/fhir/sid/icd-10), not ICD-10-CM. "
                "They were skipped for the HCC join",
            ),
        ]
        for n, msg in checks:
            if n:
                log.warning("%d %s", n, msg)
        if self.blank_lines:
            log.info("%d blank lines skipped", self.blank_lines)
        if self.bom_lines:
            log.info("%d byte order marks removed", self.bom_lines)
        if self.files and not sum(self.rows.values()):
            log.warning(
                "no rows were produced from %d files (%d lines). Check the input format",
                self.files,
                self.lines,
            )


def parse_line(line: str, stats: LoadStats) -> dict | None:
    """Return the resource on this line, or None (and count why)."""
    stats.lines += 1
    if line.startswith(BOM):
        stats.bom_lines += 1
        line = line.lstrip(BOM)
    if not line.strip():
        stats.blank_lines += 1
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        stats.bad_json_lines += 1
        return None
    if not isinstance(obj, dict):
        stats.non_object_lines += 1
        return None
    if "resource" in obj:
        resource = obj["resource"]
        if not isinstance(resource, dict):
            stats.entries_without_resource += 1
            return None
    elif "resourceType" in obj:
        stats.unwrapped_lines += 1
        resource = obj
    else:
        stats.entries_without_resource += 1
        return None
    if not isinstance(resource.get("resourceType"), str) or not resource["resourceType"]:
        stats.resources_without_type += 1
        return None
    stats.resources += 1
    return resource


def iter_resources(path: Path, stats: LoadStats) -> Iterator[dict]:
    stats.files += 1
    with open(path, "rb") as f:
        for raw in f:
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                stats.lines += 1
                stats.bad_utf8_lines += 1
                continue
            resource = parse_line(line, stats)
            if resource is not None:
                yield resource


def flatten_resource(resource: dict, stats: LoadStats) -> list[dict] | None:
    """Flatten one resource if it is a type we keep, and count Condition details."""
    from fhir_loader.flatten import FLATTENERS, condition_rows

    rtype = resource["resourceType"]
    if rtype == "Condition":
        rows, dups, who = condition_rows(resource)
        stats.conditions += 1
        stats.duplicate_icd10_codings += dups
        stats.who_icd10_codings_skipped += who
        if rows[0]["icd10_code_normalized"] is None:
            stats.conditions_without_icd10 += 1
        else:
            stats.icd10_codings += len(rows)
    else:
        flatten = FLATTENERS.get(rtype)
        if flatten is None:
            return None
        rows = flatten(resource)
    stats.rows[rtype] = stats.rows.get(rtype, 0) + len(rows)
    return rows
