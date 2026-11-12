/* Samouczek pracawre.com (11.11.2026, decyzje użytkownika) – część (a): przycisk 🎓 w pasku obok konta (dla wszystkich),
   OPROWADZANIE (12.11: osobno dla każdej sekcji – strona główna, Zimne telefony; bez Transakcji; podświetlenie miejsca + dymek z opisem, Wstecz / Dalej / Zakończ,
   Esc kończy, strzałki przewijają kroki; przejście między stronami pamiętane w localStorage, po 24 h bez ruchu znika)
   i „CO NOWEGO” (lista NOWOSCI – po zalogowaniu raz każdej osobie nowości z 30 dni, do których ma dostęp; licznik na 🎓;
   „Pokaż mi →” = jeden krok na właściwej stronie).
   KAŻDA WIDOCZNA ZMIANA W WITRYNIE = nowy wpis w NOWOSCI (na górze) i, gdy trzeba, poprawka kroków w TRASY.
   Ładowany przez pasek.js; korzysta z window.PracawrePasek (konto, aplikacje). */
(function () {
  "use strict";
  if (window.PracawreSamouczek || window.top !== window) return;   // ramka (Kontakty w nakładce) – bez samouczka
  if (location.pathname.indexOf("/radar") === 0) return;           // Radar działek – osobny projekt
  var P = window.PracawrePasek || {};
  var KL_STAN = "pracawre-samouczek", KL_NOW = "pracawre-nowosci", DOBA = 24 * 3600 * 1000;

  // ---- NOWOŚCI (najnowsze na górze; id NIE zmieniać – po nim pamiętamy, kto już widział) ----
  // KOMU (decyzja użytkownika przy KAŻDEJ nowości): dla = role (agent, administracja, dyrektor, zarzad, zarzadzanie, pozostale;
  // brak pola = wszyscy), obszar = tylko z dostępem do aplikacji. Administrator widzi wszystkie (wie, co dostali inni).
  // 12.11 (decyzja użytkownika): TREŚĆ i ODBIORCÓW każdej nowości zatwierdza użytkownik – nic nie dopisujemy bez jego zgody.
  // Nowość pokazuje się po wejściu RAZ; zamknięta przepada (bez listy „Co nowego” w menu 🎓).
  // Wzór wpisu: { id: "RRRR-MM-DD-nazwa", data: "RRRR-MM-DD", gdzie, tytul, opis, dla?: [role], obszar?, pokaz?: {sciezka, el, tytul, tekst} }
  var NOWOSCI = [
    // 12.11 – zatwierdzone przez użytkownika (1 i 2)
    { id: "2026-11-11-samouczek", data: "2026-11-12", gdzie: "Cała strona", tytul: "🎓 Samouczek",
      opis: "Przycisk 🎓 w pasku: samouczek strony głównej i Zimnych telefonów – co gdzie jest i ćwiczenie na fikcyjnym kliencie.",
      start: true },
    { id: "2026-11-11-sciaga-telefon", data: "2026-11-12", gdzie: "Zimne", obszar: "sciagi", tytul: "📋 Skrypt i obiekcje / Lista przed spotkaniem",
      opis: "W trybie „Dzwonię” otworzysz z boku skrypt rozmowy i odpowiedzi na obiekcje, a w karcie transakcji przed spotkaniem – listę, co zabrać i o co zapytać.",
      pokaz: { sciezka: "/leady/", el: "#dzwonPrz", tytul: "Skrypt i obiekcje", tekst: "Kliknij lwa <b>„Zacznij dzwonić”</b>. W pasku trybu „Dzwonię” jest przycisk <b>„📋 Skrypt i obiekcje”</b> – otwiera ściągę z boku, bez zasłaniania leada." } },
    // 12.11 – zatwierdzone przez użytkownika (wszystkie role)
    { id: "2026-11-12-notatnik", data: "2026-11-12", gdzie: "Cała strona", tytul: "📝 Notatnik",
      opis: "Twoje prywatne notatki na każdej stronie: przycisk „Notatnik” w pasku albo Alt+N. Okno przesuwasz i zmieniasz mu rozmiar, notatkę możesz przypiąć jako karteczkę na stronie głównej. Wyłączysz go w „Mój profil”.",
      pokaz: { sciezka: "/", el: "#pracawre-pasek .pp-not", tytul: "Notatnik", tekst: "Kliknij <b>„📝 Notatnik”</b> (albo Alt+N) – otworzy się okno z Twoimi notatkami. Przesuwasz je za ciemny nagłówek, rozmiar zmieniasz prawym dolnym rogiem." } }
  ];

  // ---- OPROWADZANIE: trasy po kolei; krok bez el = dymek na środku; brak elementu na stronie = krok pominięty ----
  var TRASY = [
    { id: "glowna", sciezka: "/", nazwa: "Strona główna", opis: "Pulpit, menu, konto – co gdzie jest", kroki: [
      { tytul: "Witaj w pracawre.com", tekst: "Tu są wszystkie narzędzia biura WRE. W kilku krokach pokażę, co gdzie jest i co się dzieje po kliknięciu.<br><br>Przerwiesz w każdej chwili (<b>Esc</b> albo „Zakończ”), a wrócisz przyciskiem <b>🎓</b> w pasku. Po stronach przechodzisz strzałkami ← → albo przyciskami." },
      { el: "#pracawre-pasek .pp-otw", tytul: "Menu ☰", tekst: "Wszystkie narzędzia, do których masz dostęp, np. <b>Zimne telefony</b>… Liczby przy nazwach to rzeczy do zrobienia. Na dole menu: motyw jasny / ciemny, <b>Mój profil</b>, <b>Zgłoś błąd</b>, Wyloguj." },
      { el: "#pracawre-pasek .pp-konto", tytul: "Twoje konto", tekst: "Otwiera to samo menu. W <b>„Mój profil”</b> połączysz swój kalendarz i pocztę Google – wtedy umówione spotkania same trafiają do kalendarza, a maile z klientami widać w transakcji." },
      { el: "#pracawre-pasek .pp-not", tytul: "Notatnik", tekst: "Twoje prywatne notatki – na każdej stronie (skrót <b>Alt+N</b>). Okno przesuwasz i zmieniasz mu rozmiar, notatki dzielisz na własne kategorie. „📌 Przypnij na stronie głównej” zrobi z notatki karteczkę tutaj. Wyłączysz go w „Mój profil”." },
      { el: "#spotkaniaS", tytul: "Spotkania", tekst: "Spotkania na dziś i jutro. Po terminie zapytamy <b>„Czy spotkanie się odbyło?”</b> – odpowiadasz Tak / Nie od razu tutaj (albo w okienku na dowolnej stronie)." },
      { el: "#naDzis", tytul: "Moje zadania", tekst: "Zadania: zaległe, na dziś i na najbliższe 7 dni. Kliknięcie otwiera właściwe miejsce, np. leada w Zimnych." },
      { el: "#celeS", tytul: "Moje cele", tekst: "Cele na miesiąc – ustala je z Tobą dyrektor. Pasek pokazuje, ile już zrobione." },
      { el: "#sprawyS", tytul: "Moje transakcje", tekst: "Otwarte sprawy, wynagrodzenie w toku i sukces w tym miesiącu; pigułki w kolorach etapów prowadzą do tablicy Transakcji." },
      { el: "#zimneS", tytul: "Zimne w tym tygodniu", tekst: "Odebrane telefony i umówione spotkania od poniedziałku – liczą się wszystkie Twoje telefony zapisane w systemie." },
      { el: "#podsS", tytul: "Podsumowanie od dyrektora", tekst: "Po odprawie dyrektor wysyła Ci podsumowanie i ustalenia – tutaj je przeczytasz." },
      { el: "#dzwonPrz", tytul: "Zacznij dzwonić", tekst: "Lew uruchamia tryb <b>„Dzwonię”</b> – system podaje lead po leadzie, Ty tylko dzwonisz i zapisujesz wynik. Lwa możesz przesunąć myszą w wygodne miejsce." }
    ] },
    { id: "zimne", sciezka: "/leady/", obszar: "leady", nazwa: "Zimne telefony", potem: "cw1", opis: "Co gdzie jest, a potem praca na fikcyjnym kliencie – z listy i w trybie „Zacznij dzwonić”", kroki: [
      { el: "#heroTyt", tytul: "Zimne telefony", tekst: "Prywatne ogłoszenia z portali (Otodom, Adresowo, Gratka) – właściciele bez pośrednika. Nowe ogłoszenia przychodzą codziennie wieczorem." },
      { el: "#rodzaj", tytul: "Sprzedaż / Najem", tekst: "Wybierz rodzaj ogłoszeń. Jeśli masz dostęp, są też <b>Grunty</b> i <b>Marketing</b> (leady z formularzy i kampanii)." },
      { el: "#widok", tytul: "Pula i Twoje leady", tekst: "<b>Zimne</b> – wspólna pula do wzięcia. <b>Moje zimne na dziś</b> – Twoje: „Do zadzwonienia” (nic jeszcze nie zrobione) i „Zadzwoń ponownie” (umówiony telefon, nieodebrane)." },
      { el: "#q", tytul: "Szukaj", tekst: "Po numerze telefonu (wystarczą 3 cyfry), imieniu, ulicy albo tytule – we wszystkich leadach, także cudzych (zobaczysz, kto prowadzi)." },
      { el: "#filtryR", tytul: "Filtry", tekst: "Portale, rodzaj nieruchomości, pokoje, cena i kolejność. Wybór zapamiętuje się w przeglądarce." },
      { el: "#bZLinku", tytul: "+ Dodaj z linku", tekst: "Zimny telefon z dowolnego ogłoszenia (np. OLX): wklejasz link i numer – lead od razu jest Twój." },
      { el: "#lista", tytul: "Lead", tekst: "Otwórz leada → <b>„Otwórz ogłoszenie”</b> → na portalu sam kliknij „Pokaż numer” i wklej go w pole telefonu. Z numerem kliknij <b>„Biorę”</b> – lead jest Twój, a kontakt powstaje w HubSpot." },
      { tytul: "Wynik telefonu – co się wtedy dzieje", tekst: "<ul class='pp-tour-l'>" +
          "<li><b>Nie odebrał</b> – lead zostaje u Ciebie w „Zadzwoń ponownie”. 3 nieodebrane w różne dni → wraca do puli.</li>" +
          "<li><b>Odebrał – zadzwoń ponownie</b> – zadanie z terminem i przypomnieniem; lead zostaje przy Tobie także po północy.</li>" +
          "<li><b>Stracono / Nie zainteresowany</b> (z powodem) – kontakt „Niekwalifikowany”, lead wolny od jutra, Tobie nie wróci przez 7 dni.</li>" +
          "<li><b>Spotkanie umówione</b> – wpisujesz termin; spotkanie zapisuje się w HubSpot i w Twoim kalendarzu Google (gdy go połączysz).</li>" +
          "<li><b>Niekwalifikowany?</b> – biuro, deweloper, nieaktualne, duplikat – dotyczy tylko tego ogłoszenia.</li></ul>" +
          "Lead bez Twojego zadania wraca o północy do wspólnej puli." },
      { el: "#dzwonPrz", tytul: "Tryb „Dzwonię”", tekst: "Jeden lead naraz, wynik klawiszami 1–4, następny lead podaje się sam." }
    ] },
  ];

  // ---- ĆWICZENIE na fikcyjnym kliencie (11.11, część b): Zimne, sytuacja 1 „Proszę zadzwonić za tydzień” ----
  // Leady z /leady/api/samouczek (tylko moje, numery 555 2xx 3nn); wszystko w HubSpot z „🎓 SAMOUCZEK”, sprzątane na końcu.
  var CW = null, ROZMOWA_TOMASZ = null;                                      // {leady: [{id, imie, numer, …}], rodzaj}
  function L(n) { return CW && CW.leady ? CW.leady[n - 1] : null; }
  function nrTxt(n) { var x = L(n); return x ? x.numer.slice(0, 3) + " " + x.numer.slice(3, 6) + " " + x.numer.slice(6) : "…"; }
  function otwarty() { try { return typeof OTWARTY !== "undefined" ? OTWARTY : null; } catch (e) { return null; } }   // karta leada w Zimnych
  function otwartyL(n) { var o = otwarty(), x = L(n); return !!(o && x && o.portal === "samouczek" && o.id === x.id) ? o : null; }
  // zdarzenia: udane zapisy strony (fetch) – samouczek przechodzi dalej, gdy agent zrobił to, o co prosił krok
  var ZD = [];
  (function () {
    if (!window.fetch || window.fetch.__samouczek) return;
    var f0 = window.fetch;
    var f = function (u, o) {
      var url = typeof u === "string" ? u : (u && u.url) || "", m = ((o && o.method) || "GET").toUpperCase();
      return f0.apply(this, arguments).then(function (r) { try { ZD.push({ u: new URL(url, location.href).pathname, m: m, ok: r.ok, t: Date.now() }); } catch (e) {} return r; });
    };
    f.__samouczek = true; window.fetch = f;
  })();
  function bylo(re, m, od) { return ZD.some(function (z) { return z.ok && z.m === m && z.t >= (od || 0) && re.test(z.u); }); }
  function apiL(sciezka, opcje) {
    return fetch("/leady/api/" + sciezka, Object.assign({ credentials: "same-origin", headers: { "Content-Type": "application/json" } }, opcje || {}))
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.detail || "Błąd " + r.status); return d; }); });
  }
  function kopiujBtn(n) { return '<button type="button" class="pt-k" data-kopiuj="' + (L(n) ? L(n).numer : "") + '">📋 Kopiuj</button>'; }

  var CWICZENIA = [
    { id: "cw1", sciezka: "/leady/", obszar: "leady", nazwa: "Zimne telefony · ćwiczenie 1 z 2", cw: true, kroki: [
      { tytul: "Ćwiczenie: lead z listy", dalejTxt: "Zaczynamy →",
        tekst: "Przejdziesz drogę leada z listy Zimnych – od ogłoszenia do umówionego telefonu – na <b>fikcyjnych klientach</b>.<br><br>" +
          "Wszystko, co zapiszesz, dostanie dopisek <b>🎓 SAMOUCZEK</b>: nie liczy się w Raportach, celach ani na pulpicie i na końcu samo się usunie.",
        naDalej: function () {
          return startSerwer("cw1");
        } },
      { el: function () { return L(1) && document.querySelector('#lista [data-p="samouczek"][data-i="' + L(1).id + '"]'); }, przepusc: true,
        przed: function () {
          var q = document.getElementById("q");
          if (q && L(1) && !otwartyL(1)) { q.value = "Przykładowa"; q.dispatchEvent(new Event("input", { bubbles: true })); }
        },
        czekaj: function (k) {
          if (!otwartyL(1) && L(1) && !znajdz(k.el) && Date.now() - k.od > 6000 && !k.auto) { k.auto = true; location.hash = "#lead/samouczek/" + encodeURIComponent(L(1).id); }
          return !!otwartyL(1);
        },
        tytul: "Otwórz leada", tekst: "Na liście są Twoje fikcyjne ogłoszenia (oznaczone 🎓). Wyszukałem pierwsze: <b>mieszkanie na Psim Polu, Pan Tomasz</b>. <b>Kliknij je</b> – otworzy się karta leada.",
        brak: "Nie widzę tego leada na liście (może zasłaniają go filtry). <button type='button' class='pt-k' data-otworz-l1>Otwórz go za mnie</button>" },
      { el: "#panel [data-ogloszenie]", przepusc: true,
        tytul: "Otwórz ogłoszenie i odsłoń numer", tekst: function () {
          return "Kliknij <b>„Otwórz ogłoszenie”</b> – otworzy się w osobnej karcie. Na portalu sam klikasz <b>„Pokaż numer”</b> (robot numerów nie zbiera). W ćwiczeniu numer to:<div class='pt-nr'><b>" + nrTxt(1) + "</b>" + kopiujBtn(1) + "</div>Wróć tutaj i kliknij <b>Dalej</b>.";
        } },
      { el: "#pTel", przepusc: true,
        czekaj: function () { var o = otwartyL(1); return !!(o && o.telefon === (L(1) || {}).numer) || bylo(/\/leady\/api\/lead\/samouczek\/[^/]+$/, "PUT"); },
        tytul: "Wklej numer", tekst: function () { return "Wklej numer w pole <b>Telefon</b> (9 cyfr zapisuje się samo). <div class='pt-nr'><b>" + nrTxt(1) + "</b>" + kopiujBtn(1) + "</div>"; } },
      { el: "#panel [data-wez]", przepusc: true,
        czekaj: function () { var o = otwartyL(1); return !!(o && o.moj) || bylo(/\/leady\/api\/lead\/samouczek\/[^/]+\/biore$/, "POST"); },
        tytul: "Biorę", tekst: "Kliknij <b>„Biorę”</b>. Lead jest od teraz Twój, a w HubSpot powstaje kontakt. W ćwiczeniu kontakt ma dopisek 🎓 SAMOUCZEK." },
      { rozmowa: true, tytul: "Dzwonisz do Pana Tomasza", dalejTxt: "Zapisuję wynik rozmowy →",
        tekst: "<div class='pt-r'><div class='pt-kl'><b>Pan Tomasz:</b> Dzień dobry… tak, ogłoszenie jest aktualne. Ale jestem teraz w pracy, nie bardzo mogę rozmawiać.</div>" +
          "<div class='pt-hint'>💡 <b>Ze skryptu:</b> szanuj czas klienta, ale zostaw konkret – „Rozumiem, zajmę minutę: mamy klientów szukających takiego mieszkania. Kiedy mogę zadzwonić, żeby spokojnie porozmawiać?”</div>" +
          "<div class='pt-kl'><b>Pan Tomasz:</b> Wie Pan co, proszę zadzwonić za tydzień, w czwartek po 17. Wtedy będę wiedział, czy znajomy jednak nie weźmie.</div>" +
          "<div class='pt-ja'>➡️ <b>Teraz zapiszesz:</b> Odebrano → Do ponownego kontaktu → termin <b>czwartek za tydzień, 17:00</b> + krótka notatka.</div></div>" },
      { el: "#panel #tw", przepusc: true,
        czekaj: function () { return !!document.querySelector('#panel [data-tw="odebrano"][aria-pressed="true"]'); },
        tytul: "Wynik: Odebrano", tekst: "Kliknij <b>„Odebrano”</b>. (Gdyby nie odebrał – „Nie odebrano”: lead zostaje u Ciebie w „Zadzwoń ponownie”.)",
        brak: "Czekam, aż HubSpot pokaże nowy kontakt (zwykle kilka sekund)… Sekcja <b>„Rozmowa i notatki”</b> pojawi się w karcie sama." },
      { el: "#panel #td", przepusc: true,
        czekaj: function () { return !!document.querySelector('#panel [data-td="ponownie"][aria-pressed="true"]'); },
        tytul: "Co dalej? Do ponownego kontaktu", tekst: "Klient prosi o telefon za tydzień – kliknij <b>„Do ponownego kontaktu”</b>. (<i>Stracono</i> = nie zainteresowany, z powodem; <i>Spotkanie umówione</i> = termin spotkania w HubSpot i w kalendarzu.)" },
      { el: "#panel .hsK.pw-ed", przepusc: true,
        czekaj: function (k) { return bylo(/\/leady\/api\/lead\/samouczek\/[^/]+\/telefon$/, "POST", k.od); },
        tytul: "Termin i notatka", tekst: "W polu <b>Kiedy</b> ustaw <b>czwartek za tydzień, 17:00</b> (kółko myszy nad polem zmienia dzień, z Shift – tydzień). Przypomnienie zostaw. W polu poniżej wpisz, co ustaliłeś, np. <i>„Znajomy może wziąć mieszkanie, oddzwonić w czwartek po 17.”</i> i kliknij <b>„✓ Zapisz telefon”</b>." },
      { tytul: "Gotowe – tak wygląda „zadzwoń za tydzień”", dalejTxt: "Dalej: „Zacznij dzwonić” →",
        tekst: "<ul class='pp-tour-l'><li>W HubSpot: <b>telefon</b> z wynikiem „Połączono”, <b>zadanie</b> „Zadzwoń ponownie” na czwartek 17:00 z przypomnieniem i Twoja notatka.</li>" +
          "<li>Lead jest w <b>„Moje zimne na dziś” → „Zadzwoń ponownie”</b> i <b>nie wróci o północy do puli</b> – trzyma go Twoje zadanie.</li>" +
          "<li>W dniu terminu zadanie pokaże się na <b>pulpicie</b> w „Moje zadania” i jako przypomnienie.</li></ul>" +
          "Teraz to samo w trybie <b>„Zacznij dzwonić”</b> – tak dzwoni się na co dzień.",
        naDalej: function () { zapisz(KL_STAN, null); T = null; start("cw2"); return false; } }
    ] }
  ];
  function startSerwer(id) {
    return apiL("samouczek/start", { method: "POST" }).then(function (d) { CW = d; zapisz(KL_STAN, { trasa: id, i: 1, czas: Date.now() }); location.reload(); return false; });
  }
  function dz() { try { return typeof DZ !== "undefined" ? DZ : null; } catch (e) { return null; } }   // tryb „Dzwonię” w Zimnych
  function dzLeadL(n) { var d = dz(), x = L(n); return !!(d && d.lead && x && d.lead.portal === "samouczek" && d.lead.id === x.id) ? d.lead : null; }
  function trybOtwarty() { var e = document.getElementById("dz"); return !!(e && !e.hidden); }
  ROZMOWA_TOMASZ = function (koniec) {
    return "<div class='pt-r'><div class='pt-kl'><b>Pan Tomasz:</b> Dzień dobry… tak, ogłoszenie jest aktualne. Ale jestem teraz w pracy, nie bardzo mogę rozmawiać.</div>" +
      "<div class='pt-hint'>💡 <b>Ze skryptu:</b> szanuj czas klienta, ale zostaw konkret – „Rozumiem, zajmę minutę: mamy klientów szukających takiego mieszkania. Kiedy mogę zadzwonić, żeby spokojnie porozmawiać?”</div>" +
      "<div class='pt-kl'><b>Pan Tomasz:</b> Wie Pan co, proszę zadzwonić za tydzień, w czwartek po 17. Wtedy będę wiedział, czy znajomy jednak nie weźmie.</div>" +
      "<div class='pt-ja'>➡️ <b>Teraz zapiszesz:</b> " + koniec + "</div></div>";
  };
  CWICZENIA.push({ id: "cw2", sciezka: "/leady/", obszar: "leady", nazwa: "Zimne telefony · ćwiczenie 2 z 2", cw: true, kroki: [
    { tytul: "Ćwiczenie: tryb „Zacznij dzwonić”", dalejTxt: "Dalej →",
      tekst: "Przećwiczysz dzwonienie w trybie <b>„Dzwonię”</b> – system podaje klienta po kliencie, Ty dzwonisz i zapisujesz wynik. Klienci w ćwiczeniu są <b>fikcyjni</b>.<br><br>" +
        "Jak poprzednio wszystko z dopiskiem <b>🎓 SAMOUCZEK</b> – na końcu samo się usunie.",
      naDalej: function () { return startSerwer("cw2"); } },
    { el: function () { var o = document.getElementById("okSp"); return o && !o.hidden ? o.querySelector(".ok") : document.getElementById("dzwonPrz"); }, przepusc: true,
      czekaj: function () { return trybOtwarty(); },
      tytul: "Zacznij dzwonić", tekst: "Kliknij lwa <b>„Zacznij dzwonić”</b>. Jeśli pojawi się okno <b>„📞 Dziś dzwonię”</b> – wybierz, co chcesz, i kliknij <b>„▶ Zaczynam”</b>. Fikcyjny klient i tak przyjdzie pierwszy.",
      brak: "Nie widzę lwa na tej stronie. <button type='button' class='pt-k' data-tryb>Uruchom tryb za mnie</button>" },
    { el: "#dz [data-dz-ogl]", przepusc: true,
      tytul: "Otwórz ogłoszenie i odsłoń numer", tekst: function () {
        return "Tryb podał Ci klienta (oznaczenie 🎓). Kliknij <b>„1. Otwórz ogłoszenie”</b> – na portalu sam klikasz <b>„Pokaż numer”</b>. W ćwiczeniu numer to:<div class='pt-nr'><b>" + nrTxt(1) + "</b>" + kopiujBtn(1) + "</div>Wróć tutaj i kliknij <b>Dalej</b>.";
      }, brak: "Czekam, aż tryb poda klienta…" },
    { el: "#dzTel", przepusc: true,
      czekaj: function () { var d = dzLeadL(1); return !!(d && d.telefon) || bylo(/\/leady\/api\/dzwonie\/samouczek\/[^/]+\/numer$/, "POST"); },
      tytul: "Wklej numer", tekst: function () { return "Wklej numer w pole <b>„2. Wklej numer”</b>. W trybie „Dzwonię” lead od razu jest Twój – bez „Biorę”. <div class='pt-nr'><b>" + nrTxt(1) + "</b>" + kopiujBtn(1) + "</div>"; } },
    { rozmowa: true, tytul: "Dzwonisz do Pana Tomasza", dalejTxt: "Zapisuję wynik rozmowy →",
      tekst: function () { return ROZMOWA_TOMASZ("„⏰ Odebrał – oddzwonić” → <b>Za tydzień</b>, godzina <b>17:00</b> + krótka notatka."); } },
    { el: '#dz [data-dz-w="ponownie"]', przepusc: true,
      czekaj: function () { return !!document.querySelector('#dz [data-dz-w="ponownie"][aria-pressed="true"]'); },
      tytul: "Odebrał – oddzwonić", tekst: "Kliknij <b>„⏰ Odebrał – oddzwonić”</b> (albo klawisz <b>2</b>). Inne wyniki: <i>Nie odebrał</i> – wróci w kolejnej próbie, <i>Nie jest zainteresowany</i> – z powodem, <i>Spotkanie umówione</i> – termin spotkania w HubSpot i w kalendarzu." },
    { el: "#dzDalej .dalej", przepusc: true,
      czekaj: function (k) { return bylo(/\/leady\/api\/lead\/samouczek\/[^/]+\/telefon$/, "POST", k.od); },
      tytul: "Termin i notatka", tekst: "Kliknij <b>„Za tydzień”</b>, w polu <b>Termin</b> zmień godzinę na <b>17:00</b>, dopisz notatkę, np. <i>„Znajomy może wziąć mieszkanie, oddzwonić w czwartek po 17.”</i> i kliknij <b>„Zapisz i dalej →”</b>." },
    { tytul: "Gotowe – tak wygląda praca w trybie „Dzwonię”", dalejTxt: "Zakończ ćwiczenie →",
      tekst: "<ul class='pp-tour-l'><li>Zaraz po zapisie tryb podaje <b>następnego klienta</b> – telefon, wynik, następny.</li>" +
        "<li>W HubSpot: telefon z wynikiem „Połączono”, <b>zadanie</b> na czwartek 17:00 z przypomnieniem i notatka.</li>" +
        "<li>W dniu terminu Pan Tomasz będzie <b>pierwszy w kolejce</b> („Zadzwoń ponownie – termin”) i w „Moje zadania” na pulpicie.</li></ul>" +
        "Teraz posprzątam wszystko, co powstało w ćwiczeniu.",
      naDalej: function () { koniecCwiczenia(); return false; } }
  ] });
  function trasa(id) { return TRASY.concat(CWICZENIA).filter(function (x) { return x.id === id; })[0] || null; }

  function koniecCwiczenia() {
    zakoncz(false);
    var o = okno('<div class="po-n">🎓 Samouczek</div><h2>Sprzątam po ćwiczeniu…</h2><p>Usuwam fikcyjne leady i to, co powstało w HubSpot.</p>');
    apiL("samouczek/sprzataj", { method: "POST" }).then(function (w) {
      var kal = (w.kalendarz || []).map(function (kl) { return P.google && P.google.usun ? P.google.usun(kl).then(function () { return null; }, function () { return kl; }) : Promise.resolve(kl); });
      return Promise.all(kal).then(function (nieusuniete) { return [w, nieusuniete.filter(Boolean)]; });
    }).then(function (x) {
      var w = x[0], kal = x[1], u = w.usuniete || {}, lista = Object.keys(u).map(function (k) { return "<li>" + k + ": " + u[k] + "</li>"; }).join("");
      var reczne = (w.reczne || []).map(function (r) { return "<li>" + r.co + " (HubSpot id " + r.id + ") – z dopiskiem 🎓 SAMOUCZEK</li>"; })
        .concat(kal.map(function () { return "<li>spotkanie w Twoim Kalendarzu Google z dopiskiem 🎓 SAMOUCZEK</li>"; })).join("");
      o.querySelector(".po").innerHTML = '<div class="po-n">🎓 Samouczek</div><h2>🎉 Ćwiczenie ukończone</h2>' +
        "<p>Przeprowadziłeś leada od ogłoszenia do umówionego telefonu – tak samo wygląda prawdziwa praca.</p>" +
        "<div class='nw'><b>Posprzątane automatycznie</b><ul class='pp-tour-l'>" + (lista || "<li>fikcyjne leady</li>") + "<li>fikcyjne leady i ich historia w Zimnych</li></ul>" +
        "<small style='margin:0'>Nic z ćwiczenia nie trafiło do Raportów, celów ani na pulpit.</small></div>" +
        (reczne ? "<div class='nw' style='border-color:#e5534b'><b>⚠ Tego nie udało się usunąć – usuń ręcznie</b><ul class='pp-tour-l'>" + reczne + "</ul></div>" : "") +
        '<div class="po-d"><span></span><button type="button" class="pri" data-ok>Wracam do pracy</button></div>';
      o.querySelector("[data-ok]").addEventListener("click", function () { zamknijOkno(); location.href = "/leady/"; });
    }).catch(function (e) {
      o.querySelector(".po").innerHTML = '<div class="po-n">🎓 Samouczek</div><h2>Nie udało się posprzątać</h2><p>' + String(e.message || e) +
        "</p><p>Ćwiczenie posprząta się samo po dobie. Możesz też spróbować ponownie: 🎓 → „Zakończ ćwiczenie i posprzątaj”.</p>" +
        '<div class="po-d"><span></span><button type="button" class="pri" data-ok>OK</button></div>';
      o.querySelector("[data-ok]").addEventListener("click", zamknijOkno);
    });
  }

  var CSS =
    "#pp-tour-tlo{position:fixed;inset:0;z-index:2147483100;background:transparent}" +
    "#pp-tour-cel{position:fixed;z-index:2147483101;border-radius:12px;box-shadow:0 0 0 3px #c9a03c,0 0 0 9999px rgba(12,12,10,.55);pointer-events:none;transition:all .2s ease}" +
    "#pp-tour-cel.srodek{left:50%!important;top:40%!important;width:0!important;height:0!important;box-shadow:0 0 0 9999px rgba(12,12,10,.55)}" +
    "#pp-tour-dym,#pp-tour-ok{--k:#fff;--t:#1f1d1a;--m:#6b665d;--l:#e2ddd2;--z:#7a5f1c;--zt:#fbf3d8;font:15px/1.5 Lato,'Segoe UI',system-ui,sans-serif;color:var(--t)}" +
    "html[data-theme=dark] #pp-tour-dym,html[data-theme=dark] #pp-tour-ok{--k:#212326;--t:#e8e5de;--m:#a39e94;--l:#3a3d42;--z:#e0b850;--zt:#3a3220}" +
    "#pp-tour-dym{position:fixed;z-index:2147483102;width:min(400px,calc(100vw - 24px));box-sizing:border-box;background:var(--k);border-radius:16px;padding:16px 18px 14px;box-shadow:0 14px 44px rgba(0,0,0,.35)}" +
    "#pp-tour-dym *,#pp-tour-ok *{box-sizing:border-box}" +
    "#pp-tour-dym .pt-n{font-size:11.5px;font-weight:800;letter-spacing:.06em;color:var(--z);text-transform:uppercase}" +
    "#pp-tour-dym h3{margin:4px 0 6px;font-size:18px;line-height:1.25}#pp-tour-dym .pt-t{margin:0}" +
    ".pp-tour-l{margin:6px 0 8px;padding-left:18px}.pp-tour-l li{margin:3px 0}" +
    "#pp-tour-dym .pt-p{display:flex;gap:8px;align-items:center;margin-top:14px}" +
    "#pp-tour-dym button,#pp-tour-ok button,#pp-tour-ok a{all:unset;box-sizing:border-box;cursor:pointer;height:36px;padding:0 14px;border-radius:999px;display:inline-flex;align-items:center;gap:6px;font-weight:700;font-size:14px;border:1px solid var(--l);color:var(--t)}" +
    "#pp-tour-dym button:focus-visible,#pp-tour-ok button:focus-visible,#pp-tour-ok a:focus-visible{outline:2px solid #c9a03c;outline-offset:2px}" +
    "#pp-tour-dym .pt-x{border:0;color:var(--m);padding:0 6px}#pp-tour-dym .pt-s{flex:1}" +
    "#pp-tour-dym .pt-d,#pp-tour-ok .pri{background:#1f1d1a;color:#fff;border-color:#1f1d1a}" +
    "html[data-theme=dark] #pp-tour-dym .pt-d,html[data-theme=dark] #pp-tour-ok .pri{background:#c9a03c;color:#141518;border-color:#c9a03c}" +
    "#pp-tour-dym button[disabled]{opacity:.35;cursor:default}" +
    "@media (max-width:600px){#pp-tour-dym{left:12px!important;right:12px;top:auto!important;bottom:12px;width:auto}}" +
    // przycisk w pasku
    ".pp .pp-sam{position:relative;height:28px;padding:0 11px;border-radius:999px;border:1px solid #8a6d1c;background:#2b2618;color:#f3d98a;font-size:12.5px;font-weight:800}" +
    ".pp .pp-sam:hover{background:#3a3220;color:#fff}.pp .pp-sam .pp-sam-n{background:#e5534b;color:#fff;border-radius:999px;padding:0 6px;font-size:11px;line-height:17px}" +
    "@media (max-width:600px){.pp .pp-sam .pp-sam-t{display:none}.pp .pp-sam{padding:0 8px}}" +
    // menu 🎓 i okno „Co nowego”
    "#pp-tour-ok{position:fixed;inset:0;z-index:2147483050;background:rgba(15,14,12,.45);display:flex;justify-content:center;align-items:flex-start;padding:70px 12px 12px}" +
    "#pp-tour-ok.menu{background:transparent;justify-content:flex-end;padding:46px 12px 12px}" +
    "#pp-tour-ok .po{background:var(--k);border-radius:18px;box-shadow:0 16px 48px rgba(0,0,0,.3);width:min(560px,100%);max-height:calc(100vh - 90px);overflow:auto;padding:20px 22px}" +
    "#pp-tour-ok.menu .po{width:min(340px,100%);padding:10px;border-radius:14px}" +
    "#pp-tour-ok .po-n{font-size:12px;color:var(--z);font-weight:800;letter-spacing:.06em;text-transform:uppercase}" +
    "#pp-tour-ok h2{margin:4px 0 12px;font-size:21px}" +
    "#pp-tour-ok .nw{border:1px solid var(--l);border-radius:14px;padding:12px 14px;margin-top:10px}" +
    "#pp-tour-ok .nw b{font-size:15px}#pp-tour-ok .nw small{color:var(--m);margin-left:6px}#pp-tour-ok .nw p{margin:5px 0 8px;color:var(--t)}" +
    "#pp-tour-ok .nw button{height:32px;background:var(--zt);border-color:#bd9302}" +
    "#pp-tour-ok .po-d{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:16px;color:var(--m);font-size:13px}" +
    "#pp-tour-ok .mi{display:flex;width:100%;height:auto;min-height:44px;padding:8px 12px;border:0;border-radius:10px;flex-direction:column;align-items:flex-start;gap:1px}" +
    "#pp-tour-ok .mi:hover{background:var(--zt)}#pp-tour-ok .mi small{font-weight:400;color:var(--m);font-size:12.5px}" +
    "#pp-tour-ok .mi[disabled]{opacity:.55;cursor:default;background:none}" +
    "#pp-tour-dym .pt-nr{display:flex;align-items:center;gap:10px;background:var(--zt);border-radius:10px;padding:8px 12px;margin:8px 0}" +
    "#pp-tour-dym .pt-nr b{font-size:19px;letter-spacing:.05em;flex:1}" +
    "#pp-tour-dym .pt-k{height:30px;padding:0 10px;font-size:13px}" +
    "#pp-tour-dym .pt-cz{margin-top:10px;font-size:13px;color:var(--m)}" +
    "#pp-tour-dym.rozm{width:min(620px,calc(100vw - 24px))}" +
    "#pp-tour-dym .pt-r{display:flex;flex-direction:column;gap:10px;margin-top:4px}" +
    "#pp-tour-dym .pt-kl{align-self:flex-start;max-width:85%;background:var(--l);border-radius:14px 14px 14px 4px;padding:8px 12px}" +
    "#pp-tour-dym .pt-hint{background:var(--zt);border-radius:12px;padding:8px 12px;font-size:14px}" +
    "#pp-tour-dym .pt-ja{background:#1f1d1a;color:#fff;border-radius:12px;padding:10px 12px}" +
    "#pp-tour-tlo.przepusc{pointer-events:none}" +
    "#pp-tour-ok .mi .pp-sam-n{background:#e5534b;color:#fff;border-radius:999px;padding:0 6px;font-size:11px;margin-left:6px}";

  function styl() {
    if (document.getElementById("pp-tour-styl")) return;
    var s = document.createElement("style"); s.id = "pp-tour-styl"; s.textContent = CSS; document.head.appendChild(s);
  }
  function czytaj(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } }
  function zapisz(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function ta(sciezka) { var p = location.pathname; return sciezka === "/" ? p === "/" || p === "/index.html" : p.indexOf(sciezka) === 0 || p + "/" === sciezka; }

  // ---- dostęp ----
  var KONTO = null;
  function maObszar(o) {
    if (!o) return true;
    if (!KONTO || !P.aplikacje) return false;
    if (P.aplikacje(KONTO).some(function (a) { return a.obszar === o; })) return true;
    if (o === "leady" || o === "transakcje" || o === "wdrozenie") return false;          // aplikacje – tylko widoczne w menu
    var p = (KONTO.obszary || {})[o];                                                     // pozostałe obszary (np. ściągi) – z konta
    return p === "dostep" || p === "admin";
  }

  // ---- nowości ----
  function dlaMnie(n) {
    if (!maObszar(n.obszar)) return false;
    if (!n.dla || (KONTO && KONTO.admin)) return true;
    var role = (KONTO && (KONTO.role || [KONTO.rola])) || [];
    return n.dla.some(function (r) { return role.indexOf(r) >= 0; });
  }
  // widziane – na KONCIE (Kontakty: profil.nowosci, PUT /administracja/api/ja/nowosci); localStorage tylko na wypadek braku serwera
  function klNow() { return KL_NOW + ":" + ((KONTO && KONTO.email) || ""); }   // wspólny komputer – osobno dla każdego konta
  function widziane() {
    var z = (KONTO && KONTO.profil && KONTO.profil.nowosci) || [];
    return z.concat(czytaj(klNow()) || []);
  }
  function nowe() {
    var w = widziane(), od = Date.now() - 30 * 24 * 3600 * 1000;
    return NOWOSCI.filter(function (n) { return w.indexOf(n.id) < 0 && Date.parse(n.data) >= od && dlaMnie(n) && !(wylaczony() && (n.start || n.cw)); });
  }
  function oznaczWidziane() {
    var ids = NOWOSCI.map(function (n) { return n.id; });
    zapisz(klNow(), ids);
    if (KONTO) {
      KONTO.profil = KONTO.profil || {};
      KONTO.profil.nowosci = ids;
      fetch("/administracja/api/ja/nowosci", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ widziane: ids }) }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
        if (!d) return;
        try { var k = JSON.parse(sessionStorage.getItem("pracawre-konto") || "null"); if (k) { k.profil = k.profil || {}; k.profil.nowosci = d.nowosci; sessionStorage.setItem("pracawre-konto", JSON.stringify(k)); } } catch (e) {}
      }).catch(function () {});
    }
    licznik();
  }
  function licznik() {
    var n = nowe().length;
    document.querySelectorAll(".pp-sam-n").forEach(function (e) { e.textContent = n; e.hidden = !n; });
  }

  // ---- okno (menu 🎓 / co nowego) ----
  function zamknijOkno() { var o = document.getElementById("pp-tour-ok"); if (o) o.remove(); window.removeEventListener("keydown", klawOkno, true); }
  function klawOkno(e) { if (e.key === "Escape" && !e.defaultPrevented && document.getElementById("pp-tour-ok")) { e.preventDefault(); e.stopPropagation(); var m = document.querySelector("#pp-tour-ok:not(.menu)"); zamknijOkno(); if (m) oznaczWidziane(); } }
  function okno(htmlTxt, menu) {
    zamknijOkno(); styl();
    var o = document.createElement("div"); o.id = "pp-tour-ok"; if (menu) o.className = "menu";
    o.setAttribute("role", "dialog"); o.setAttribute("aria-modal", "true");
    o.innerHTML = '<div class="po">' + htmlTxt + "</div>";
    o.addEventListener("click", function (e) { if (e.target === o) { zamknijOkno(); if (!menu) oznaczWidziane(); } });
    document.body.appendChild(o);
    window.addEventListener("keydown", klawOkno, true);
    var f = o.querySelector("button"); if (f) f.focus();
    return o;
  }
  function menu() {
    var n = nowe().length, t = trasaTu(), st0 = czytaj(KL_STAN), cwSt = st0 && st0.trasa && (trasa(st0.trasa) || {}).cw ? st0 : null;
    var o = okno(
      (cwSt ? '<button type="button" class="mi" data-m="cw-wroc"><b>▶ Wróć do samouczka</b><small>Tam, gdzie skończyłeś</small></button>' +
              '<button type="button" class="mi" data-m="cw-koniec"><b>Zakończ samouczek i posprzątaj</b><small>Usuwa fikcyjne leady i to, co powstało w HubSpot</small></button>' : "") +
      TRASY.filter(function (x) { return maObszar(x.obszar); }).map(function (x) {
        return '<button type="button" class="mi" data-m="tr-' + x.id + '"><b>🎓 ' + x.nazwa + "</b><small>" + x.opis + "</small></button>";
      }).join(""), true);
    var bwr = o.querySelector('[data-m="cw-wroc"]'); if (bwr) bwr.addEventListener("click", function () { zamknijOkno(); start(cwSt.trasa); });
    var bk = o.querySelector('[data-m="cw-koniec"]'); if (bk) bk.addEventListener("click", function () { zamknijOkno(); zapisz(KL_STAN, null); koniecCwiczenia(); });
    TRASY.forEach(function (x) { var b = o.querySelector('[data-m="tr-' + x.id + '"]'); if (b) b.addEventListener("click", function () { zamknijOkno(); zapisz(KL_STAN, null); start(x.id, false); }); });
  }
  function coNowego(wszystkie) {
    var lista = wszystkie ? NOWOSCI.filter(dlaMnie).slice(0, 8) : nowe();
    if (!lista.length) return;
    var nw = nowe().length;
    var o = okno('<div class="po-n">Co nowego' + (wszystkie ? "" : " · od Twojej ostatniej wizyty") + "</div>" +
      "<h2>" + (wszystkie ? "Nowości w pracawre.com" : nw === 1 ? "Nowość w pracawre.com" : nw + " nowości w pracawre.com") + "</h2>" +
      lista.map(function (n) {
        var d = n.data.split("-");
        return '<div class="nw"><b>' + n.tytul + "</b><small>" + n.gdzie + " · " + Number(d[2]) + "." + d[1] + "</small><p>" + n.opis + "</p>" +
          (n.start ? '<button type="button" data-start>Wybierz samouczek →</button>' : n.cw ? '<button type="button" data-cw>Wybierz ćwiczenie →</button>' : n.pokaz ? '<button type="button" data-pokaz="' + n.id + '">Pokaż mi →</button>' : "") + "</div>";
      }).join("") +
      '<div class="po-d"><span></span><button type="button" class="pri" data-ok>Rozumiem</button></div>');
    o.querySelector("[data-ok]").addEventListener("click", function () { zamknijOkno(); oznaczWidziane(); });
    var c = o.querySelector("[data-cw]"); if (c) c.addEventListener("click", function () { zamknijOkno(); oznaczWidziane(); menu(); });
    var s = o.querySelector("[data-start]"); if (s) s.addEventListener("click", function () { zamknijOkno(); oznaczWidziane(); menu(); });
    o.querySelectorAll("[data-pokaz]").forEach(function (b) {
      b.addEventListener("click", function () {
        var n = NOWOSCI.filter(function (x) { return x.id === b.dataset.pokaz; })[0];
        zamknijOkno(); oznaczWidziane();
        if (ta(n.pokaz.sciezka)) pokazJeden(n.pokaz);
        else { zapisz(KL_STAN, { pokaz: n.id, czas: Date.now() }); location.href = n.pokaz.sciezka; }
      });
    });
  }

  // ---- silnik oprowadzania ----
  function trasaTu() { return TRASY.filter(function (t) { return ta(t.sciezka); })[0] || null; }
  function widoczne(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
  }
  function znajdz(sel) { if (!sel) return null; var el = typeof sel === "function" ? sel() : document.querySelector(sel); return widoczne(el) ? el : null; }

  var T = null;   // {trasa, kroki (dostępne), i, cale}
  function start(id, cale) {
    var t = trasa(id);
    if (!t) return;
    if (t.cw) return startCw(t);
    if (!ta(t.sciezka)) { zapisz(KL_STAN, { trasa: id, i: 0, cale: cale, czas: Date.now() }); location.href = t.sciezka; return; }
    zapisz(KL_STAN, { trasa: id, i: 0, cale: cale, czas: Date.now() });
    // strona dociąga dane – chwila na pokazanie sekcji, potem tylko kroki, których elementy są widoczne
    setTimeout(function () {
      var kroki = t.kroki.filter(function (k) { return !k.el || znajdz(k.el); });
      var st = czytaj(KL_STAN) || {};
      T = { trasa: t, kroki: kroki, i: Math.min(st.trasa === id ? st.i || 0 : 0, kroki.length - 1), cale: cale };
      rysuj();
    }, 900);
  }
  function startCw(t) {
    var st = czytaj(KL_STAN) || {};
    if (!ta(t.sciezka)) { zapisz(KL_STAN, { trasa: t.id, i: st.trasa === t.id ? st.i || 0 : 0, czas: Date.now() }); location.href = t.sciezka; return; }
    apiL("samouczek").then(function (d) {
      CW = d.aktywny ? d : null;
      var i = st.trasa === t.id && CW ? st.i || 0 : 0;      // ćwiczenia nie ma na serwerze (posprzątane) – od początku
      zapisz(KL_STAN, { trasa: t.id, i: i, czas: Date.now() });
      setTimeout(function () { T = { trasa: t, kroki: t.kroki, i: i, cale: false }; rysuj(); }, 700);
    }).catch(function () {});
  }
  function nastepnaTrasa() {
    var i = TRASY.indexOf(T.trasa);
    for (var j = i + 1; j < TRASY.length; j++) if (maObszar(TRASY[j].obszar)) return TRASY[j];
    return null;
  }
  var petla = null;
  function zakoncz(gotowe, pauza) {
    ["pp-tour-tlo", "pp-tour-cel", "pp-tour-dym"].forEach(function (id) { var e = document.getElementById(id); if (e) e.remove(); });
    clearInterval(petla); petla = null;
    if (pauza && T && T.trasa.cw) {                  // ćwiczenie przerwane – wraca w tym samym miejscu (🎓 → „Wróć do ćwiczenia”)
      zapisz(KL_STAN, { trasa: T.trasa.id, i: T.i, czas: Date.now(), pauza: true });
      window.removeEventListener("keydown", klaw, true);
      window.removeEventListener("resize", pozycja); window.removeEventListener("scroll", pozycja, true);
      T = null; return;
    }
    window.removeEventListener("keydown", klaw, true);
    window.removeEventListener("resize", pozycja); window.removeEventListener("scroll", pozycja, true);
    zapisz(KL_STAN, null);
    T = null;
    if (gotowe) {
      var o = okno('<div class="po-n">🎓 Samouczek</div><h2>Gotowe – znasz już najważniejsze miejsca</h2>' +
        "<p>Samouczki innych sekcji znajdziesz pod przyciskiem <b>🎓</b> w pasku. Przećwicz pracę z leadem: 🎓 → „Ćwiczenie na przykładowym kliencie”.</p>" +
        '<div class="po-d"><span></span><button type="button" class="pri" data-ok>Wracam do pracy</button></div>');
      o.querySelector("[data-ok]").addEventListener("click", zamknijOkno);
    }
  }
  function klaw(e) {
    if (!T || e.defaultPrevented) return;
    if (T.trasa.cw && e.target && e.target.closest && e.target.closest("input, textarea, select, .pw-ed")) return;   // Esc w polu – dla strony
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); zakoncz(false, true); }
    else if (T.trasa.cw) return;                      // ćwiczenie: Enter i strzałki należą do pól, które agent wypełnia
    else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); dalej(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); wstecz(); }
  }
  function dalej(zKroku) {
    if (!T) return;
    var k = T.kroki[T.i];
    if (k.naDalej && !zKroku) {
      var b = document.querySelector("#pp-tour-dym [data-d]"); if (b) { b.disabled = true; b.textContent = "Chwila…"; }
      Promise.resolve(k.naDalej()).then(function (dalejTak) { if (dalejTak !== false) dalej(true); },
        function (e) { if (b) { b.disabled = false; b.textContent = "Spróbuj ponownie"; } var t = document.querySelector("#pp-tour-dym .pt-t"); if (t) t.insertAdjacentHTML("beforeend", "<p style='color:#c0392b'>" + String(e.message || e) + "</p>"); });
      return;
    }
    if (T.i < T.kroki.length - 1) { T.i++; zapisz(KL_STAN, { trasa: T.trasa.id, i: T.i, cale: T.cale, czas: Date.now() }); rysuj(); return; }
    var n = T.cale ? nastepnaTrasa() : null;
    if (n) { zapisz(KL_STAN, { trasa: n.id, i: 0, cale: true, czas: Date.now() }); location.href = n.sciezka; }
    else if (T.trasa.potem) { var p = T.trasa.potem; zapisz(KL_STAN, null); T = null; start(p); }   // 12.11: oprowadzanie i ćwiczenia = jeden samouczek
    else zakoncz(true);
  }
  function wstecz() { if (T && T.i > 0) { T.i--; zapisz(KL_STAN, { trasa: T.trasa.id, i: T.i, cale: T.cale, czas: Date.now() }); rysuj(); } }

  function warstwy() {
    styl();
    if (!document.getElementById("pp-tour-tlo")) {
      var tlo = document.createElement("div"); tlo.id = "pp-tour-tlo"; document.body.appendChild(tlo);
      var cel = document.createElement("div"); cel.id = "pp-tour-cel"; document.body.appendChild(cel);
      var d = document.createElement("div"); d.id = "pp-tour-dym"; d.setAttribute("role", "dialog"); d.setAttribute("aria-live", "polite"); document.body.appendChild(d);
      window.addEventListener("keydown", klaw, true);
      window.addEventListener("resize", pozycja); window.addEventListener("scroll", pozycja, true);
    }
  }
  function rysuj() {
    if (!T) return;
    if (!T.kroki.length) return dalej();
    warstwy();
    var k = T.kroki[T.i], ost = T.i === T.kroki.length - 1, n = ost && T.cale ? nastepnaTrasa() : null, cw = !!T.trasa.cw;
    k.od = Date.now();
    if (k.przed) try { k.przed(); } catch (e) {}
    var d = document.getElementById("pp-tour-dym");
    d.className = k.rozmowa ? "rozm" : "";
    document.getElementById("pp-tour-tlo").className = k.przepusc ? "przepusc" : "";
    var tekst = typeof k.tekst === "function" ? k.tekst() : k.tekst;
    d.innerHTML = '<div class="pt-n">' + T.trasa.nazwa + " · krok " + (T.i + 1) + " z " + T.kroki.length + "</div>" +
      "<h3>" + k.tytul + '</h3><div class="pt-t">' + tekst + "</div>" + (k.czekaj ? '<div class="pt-cz">Samouczek przejdzie dalej sam, gdy to zrobisz.</div><div class="pt-cz pt-brak" hidden></div>' : "") +
      '<div class="pt-p"><button type="button" class="pt-x" data-x>' + (cw ? "Przerwij" : "Zakończ") + '</button><span class="pt-s"></span>' +
      (cw ? "" : '<button type="button" data-w' + (T.i ? "" : " disabled") + ">← Wstecz</button>") +
      (k.czekaj ? "" : '<button type="button" class="pt-d" data-d>' + (k.dalejTxt || (!ost ? "Dalej →" : n ? n.nazwa + " →" : T.trasa.potem ? "Dalej: ćwiczenie →" : "Gotowe ✓")) + "</button>") + "</div>";
    d.querySelector("[data-x]").addEventListener("click", function () { zakoncz(false, true); });
    var bw = d.querySelector("[data-w]"); if (bw) bw.addEventListener("click", wstecz);
    var bd = d.querySelector("[data-d]"); if (bd) bd.addEventListener("click", function () { dalej(); });
    d.onclick = function (e) {
      var kb = e.target.closest("[data-kopiuj]");
      if (kb && navigator.clipboard) navigator.clipboard.writeText(kb.dataset.kopiuj).then(function () { kb.textContent = "✓ Skopiowano"; });
      if (e.target.closest("[data-otworz-l1]") && L(1)) location.hash = "#lead/samouczek/" + encodeURIComponent(L(1).id);
      if (e.target.closest("[data-tryb]")) try { if (typeof dzStart === "function") dzStart(); } catch (er) {}
    };
    clearInterval(petla); petla = null;
    if (k.czekaj || typeof k.el === "function" || cw) petla = setInterval(function () {
      if (!T || T.kroki[T.i] !== k) return;
      if (k.czekaj && k.czekaj(k)) { T.i++; zapisz(KL_STAN, { trasa: T.trasa.id, i: T.i, czas: Date.now() }); if (T.i >= T.kroki.length) return zakoncz(true); return rysuj(); }
      pozycja();
    }, 450);
    var el = znajdz(k.el);
    if (el) {
      var r = el.getBoundingClientRect();
      if (r.top < 50 || r.bottom > innerHeight - 20) el.scrollIntoView({ block: r.height > innerHeight * 0.6 ? "start" : "center" });
    }
    pozycja();
    if (bd) bd.focus({ preventScroll: true });
  }
  function pozycja() {
    if (!T) return;
    var k = T.kroki[T.i], el = znajdz(k.el), cel = document.getElementById("pp-tour-cel"), d = document.getElementById("pp-tour-dym");
    if (!cel || !d) return;
    var br = d.querySelector(".pt-brak");
    if (br) { br.hidden = !!el || !k.brak; if (!el && k.brak && br.innerHTML !== k.brak) br.innerHTML = k.brak; }
    if (!el) {
      cel.className = "srodek";
      d.style.left = Math.max(12, (innerWidth - d.offsetWidth) / 2) + "px";
      d.style.top = Math.max(60, (innerHeight - d.offsetHeight) / 2.4) + "px";
      return;
    }
    cel.className = "";
    var r = el.getBoundingClientRect(), m = 6;
    var top = Math.max(r.top - m, 2), bottom = Math.min(r.bottom + m, innerHeight - 4);
    cel.style.left = r.left - m + "px"; cel.style.top = top + "px";
    cel.style.width = r.width + 2 * m + "px"; cel.style.height = Math.max(bottom - top, 20) + "px";
    var dw = d.offsetWidth, dh = d.offsetHeight, x, y;
    var yBok = Math.min(Math.max(52, top), innerHeight - dh - 12);
    x = Math.min(Math.max(12, r.left), innerWidth - dw - 12);
    if (innerHeight - bottom > dh + 16) y = bottom + 12;
    else if (top - 48 > dh + 16) y = top - dh - 12;
    else if (r.left - m >= dw + 24) { x = r.left - m - dw - 12; y = yBok; }            // wysoki element – dymek obok, nie na nim
    else if (innerWidth - r.right - m >= dw + 24) { x = r.right + m + 12; y = yBok; }
    else {                                                                                  // nic nie pasuje – róg, który najmniej zasłania
      var naj = null;
      [[12, innerHeight - dh - 12], [innerWidth - dw - 12, innerHeight - dh - 12], [innerWidth - dw - 12, 52], [12, 52]].forEach(function (p) {
        var ox = Math.max(0, Math.min(p[0] + dw, r.right) - Math.max(p[0], r.left)), oy = Math.max(0, Math.min(p[1] + dh, r.bottom) - Math.max(p[1], r.top));
        if (!naj || ox * oy < naj[2]) naj = [p[0], p[1], ox * oy];
      });
      x = Math.max(12, naj[0]); y = Math.max(52, naj[1]);
    }
    d.style.left = x + "px"; d.style.top = y + "px";
  }
  function pokazJeden(p) {
    var t = { id: "pokaz", sciezka: p.sciezka, nazwa: "🎓 Nowość", kroki: [{ el: p.el, tytul: p.tytul, tekst: p.tekst }] };
    setTimeout(function () { T = { trasa: t, kroki: t.kroki, i: 0, cale: false }; rysuj(); }, 900);
  }

  // 12.11 (decyzja użytkownika): samouczek wyłączony w „Mój profil” – bez przycisku 🎓 i bez wznawiania oprowadzania;
  // „Co nowego” zostaje (bez wpisów, które zapraszają do samouczka)
  function wylaczony() {
    var k = KONTO; if (!k) try { k = JSON.parse(sessionStorage.getItem("pracawre-konto") || "null"); } catch (e) {}
    var u = k && k.profil && k.profil.ustawienia; return !!(u && u.samouczek === false);
  }
  function odswiez(k) { if (k) KONTO = k; if (wylaczony()) { document.querySelectorAll(".pp-sam").forEach(function (b) { b.remove(); }); if (T && !T.trasa.cw) zakoncz(false); } else przycisk(); }

  // ---- przycisk w pasku ----
  function przycisk() {
    var r = document.querySelector("#pracawre-pasek .pp-r");
    if (r && wylaczony()) { var x = r.querySelector(".pp-sam"); if (x) x.remove(); return true; }
    if (!r || r.querySelector(".pp-sam")) return !!r;
    styl();
    var b = document.createElement("button");
    b.type = "button"; b.className = "pp-sam"; b.title = "Samouczek – oprowadzanie i ćwiczenia";
    b.innerHTML = '🎓<span class="pp-sam-t">Samouczek</span>';
    b.addEventListener("click", menu);
    r.insertBefore(b, r.querySelector(".pp-konto"));
    licznik();
    return true;
  }

  function poStarcie() {
    var st = czytaj(KL_STAN);
    if (st && Date.now() - (st.czas || 0) > DOBA) { zapisz(KL_STAN, null); st = null; }   // 24 h bez ruchu – samouczek znika
    if (st && st.pokaz) {
      zapisz(KL_STAN, null);
      var n = NOWOSCI.filter(function (x) { return x.id === st.pokaz; })[0];
      if (n && ta(n.pokaz.sciezka)) pokazJeden(n.pokaz);
      return;
    }
    if (st && st.trasa && !wylaczony()) {
      var t = trasa(st.trasa);
      if (t && t.cw && st.pauza) { /* przerwane – wraca z menu 🎓 */ }
      else if (t && ta(t.sciezka)) { start(t.id, st.cale); return; }
    }
    // nowości – po zalogowaniu raz; nie na okno „Czy spotkania się odbyły?” (czekamy, aż zniknie)
    var proby = 0;
    (function czekaj() {
      if (!nowe().length) return;
      if (document.getElementById("pp-sp") || document.getElementById("pp-tour-ok") || document.getElementById("pp-prof")) { if (++proby < 300) setTimeout(czekaj, 2000); return; }
      coNowego(false);
    })();
  }

  function init() {
    var n = 0;
    (function sprobuj() { if (!przycisk() && ++n < 40) setTimeout(sprobuj, 250); })();
    var k = P.konto ? P.konto() : Promise.resolve(null);
    k.then(function (konto) {
      KONTO = konto;
      if (!konto) return;
      przycisk(); licznik();
      setTimeout(poStarcie, 600);
    });
  }

  window.PracawreSamouczek = { przycisk: przycisk, odswiez: odswiez, menu: menu, start: start, coNowego: coNowego, NOWOSCI: NOWOSCI, TRASY: TRASY };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
