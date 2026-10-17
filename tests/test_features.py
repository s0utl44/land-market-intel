from datetime import date

from lmi.scrapers import features


def test_from_params_skips_personal_and_maps():
    f = features.from_params({"Uzbrojenie": "prąd, gaz", "Droga dojazdowa": "utwardzona", "Agent": "Jan Kowalski",
                              "Typ ogłoszeniodawcy": "biuro nieruchomości", "Cena do negocjacji": "tak"})
    assert f["media"] == ["gaz", "prąd"] and f["access"] == ["utwardzony"] and f["seller"] == "biuro"
    assert f["negotiable"] is True and "Kowalski" not in str(f)


def test_relative_dates():
    t = date(2026, 10, 17)
    assert features.relative_date("wczoraj", t) == date(2026, 10, 16)
    assert features.relative_date("3 dni temu", t) == date(2026, 10, 14)
    assert features.relative_date("ponad miesiąc temu", t) is None
