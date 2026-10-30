"""Flatten Patient, Condition and Encounter resources into flat rows.

Column names follow the style of Metriport's fhir-to-csv configs (lower case, path joined
with underscores). Every value is a string or None, like the CSV output.

Patient and Encounter give one row per resource. Condition gives one row per ICD-10-CM
coding. SNOMED is kept in a column. A Condition with no usable ICD-10-CM coding still gives
one row, with icd10_code empty, so it is never lost.

Only ICD-10-CM (the US version) is joined to the HCC table. WHO ICD-10 codings are counted
and skipped, like Metriport's Condition normalization, which only reads ICD-10-CM.
"""

from __future__ import annotations

import re
from collections.abc import Callable

ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
ICD10_OID = "urn:oid:2.16.840.1.113883.6.90"
ICD10_WHO_SYSTEM = "http://hl7.org/fhir/sid/icd-10"
SNOMED_SYSTEM = "http://snomed.info/sct"

# System URIs accepted as ICD-10-CM. Compared after trimming and lower-casing.
ICD10_SYSTEMS: frozenset[str] = frozenset(s.lower() for s in (ICD10_SYSTEM, ICD10_OID))

_SPACES = re.compile(r"\s+")
_CODE = re.compile(r"[A-Z][0-9A-Z]{2}(?:\.?[0-9A-Z]{1,4})?")


def normalize_icd10(code) -> str | None:
    """'e11.9 ' -> 'E119'. Returns None when the code is not a valid shape.

    Spaces are removed and letters are upper-cased. A dot is allowed only after the third
    character, so 'E1.19' is rejected instead of turning into 'E119'.
    """
    if code is None:
        return None
    raw = _SPACES.sub("", str(code)).upper()
    if not _CODE.fullmatch(raw):
        return None
    return raw.replace(".", "")


def _system(system) -> str | None:
    return system.strip().lower() if isinstance(system, str) else None


def is_icd10_system(system) -> bool:
    return _system(system) in ICD10_SYSTEMS


def is_who_icd10_system(system) -> bool:
    return _system(system) == ICD10_WHO_SYSTEM


def _s(v) -> str | None:
    if v is None or v == "":
        return None
    return str(v)


def _dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _ref_id(ref) -> str | None:
    ref = _dict(ref).get("reference")
    if not isinstance(ref, str) or not ref:
        return None
    return ref.rsplit("/", 1)[-1]


def _codings(cc) -> list[dict]:
    return [c for c in _list(_dict(cc).get("coding")) if isinstance(c, dict)]


def _coding(cc, system: str | None = None) -> dict:
    for c in _codings(cc):
        if system is None or c.get("system") == system:
            return c
    return {}


def _first(items) -> dict:
    items = _list(items)
    return _dict(items[0]) if items else {}


def patient(r: dict) -> list[dict]:
    name = _first(r.get("name"))
    addr = _first(r.get("address"))
    given = _list(name.get("given"))
    return [
        {
            "id": _s(r.get("id")),
            "gender": _s(r.get("gender")),
            "birthdate": _s(r.get("birthDate")),
            "name_0_family": _s(name.get("family")),
            "name_0_given_0": _s(given[0] if given else None),
            "address_0_state": _s(addr.get("state")),
            "address_0_postalcode": _s(addr.get("postalCode")),
            "meta_lastupdated": _s(_dict(r.get("meta")).get("lastUpdated")),
        }
    ]


def icd10_codings(r: dict) -> tuple[list[dict], int, int]:
    """ICD-10-CM codings of a Condition, deduplicated on the normalized code.

    Returns (codings, duplicates dropped, WHO ICD-10 codings skipped). Codings with an
    ICD-10-CM system but an empty or invalid code are left out here. The Condition then falls
    back to the one empty row.
    """
    out, seen, dups, who = [], set(), 0, 0
    for c in _codings(r.get("code")):
        if is_who_icd10_system(c.get("system")):
            who += 1
            continue
        if not is_icd10_system(c.get("system")):
            continue
        norm = normalize_icd10(c.get("code"))
        if norm is None:
            continue
        if norm in seen:
            dups += 1
            continue
        seen.add(norm)
        out.append({**c, "_norm": norm})
    return out, dups, who


def condition(r: dict) -> list[dict]:
    return condition_rows(r)[0]


def condition_rows(r: dict) -> tuple[list[dict], int, int]:
    """Rows for one Condition, plus duplicate ICD-10-CM codings dropped and WHO codings skipped."""
    sct = _coding(r.get("code"), SNOMED_SYSTEM)
    base = {
        "id": _s(r.get("id")),
        "patient_id": _s(_ref_id(r.get("subject"))),
        "encounter_id": _s(_ref_id(r.get("encounter"))),
        "coding_index": None,
        "icd10_system": None,
        "icd10_code": None,
        "icd10_code_normalized": None,
        "icd10_display": None,
        "snomed_code": _s(sct.get("code")),
        "clinicalstatus": _s(_coding(r.get("clinicalStatus")).get("code")),
        "verificationstatus": _s(_coding(r.get("verificationStatus")).get("code")),
        "onsetdatetime": _s(r.get("onsetDateTime")),
        "recordeddate": _s(r.get("recordedDate")),
    }
    codings, dups, who = icd10_codings(r)
    if not codings:
        return [base], dups, who
    rows = [
        {
            **base,
            "coding_index": str(i),
            "icd10_system": _s(c.get("system")),
            "icd10_code": _s(c.get("code")),
            "icd10_code_normalized": c["_norm"],
            "icd10_display": _s(c.get("display")),
        }
        for i, c in enumerate(codings)
    ]
    return rows, dups, who


def encounter(r: dict) -> list[dict]:
    typ = _coding(_first(r.get("type")))
    period = _dict(r.get("period"))
    return [
        {
            "id": _s(r.get("id")),
            "patient_id": _s(_ref_id(r.get("subject"))),
            "status": _s(r.get("status")),
            "class_code": _s(_dict(r.get("class")).get("code")),
            "type_code": _s(typ.get("code")),
            "type_display": _s(typ.get("display")),
            "period_start": _s(period.get("start")),
            "period_end": _s(period.get("end")),
        }
    ]


FLATTENERS: dict[str, Callable[[dict], list[dict]]] = {
    "Patient": patient,
    "Condition": condition,
    "Encounter": encounter,
}

COLUMNS: dict[str, list[str]] = {t: list(f({})[0].keys()) for t, f in FLATTENERS.items()}
