"""Flatten Patient, Condition and Encounter resources into flat rows.

Column names follow the style of Metriport's fhir-to-csv configs (lower case, path joined
with underscores). Every value is a string or None, like the CSV output.
"""

from __future__ import annotations

from collections.abc import Callable

ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
SNOMED_SYSTEM = "http://snomed.info/sct"


def _s(v) -> str | None:
    if v is None or v == "":
        return None
    return str(v)


def _ref_id(ref: dict | None) -> str | None:
    if not ref or not ref.get("reference"):
        return None
    return ref["reference"].rsplit("/", 1)[-1]


def _coding(cc: dict | None, system: str | None = None) -> dict:
    for c in (cc or {}).get("coding") or []:
        if system is None or c.get("system") == system:
            return c
    return {}


def _first(items: list | None) -> dict:
    return (items or [{}])[0]


def patient(r: dict) -> dict:
    name = _first(r.get("name"))
    addr = _first(r.get("address"))
    return {
        "id": _s(r.get("id")),
        "gender": _s(r.get("gender")),
        "birthdate": _s(r.get("birthDate")),
        "name_0_family": _s(name.get("family")),
        "name_0_given_0": _s((name.get("given") or [None])[0]),
        "address_0_state": _s(addr.get("state")),
        "address_0_postalcode": _s(addr.get("postalCode")),
        "meta_lastupdated": _s((r.get("meta") or {}).get("lastUpdated")),
    }


def condition(r: dict) -> dict:
    icd = _coding(r.get("code"), ICD10_SYSTEM)
    sct = _coding(r.get("code"), SNOMED_SYSTEM)
    return {
        "id": _s(r.get("id")),
        "patient_id": _s(_ref_id(r.get("subject"))),
        "encounter_id": _s(_ref_id(r.get("encounter"))),
        "icd10_code": _s(icd.get("code")),
        "icd10_display": _s(icd.get("display")),
        "snomed_code": _s(sct.get("code")),
        "clinicalstatus": _s(_coding(r.get("clinicalStatus")).get("code")),
        "verificationstatus": _s(_coding(r.get("verificationStatus")).get("code")),
        "onsetdatetime": _s(r.get("onsetDateTime")),
        "recordeddate": _s(r.get("recordedDate")),
    }


def encounter(r: dict) -> dict:
    typ = _coding(_first(r.get("type")))
    period = r.get("period") or {}
    return {
        "id": _s(r.get("id")),
        "patient_id": _s(_ref_id(r.get("subject"))),
        "status": _s(r.get("status")),
        "class_code": _s((r.get("class") or {}).get("code")),
        "type_code": _s(typ.get("code")),
        "type_display": _s(typ.get("display")),
        "period_start": _s(period.get("start")),
        "period_end": _s(period.get("end")),
    }


FLATTENERS: dict[str, Callable[[dict], dict]] = {
    "Patient": patient,
    "Condition": condition,
    "Encounter": encounter,
}

COLUMNS: dict[str, list[str]] = {t: list(f({}).keys()) for t, f in FLATTENERS.items()}
