import os
import uuid

import pytest

from lmi import csv_import, synthetic

os.environ.setdefault("LMI_RCN", "0")  # testy nie odpytują geoportalu (RCN odświeża się w poniedziałki)


@pytest.fixture(scope="session")
def synthetic_data(tmp_path_factory):
    """Dane syntetyczne (seed 42) sparsowane do listy dictów jak z core.listing_observations."""
    out = tmp_path_factory.mktemp("synthetic")
    paths = synthetic.generate(out, seed=42)
    rows = []
    for src in synthetic.SOURCES:
        parsed = csv_import.parse_file(paths[src])
        assert parsed.ok, parsed.errors[:5]
        for o in parsed.observations:
            d = dict(o.__dict__)
            d["source_id"] = src
            rows.append(d)
    return {"paths": paths, "rows": rows, "truth": synthetic.load_ground_truth(paths["ground_truth"])}


@pytest.fixture
def pg_conn():
    """Świeża baza na każdy test. Wymaga LMI_TEST_DATABASE_URL (użytkownik z prawem CREATE DATABASE)."""
    url = os.environ.get("LMI_TEST_DATABASE_URL")
    if not url:
        pytest.skip("LMI_TEST_DATABASE_URL nie ustawiony — pomijam testy integracyjne")
    import psycopg

    from lmi import db

    name = f"lmi_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    test_url = url.rsplit("/", 1)[0] + "/" + name
    conn = psycopg.connect(test_url)
    conn.test_url = test_url  # dla testów, które łączą się same (np. strona)
    db.apply_schema(conn)
    try:
        yield conn
    finally:
        conn.close()
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
