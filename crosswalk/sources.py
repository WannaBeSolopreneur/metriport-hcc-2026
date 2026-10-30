"""Pinned public inputs. Every file is checked against a sha256 before use."""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

# Local copy used only if the CMS download fails. Override with HCC_FALLBACK_DIR.
FALLBACK_DIR = Path(os.environ.get("HCC_FALLBACK_DIR", "/workspace/verify"))

USER_AGENT = "Mozilla/5.0 (metriport-hcc-2026; +https://github.com/WannaBeSolopreneur)"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    sha256: str
    filename: str
    member: str | None = None  # file inside the zip, if any
    fallback: str | None = None  # file name inside FALLBACK_DIR


CMS_2026 = Source(
    name="CMS 2026 Midyear/Final ICD-10-CM to HCC mappings",
    url="https://www.cms.gov/files/zip/2026-midyear-final-icd-10-mappings.zip",
    sha256="1143bc102311fa6f9da33ef7c72cb4a34849a4354feb0ef1c745d38c887f23a2",
    filename="cms_2026_midyear_final_icd10_mappings.zip",
    member="2026 Final ICD-10-CM Mappings.csv",
    fallback="map26.zip",
)

CMS_2025 = Source(
    name="CMS 2025 Midyear/Final ICD-10-CM to HCC mappings",
    url="https://www.cms.gov/files/zip/2025-midyear/final-icd-10-mappings.zip-0",
    sha256="3fd8a313d8476332243fd4ad139cb3c71bd3597e1e1164c6e9f844a66de0b8ac",
    filename="cms_2025_midyear_final_icd10_mappings.zip",
    member="2025 Midyear_Final ICD-10-CM Mappings.csv",
    fallback="map25.zip",
)

# Official ICD-10-CM code lists (CDC/CMS). Used to tell which codes are valid in a fiscal year
# and which were added or deleted on Oct 1 of that year.
ICD10CM_2026 = Source(
    name="ICD-10-CM FY2026 code descriptions in tabular order",
    url="https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order.zip",
    sha256="55a9124a27ca78a4a5c41e1101eda064ec2e08d105ff9e78d1fbd1a83298ef11",
    filename="icd10cm_2026_code_descriptions.zip",
    member="icd10cm_codes_2026.txt",
    fallback="2026-code-descriptions-tabular-order.zip",
)

ICD10CM_2025 = Source(
    name="ICD-10-CM FY2025 code descriptions in tabular order",
    url="https://www.cms.gov/files/zip/2025-code-descriptions-tabular-order.zip",
    sha256="4f6c65f0034736d2b02fa9eb1128aab564fa673dd4d99363f8b2167af3994816",
    filename="icd10cm_2025_code_descriptions.zip",
    member="icd10cm_codes_2025.txt",
    fallback="2025-code-descriptions-tabular-order.zip",
)

METRIPORT_COMMIT = "e1f26d504cb9d132d66a7a9607ffb199be759168"
METRIPORT_HCC_MAP_PATH = "packages/core/src/external/fhir/shared/hcc-map.ts"
METRIPORT_HCC_MAP = Source(
    name=f"Metriport hcc-map.ts at {METRIPORT_COMMIT[:7]}",
    url=(
        "https://raw.githubusercontent.com/metriport/metriport/"
        f"{METRIPORT_COMMIT}/{METRIPORT_HCC_MAP_PATH}"
    ),
    sha256="8ddc36082f70ab3c2df9b80a5d8943e9da6e8116e433955a32ce0bb3f2a0f15c",
    filename=f"metriport_hcc-map_{METRIPORT_COMMIT[:7]}.ts",
)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(src: Source) -> tuple[Path, str]:
    """Return (local path, origin). Origin is 'cache', 'download' or 'fallback'.

    The file must match the pinned sha256, whatever its origin.
    """
    CACHE.mkdir(exist_ok=True)
    dest = CACHE / src.filename
    if dest.exists() and sha256_of(dest) == src.sha256:
        return dest, "cache"
    origin = "download"
    try:
        req = urllib.request.Request(src.url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
    except Exception as exc:
        fb = FALLBACK_DIR / src.fallback if src.fallback else None
        if fb is None or not fb.exists():
            raise RuntimeError(f"Download failed for {src.url} and no local fallback") from exc
        print(
            f"WARNING: download of {src.url} failed ({exc}). Using local copy {fb}.",
            file=sys.stderr,
        )
        dest.write_bytes(fb.read_bytes())
        origin = "fallback"
    got = sha256_of(dest)
    if got != src.sha256:
        dest.unlink()
        raise RuntimeError(f"sha256 mismatch for {src.name}: expected {src.sha256}, got {got}")
    return dest, origin
