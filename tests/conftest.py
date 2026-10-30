from pathlib import Path

import pytest

from compare.metriport_map import parse_hcc_map
from crosswalk.build import build_rows
from crosswalk.cms import read_cms_csv
from crosswalk.sources import CMS_2025, CMS_2026, METRIPORT_HCC_MAP, fetch


@pytest.fixture(scope="session")
def cms26():
    path, _ = fetch(CMS_2026)
    return read_cms_csv(path, CMS_2026.member)


@pytest.fixture(scope="session")
def cms25_rows():
    path, _ = fetch(CMS_2025)
    return read_cms_csv(path, CMS_2025.member)[1]


@pytest.fixture(scope="session")
def crosswalk(cms26):
    header, rows = cms26
    return build_rows(rows, header)


@pytest.fixture(scope="session")
def hcc_map():
    path, _ = fetch(METRIPORT_HCC_MAP)
    return parse_hcc_map(Path(path).read_text(encoding="utf-8"))
