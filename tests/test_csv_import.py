import pytest

from lmi.csv_import import CsvFormatError, parse_bytes

HEADER = "source_listing_id,observed_at,municipality_teryt,municipality_name,parcel_id,lat,lon,area_m2,price_pln\n"


def parse(body: str, header: str = HEADER):
    return parse_bytes((header + body).encode("utf-8"))


def test_valid_row():
    r = parse("A1,2026-03-02,1465011,Warszawa,146501_1.0001.12/3,52.2,21.0,1200,360000\n")
    assert r.ok and len(r.observations) == 1
    o = r.observations[0]
    assert o.area_m2 == 1200 and o.price_pln == 360000 and o.parcel_id == "146501_1.0001.12/3"


def test_polish_number_format_and_semicolon():
    header = HEADER.replace(",", ";")
    r = parse('A1;2026-03-02;1465011;Warszawa;;52,2;21,0;"1 200,5";360000\n', header)
    assert r.ok, r.errors
    assert r.observations[0].area_m2 == 1200.5
    assert r.observations[0].lat == 52.2


def test_optional_columns_may_be_missing():
    header = "source_listing_id,observed_at,municipality_teryt,municipality_name,area_m2,price_pln\n"
    r = parse("A1,2026-03-02,1465011,Warszawa,1000,100000\n", header)
    assert r.ok and r.observations[0].lat is None


def test_missing_required_column():
    with pytest.raises(CsvFormatError, match="price_pln"):
        parse("A1,2026-03-02,1465011,Warszawa,1000\n",
              "source_listing_id,observed_at,municipality_teryt,municipality_name,area_m2\n")


@pytest.mark.parametrize(
    "row, message",
    [
        ("A1,02.03.2026,1465011,W,,,,1000,1\n", "RRRR-MM-DD"),
        ("A1,2026-03-02,14650,W,,,,1000,1\n", "7 cyfr"),
        ("A1,2026-03-02,1465011,W,,,,0,1\n", "area_m2 musi być > 0"),
        ("A1,2026-03-02,1465011,W,,,,1000,-5\n", "price_pln musi być > 0"),
        ("A1,2026-03-02,1465011,W,,52.2,,1000,1\n", "razem"),
        ("A1,2026-03-02,1465011,W,,21.0,52.2,1000,1\n", "poza Polską"),
        ("A1,2026-03-02,1465011,W,,,,dużo,1\n", "liczbami"),
        (",2026-03-02,1465011,W,,,,1000,1\n", "puste pole source_listing_id"),
    ],
)
def test_invalid_rows(row, message):
    r = parse(row)
    assert not r.ok
    assert message in r.errors[0]


def test_duplicate_in_file():
    r = parse("A1,2026-03-02,1465011,W,,,,1000,1\nA1,2026-03-02,1465011,W,,,,1000,1\n")
    assert len(r.observations) == 1 and "duplikat" in r.errors[0]


def test_errors_do_not_stop_parsing():
    r = parse("A1,zła-data,1465011,W,,,,1000,1\nA2,2026-03-02,1465011,W,,,,1000,1\n")
    assert len(r.errors) == 1 and len(r.observations) == 1
    assert r.errors[0].startswith("wiersz 2:")
