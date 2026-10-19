import io
import zipfile
from datetime import date

import pytest

from lmi import gunb

HEAD = ("numer_urzad;numer_gunb;nazwa_organu;adres_organu;data_wplywu_wniosku;numer_decyzji_urzedu;data_wydania_decyzji;"
        "nazwa_inwestor;wojewodztwo;miasto;terc;cecha;cecha;ulica;ulica_dalej;nr_domu;rodzaj_inwestycji;kategoria;"
        "nazwa_zamierzenia_bud;nazwa_zam_budowlanego;kubatura;projektant_nazwisko;projektant_imie;"
        "projektant_numer_uprawnien;jednosta_numer_ew;obreb_numer;numer_dzialki;numer_arkusza_dzialki;"
        "jednostka_stara_numeracja_z_wniosku;stara_numeracja_obreb_z_wnioskiu;stara_numeracja_dzialka_z_wniosku")


def line(num, unit="022304_5", terc="0223045", kind="Budynek mieszkalny jednorodzinny", cat="I", parcel="12/3",
         decided="2026-05-04 00:00:00"):
    return (f"1/26;{num};Starosta;ul. X 1;2026-03-01 00:00:00;5/2026;{decided};Jan Kowalski;dolnośląskie;Kąty;"
            f"{terc};ul.;;Leśna;;2;{kind};{cat};dom;dom;650;Nowak;Anna;DOŚ/1/26;{unit};0007;{parcel};;;;")


def test_rows_assign_gmina_and_skip_personal_data():
    text = io.StringIO("\n".join([HEAD, line("A"), line("A", parcel="12/4"), line("B", unit="", terc="0264011"),
                                  line("C", unit="140101_1", terc="1401011")]) + "\n")
    out = list(gunb.rows(text))
    assert [r[0] for r in out] == ["A", "A", "B"]                      # spoza województwa pominięte
    assert out[0][2] == "0223043" and out[2][2] == "0264011"            # obszar wiejski -> gmina m.-w.
    assert out[0][4] == date(2026, 5, 4) and out[0][5] == "Budynek mieszkalny jednorodzinny" and out[0][7] == 650
    assert "Kowalski" not in repr(out) and "Nowak" not in repr(out) and "Leśna" not in repr(out)


@pytest.mark.integration
def test_load_and_view(pg_conn):
    from lmi import db

    db.apply_schema(pg_conn)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("wynik_dolnoslaskie.csv", "﻿" + "\n".join([
            HEAD, line("A"), line("A", parcel="12/4"), line("B", kind="Obiekt budowlany inny niż budynek mieszk", cat="XVII")]))
    assert gunb.load(pg_conn, buf.getvalue()) == 3
    rows = pg_conn.execute("SELECT numer_gunb, gmina_teryt, parcels, single_family FROM mart.gunb_permits ORDER BY 1").fetchall()
    assert rows == [("A", "0223043", 2, True), ("B", "0223043", 1, False)]
    assert gunb.load(pg_conn, buf.getvalue()) == 3                    # ponowne wczytanie zastępuje, nie dubluje
    assert pg_conn.execute("SELECT count(*) FROM scrape.gunb_permits").fetchone()[0] == 3


def test_old_gmina_code_goes_to_current_gmina(pg_conn):
    # Miękinia: dziś gmina miejsko-wiejska 0218033, w rejestrze jednostka ze starym kodem 021803_2
    pg_conn.execute("INSERT INTO scrape.uldk_communes (coord_key, teryt, name) VALUES ('a', '0218033', 'Miękinia'),"
                    " ('b', '0218012', 'Kostomłoty')")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("w.csv", "\n".join([HEAD, line("A", unit="021803_2", terc="0218032"),
                                       line("B", unit="026491_1", terc="0264911")]))
    gunb.load(pg_conn, buf.getvalue())
    rows = dict(pg_conn.execute("SELECT numer_gunb, gmina_teryt FROM mart.gunb_permits").fetchall())
    assert rows == {"A": "0218033", "B": "0264911"}      # nieznany numer gminy zostaje bez zmian
