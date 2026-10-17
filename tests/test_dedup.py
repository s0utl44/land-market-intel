from datetime import date

import pytest

from lmi import dedup
from lmi.dedup import Listing


def L(src, lid, area=1000.0, prices=(100_000.0,), parcel=None, lat=None, lon=None,
      first=date(2026, 3, 2), last=date(2026, 4, 6), muni="1465011"):
    return Listing(src, lid, muni, area, first, last, set(prices), dedup.normalize_parcel_id(parcel), lat, lon)


def groups(links):
    out = {}
    for l in links:
        out.setdefault(l.property_key, set()).add(l.source_listing_id)
    return sorted(sorted(g) for g in out.values())


def test_parcel_id_match_ignores_whitespace_and_case():
    links = dedup.deduplicate([L("a", "1", parcel="146501_1.0001.12/3"), L("b", "2", parcel=" 146501_1.0001.12/3 ", area=5000)])
    assert groups(links) == [["1", "2"]]
    assert {l.match_method for l in links} == {"parcel_id"}


def test_location_match_within_150m():
    # ~100 m na północ
    links = dedup.deduplicate([L("a", "1", lat=52.0, lon=21.0), L("b", "2", lat=52.0009, lon=21.0, area=1030)])
    assert groups(links) == [["1", "2"]]


def test_location_too_far_or_area_too_different():
    assert groups(dedup.deduplicate([L("a", "1", lat=52.0, lon=21.0), L("b", "2", lat=52.002, lon=21.0)])) == [["1"], ["2"]]
    assert groups(dedup.deduplicate([L("a", "1", lat=52.0, lon=21.0), L("b", "2", lat=52.0001, lon=21.0, area=1200)])) == [["1"], ["2"]]


def test_different_parcel_ids_block_location_match():
    links = dedup.deduplicate([L("a", "1", parcel="X/1", lat=52.0, lon=21.0), L("b", "2", parcel="X/2", lat=52.0, lon=21.0)])
    assert groups(links) == [["1"], ["2"]]


def test_price_area_match_when_coords_missing():
    links = dedup.deduplicate([L("a", "1", lat=52.0, lon=21.0), L("b", "2", area=1003, prices=(100_200.0,))])
    assert groups(links) == [["1", "2"]]
    assert {l.match_confidence for l in links} == {0.60}


def test_price_area_not_used_when_both_have_coords():
    links = dedup.deduplicate([L("a", "1", lat=52.0, lon=21.0), L("b", "2", lat=52.1, lon=21.0)])
    assert groups(links) == [["1"], ["2"]]


def test_price_area_requires_overlapping_activity():
    links = dedup.deduplicate([L("a", "1"), L("b", "2", first=date(2026, 5, 4), last=date(2026, 6, 1))])
    assert groups(links) == [["1"], ["2"]]


def test_price_area_ambiguous_candidates_are_rejected():
    # dwa ogłoszenia z portalu b pasują do jednego bez współrzędnych -> nie wiadomo które
    links = dedup.deduplicate([
        L("a", "1"),
        L("b", "2", lat=52.0, lon=21.0),
        L("b", "3", lat=52.1, lon=21.1),
    ])
    assert groups(links) == [["1"], ["2"], ["3"]]


def test_transitive_grouping_and_stable_key():
    ls = [L("a", "1", parcel="P/1"), L("b", "2", parcel="P/1", lat=52.0, lon=21.0), L("c", "3", lat=52.0005, lon=21.0)]
    first, second = dedup.deduplicate(ls), dedup.deduplicate(list(reversed(ls)))
    assert groups(first) == [["1", "2", "3"]]
    assert {l.property_key for l in first} == {l.property_key for l in second}


def test_different_municipalities_never_match():
    links = dedup.deduplicate([L("a", "1", lat=52.0, lon=21.0), L("b", "2", lat=52.0, lon=21.0, muni="1465028")])
    assert groups(links) == [["1"], ["2"]]


def test_evaluate():
    links = [dedup.Link("a", "1", "P", "x", 1), dedup.Link("b", "2", "P", "x", 1), dedup.Link("c", "3", "Q", "x", 1)]
    truth = {("a", "1"): "T1", ("b", "2"): "T2", ("c", "3"): "T2"}
    q = dedup.evaluate(links, truth)
    assert (q.precision, q.recall) == (0.0, 0.0)
    truth = {("a", "1"): "T1", ("b", "2"): "T1", ("c", "3"): "T2"}
    q = dedup.evaluate(links, truth)
    assert (q.precision, q.recall) == (1.0, 1.0)


