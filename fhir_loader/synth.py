"""Generate synthetic, Metriport-shaped FHIR NDJSON: one file per patient, one bundle entry
({"fullUrl", "resource"}) per line, covering all 28 resource types the fhir-to-csv step handles.

A small share of the data is messy on purpose, the way real feeds are: Conditions with two
ICD-10 codings, the OID or WHO ICD-10 system name, lowercase or spaced codes, Conditions with
no ICD-10 code, files with a byte order mark, files of plain unwrapped resources, and the odd
blank or non-object line.

Fully deterministic for a given seed. No real patient data is involved.
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import uuid
from pathlib import Path

from fhir_loader.flatten import ICD10_OID, ICD10_SYSTEM, ICD10_WHO_SYSTEM, SNOMED_SYSTEM
from fhir_loader.resource_types import RESOURCE_TYPES

STATES = ["TX", "IL", "CA", "NY", "FL", "OH", "GA", "WA", "AZ", "MI"]
FAMILY = ["Garcia", "Smith", "Nguyen", "Patel", "Johnson", "Kim", "Lopez", "Brown", "Khan"]
GIVEN = ["Maria", "James", "Linh", "Ravi", "Ana", "John", "Aisha", "Wei", "Grace", "Omar"]
ENC_TYPES = [("185349003", "Encounter for check up"), ("50849002", "Emergency room admission")]
NON_HCC_CODES = [("I10", "Essential (primary) hypertension"), ("J06.9", "Acute URI, unspecified")]


def _uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _date(rng: random.Random, start: int = 2015, end: int = 2026) -> str:
    return f"{rng.randint(start, end)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def _dotted(code: str) -> str:
    return code if len(code) <= 3 else f"{code[:3]}.{code[3:]}"


def _meta(rng: random.Random) -> dict:
    return {
        "versionId": str(rng.randint(1, 5)),
        "lastUpdated": f"{_date(rng, 2024)}T{rng.randint(0, 23):02d}:00:00.000Z",
        "source": f"urn:oid:2.16.840.1.113883.3.{rng.randint(1000, 9999)}",
    }


def _base(rng: random.Random, rtype: str, pid: str) -> dict:
    rid = _uuid(rng)
    return {
        "resourceType": rtype,
        "id": rid,
        "meta": _meta(rng),
        "identifier": [{"system": "urn:ietf:rfc:3986", "value": f"urn:uuid:{rid}"}],
        "text": {"status": "generated", "div": f"<div>{rtype} for patient {pid}</div>"},
    }


def make_patient(rng: random.Random, pid: str) -> dict:
    r = _base(rng, "Patient", pid)
    r["id"] = pid
    r.update(
        {
            "name": [{"family": rng.choice(FAMILY), "given": [rng.choice(GIVEN)]}],
            "gender": rng.choice(["male", "female"]),
            "birthDate": _date(rng, 1935, 1960),
            "address": [
                {
                    "line": [f"{rng.randint(1, 9999)} Main St"],
                    "city": "Springfield",
                    "state": rng.choice(STATES),
                    "postalCode": f"{rng.randint(10000, 99999)}",
                }
            ],
            "telecom": [{"system": "phone", "value": f"555-{rng.randint(1000, 9999)}"}],
        }
    )
    return r


def make_encounter(rng: random.Random, pid: str) -> dict:
    r = _base(rng, "Encounter", pid)
    code, display = rng.choice(ENC_TYPES)
    start = _date(rng)
    r.update(
        {
            "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
            "type": [{"coding": [{"system": SNOMED_SYSTEM, "code": code, "display": display}]}],
            "subject": {"reference": f"Patient/{pid}"},
            "period": {"start": f"{start}T09:00:00Z", "end": f"{start}T09:30:00Z"},
        }
    )
    return r


def _messy_code(rng: random.Random, code: str) -> str:
    x = rng.random()
    if x < 0.05:
        return f" {_dotted(code).lower()} "
    if x < 0.15:
        return code
    return _dotted(code)


def _icd_coding(rng: random.Random, code: str, display: str) -> dict:
    x = rng.random()
    system = ICD10_OID if x < 0.04 else ICD10_WHO_SYSTEM if x < 0.07 else ICD10_SYSTEM
    return {"system": system, "code": _messy_code(rng, code), "display": display}


def make_condition(rng, pid, enc_ids, icd_codes) -> dict:
    r = _base(rng, "Condition", pid)
    if rng.random() < 0.85:
        code, display = rng.choice(icd_codes)
    else:
        code, display = rng.choice(NON_HCC_CODES)
    coding = [_icd_coding(rng, code, display)]
    x = rng.random()
    if x < 0.10:
        # Two ICD-10 codings on one Condition, for example hypertension plus diabetes.
        coding.append(_icd_coding(rng, *rng.choice(icd_codes + NON_HCC_CODES)))
    elif x < 0.13:
        coding = []  # SNOMED only, no ICD-10 code
    elif x < 0.14:
        coding = [{"system": ICD10_SYSTEM, "display": display}]  # ICD-10 system, no code
    if rng.random() < 0.5 or not coding:
        coding.insert(0, {"system": SNOMED_SYSTEM, "code": str(rng.randint(10**8, 10**9))})
    r.update(
        {
            "clinicalStatus": {"coding": [{"code": rng.choice(["active", "resolved"])}]},
            "verificationStatus": {"coding": [{"code": "confirmed"}]},
            "code": {"coding": coding, "text": display},
            "subject": {"reference": f"Patient/{pid}"},
            "onsetDateTime": f"{_date(rng)}T00:00:00Z",
            "recordedDate": _date(rng),
        }
    )
    if enc_ids:
        r["encounter"] = {"reference": f"Encounter/{rng.choice(enc_ids)}"}
    return r


def make_other(rng: random.Random, rtype: str, pid: str) -> dict:
    r = _base(rng, rtype, pid)
    if rtype == "Binary":
        r["contentType"] = "text/plain"
        r["data"] = base64.b64encode(rng.randbytes(600)).decode()
        return r
    r.update(
        {
            "status": "final",
            "subject": {"reference": f"Patient/{pid}"},
            "code": {
                "coding": [{"system": "http://loinc.org", "code": f"{rng.randint(1000, 99999)}-1"}]
            },
            "effectiveDateTime": f"{_date(rng)}T00:00:00Z",
        }
    )
    if rtype == "Observation":
        r["valueQuantity"] = {"value": round(rng.uniform(1, 200), 1), "unit": "mg/dL"}
    return r


def patient_entries(rng: random.Random, icd_codes: list[tuple[str, str]]) -> list[dict]:
    pid = _uuid(rng)
    resources = [make_patient(rng, pid)]
    encounters = [make_encounter(rng, pid) for _ in range(rng.randint(5, 20))]
    resources += encounters
    enc_ids = [e["id"] for e in encounters]
    resources += [make_condition(rng, pid, enc_ids, icd_codes) for _ in range(rng.randint(5, 25))]
    for rtype in RESOURCE_TYPES:
        if rtype in ("Patient", "Encounter", "Condition"):
            continue
        n = rng.randint(20, 60) if rtype == "Observation" else rng.randint(0, 4)
        resources += [make_other(rng, rtype, pid) for _ in range(n)]
    rng.shuffle(resources)
    return [{"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in resources]


def generate(out_dir: Path, patients: int, icd_codes: list[tuple[str, str]], seed: int = 2026):
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    paths = []
    for i in range(patients):
        path = out_dir / f"patient_{i:05d}.ndjson"
        entries = patient_entries(rng, icd_codes)
        x = rng.random()
        with open(path, "w", encoding="utf-8") as f:
            if x < 0.02:
                f.write("\ufeff")  # byte order mark
            for entry in entries:
                # 2% of files are plain NDJSON resources, not bundle entries.
                f.write(json.dumps(entry["resource"] if 0.02 <= x < 0.04 else entry) + "\n")
            if 0.04 <= x < 0.05:
                f.write("\n[]\n")  # a blank line and a non-object line
        paths.append(path)
    return paths


def crosswalk_codes(crosswalk_parquet: Path) -> list[tuple[str, str]]:
    import pyarrow.parquet as pq

    t = pq.read_table(crosswalk_parquet, columns=["code", "display"]).to_pylist()
    return sorted({(r["code"], r["display"]) for r in t})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(".cache/synthetic"))
    ap.add_argument("--patients", type=int, default=2000)
    ap.add_argument("--crosswalk", type=Path, default=Path("data/hcc_crosswalk_2026.parquet"))
    args = ap.parse_args()
    generate(args.out, args.patients, crosswalk_codes(args.crosswalk))


if __name__ == "__main__":
    main()