def test_quality_on_synthetic_data(synthetic_data):
    """Cel PoC: precyzja >= 90%, czułość >= 80% (pary ogłoszeń)."""
    listings = dedup.listings_from_observations(synthetic_data["rows"])
    q = dedup.evaluate(dedup.deduplicate(listings), synthetic_data["truth"])
    assert q.precision >= 0.90, q
    assert q.recall >= 0.80, q


@pytest.mark.parametrize("seed", [1, 7, 123])
def test_quality_is_stable_across_seeds(tmp_path, seed):
    from lmi import csv_import, synthetic

    paths = synthetic.generate(tmp_path, seed=seed)
    rows = []
    for src in synthetic.SOURCES:
        for o in csv_import.parse_file(paths[src]).observations:
            rows.append({**o.__dict__, "source_id": src})
    q = dedup.evaluate(dedup.deduplicate(dedup.listings_from_observations(rows)),
                       synthetic.load_ground_truth(paths["ground_truth"]))
    assert q.precision >= 0.90 and q.recall >= 0.80, q


def test_portal_added_later_still_matches_long_running_offer():
    # oferta na Otodomie od marca, Adresowo pobrane pierwszy raz w październiku: widoczne naraz -> ta sama działka
    old = L("otodom", "1", area=1636, prices=(329_000.0,), lat=51.0, lon=17.0,
            first=date(2026, 3, 2), last=date(2026, 10, 17))
    new = L("adresowo", "2", area=1636, prices=(335_000.0,), first=date(2026, 10, 17), last=date(2026, 10, 17))
    assert groups(dedup.deduplicate([old, new])) == [["1", "2"]]


def test_round_area_with_different_price_is_not_enough():
    # 1000 m² i cena różna o 2%: za mało wspólnego, żeby łączyć
    assert groups(dedup.deduplicate([L("a", "1", lat=52.0, lon=21.0), L("b", "2", prices=(102_000.0,))])) == [["1"], ["2"]]


def test_different_land_use_blocks_attribute_match():
    a, b = L("a", "1", area=1636, lat=52.0, lon=21.0), L("b", "2", area=1636)
    a.land_use, b.land_use = "budowlana", "rolna"
    assert groups(dedup.deduplicate([a, b])) == [["1"], ["2"]]


def test_neighbouring_plots_from_one_subdivision_stay_separate():
    # ten sam portal, widoczne naraz, 40 m od siebie, 1000 i 1020 m², różne ceny: dwie działki
    plots = [L("a", "1", lat=52.0, lon=21.0, prices=(200_000.0,)),
             L("a", "2", lat=52.00036, lon=21.0, area=1020, prices=(210_000.0,))]
    assert groups(dedup.deduplicate(plots)) == [["1"], ["2"]]
    # ...a ogłoszenie z innego portalu przy obu nie skleja ich pośrednio
    plots.append(L("b", "3", lat=52.00018, lon=21.0, area=1010, prices=(205_000.0,)))
    assert all(len(g) <= 2 for g in groups(dedup.deduplicate(plots)))


def test_same_portal_double_post_is_merged():
    a = L("a", "1", lat=52.0, lon=21.0)
    b = L("a", "2", lat=52.0002, lon=21.0)
    assert groups(dedup.deduplicate([a, b])) == [["1", "2"]]


def test_parcel_conflict_is_not_bridged_transitively():
    ls = [L("a", "1", parcel="X/1", lat=52.0, lon=21.0), L("b", "2", lat=52.0003, lon=21.0),
          L("c", "3", parcel="X/2", lat=52.0006, lon=21.0)]
    assert all(len({l.source_listing_id for l in dedup.deduplicate(ls) if l.property_key == k}) <= 2
               for k in {l.property_key for l in dedup.deduplicate(ls)})


def test_diff_runs_explains_split_pairs():
    a, b = L("a", "1", area=1636, lat=52.0, lon=21.0), L("b", "2", area=1636)
    a.land_use, b.land_use = "budowlana", "rolna"
    old = {a.key: "P1", b.key: "P1"}
    new = {a.key: "P1", b.key: "P2"}
    d = dedup.diff_runs([a, b], old, new)
    assert list(d) == ["inny typ działki"] and d["inny typ działki"]["pairs"] == 1
