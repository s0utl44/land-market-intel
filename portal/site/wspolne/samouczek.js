/* Samouczek pracawre.com (11.11.2026, decyzje użytkownika) – część (a): przycisk 🎓 w pasku obok konta (dla wszystkich),
   OPROWADZANIE (strona główna → Zimne telefony → Transakcje; podświetlenie miejsca + dymek z opisem, Wstecz / Dalej / Zakończ,
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
  var NOWOSCI = [
    { id: "2026-11-11-samouczek", data: "2026-11-11", gdzie: "Cała strona", tytul: "🎓 Samouczek",
      opis: "Oprowadzanie po stronie głównej, Zimnych telefonach i Transakcjach – co gdzie jest i co dzieje się po każdym kliknięciu. Włączysz je w każdej chwili przyciskiem 🎓 w pasku.",
      start: true },
    { id: "2026-11-11-sciaga-telefon", data: "2026-11-11", gdzie: "Zimne", obszar: "leady", dla: ["agent", "administracja"], tytul: "📋 Skrypt i obiekcje w trybie „Dzwonię”",
      opis: "Podczas dzwonienia otworzysz z boku skrypt rozmowy i odpowiedzi na obiekcje – z podręcznika agenta.",
      pokaz: { sciezka: "/leady/", el: "#dzwonPrz", tytul: "Skrypt i obiekcje", tekst: "Kliknij lwa <b>„Zacznij dzwonić”</b>. W pasku trybu „Dzwonię” jest przycisk <b>„📋 Skrypt i obiekcje”</b> – otwiera ściągę z boku, bez zasłaniania leada." } },
    { id: "2026-11-11-sciaga-spotkanie", data: "2026-11-11", gdzie: "Transakcje", obszar: "transakcje", dla: ["agent", "dyrektor"], tytul: "📋 Lista przed spotkaniem",
      opis: "W karcie transakcji przed spotkaniem pozyskowym – etapy spotkania i checklista, co zabrać i o co zapytać.",
      pokaz: { sciezka: "/transakcje/", el: "#tablica", tytul: "Lista przed spotkaniem", tekst: "Otwórz transakcję na etapie <b>Nowy</b>, <b>Spotkanie umówione</b> albo <b>Zadzwoń ponownie</b>. Pod przyciskami działań znajdziesz <b>„📋 Lista przed spotkaniem”</b>." } },
    { id: "2026-11-11-wdrozenie", data: "2026-11-11", gdzie: "Wdrożenie", obszar: "wdrozenie", tytul: "📘 Podręcznik agenta i Moja ścieżka",
      opis: "Menu ☰ → Biuro → Wdrożenie: podręcznik (zimny telefon, spotkanie, umowy, najem, notariusz) i plan pierwszych tygodni z zadaniami do odhaczenia.",
      pokaz: { sciezka: "/wdrozenie/", el: "#zakl", tytul: "Podręcznik i Moja ścieżka", tekst: "<b>Podręcznik</b> – rozdziały z „W skrócie” na początku i szukaniem po każdym słowie. <b>Moja ścieżka</b> – zadania na pierwsze tygodnie; przeczytany rozdział odhaczysz przyciskiem w jego stopce." } }
  ];

  // ---- OPROWADZANIE: trasy po kolei; krok bez el = dymek na środku; brak elementu na stronie = krok pominięty ----
  var TRASY = [
    { id: "glowna", sciezka: "/", nazwa: "Strona główna", kroki: [
      { tytul: "Witaj w pracawre.com", tekst: "Tu są wszystkie narzędzia biura WRE. W kilku krokach pokażę, co gdzie jest i co się dzieje po kliknięciu.<br><br>Przerwiesz w każdej chwili (<b>Esc</b> albo „Zakończ”), a wrócisz przyciskiem <b>🎓</b> w pasku. Po stronach przechodzisz strzałkami ← → albo przyciskami." },
      { el: "#pracawre-pasek .pp-otw", tytul: "Menu ☰", tekst: "Wszystkie narzędzia: <b>Zimne telefony</b>, <b>Transakcje</b>, <b>Generator umów</b>, <b>Kontakty</b>, <b>Wdrożenie</b>… Liczby przy nazwach to rzeczy do zrobienia. Na dole menu: motyw jasny / ciemny, <b>Mój profil</b>, <b>Zgłoś błąd</b>, Wyloguj." },
      { el: "#pracawre-pasek .pp-konto", tytul: "Twoje konto", tekst: "Otwiera to samo menu. W <b>„Mój profil”</b> połączysz swój kalendarz i pocztę Google – wtedy umówione spotkania same trafiają do kalendarza, a maile z klientami widać w transakcji." },
      { el: "#spotkaniaS", tytul: "Spotkania", tekst: "Spotkania na dziś i jutro. Po terminie zapytamy <b>„Czy spotkanie się odbyło?”</b> – odpowiadasz Tak / Nie od razu tutaj (albo w okienku na dowolnej stronie)." },
      { el: "#naDzis", tytul: "Moje zadania", tekst: "Zadania: zaległe, na dziś i na najbliższe 7 dni. Kliknięcie otwiera transakcję albo leada w Zimnych." },
      { el: "#celeS", tytul: "Moje cele", tekst: "Cele na miesiąc – ustala je z Tobą dyrektor. Pasek pokazuje, ile już zrobione." },
      { el: "#sprawyS", tytul: "Moje transakcje", tekst: "Otwarte sprawy, wynagrodzenie w toku i sukces w tym miesiącu; pigułki w kolorach etapów prowadzą do tablicy Transakcji." },
      { el: "#zimneS", tytul: "Zimne w tym tygodniu", tekst: "Odebrane telefony i umówione spotkania od poniedziałku – liczą się wszystkie Twoje telefony zapisane w systemie." },
      { el: "#podsS", tytul: "Podsumowanie od dyrektora", tekst: "Po odprawie dyrektor wysyła Ci podsumowanie i ustalenia – tutaj je przeczytasz." },
      { el: "#dzwonPrz", tytul: "Zacznij dzwonić", tekst: "Lew uruchamia tryb <b>„Dzwonię”</b> – system podaje lead po leadzie, Ty tylko dzwonisz i zapisujesz wynik. Lwa możesz przesunąć myszą w wygodne miejsce." }
    ] },
    { id: "zimne", sciezka: "/leady/", obszar: "leady", nazwa: "Zimne telefony", kroki: [
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
          "<li><b>Spotkanie umówione</b> – powstaje transakcja w <b>Transakcjach</b> na etapie „Spotkanie umówione” i spotkanie w HubSpot (oraz w Twoim kalendarzu Google).</li>" +
          "<li><b>Niekwalifikowany?</b> – biuro, deweloper, nieaktualne, duplikat – dotyczy tylko tego ogłoszenia.</li></ul>" +
          "Lead bez Twojego zadania wraca o północy do wspólnej puli." },
      { el: "#dzwonPrz", tytul: "Tryb „Dzwonię”", tekst: "Jeden lead naraz, wynik klawiszami 1–4, następny lead podaje się sam. Z boku otworzysz <b>„📋 Skrypt i obiekcje”</b>." }
    ] },
    { id: "transakcje", sciezka: "/transakcje/", obszar: "transakcje", nazwa: "Transakcje", kroki: [
      { el: "#lejki", tytul: "Transakcje", tekst: "Twoje sprawy od spotkania do faktury. Proces: <b>Nieruchomości</b> (domyślny), Finanse, DoneHome." },
      { el: "#tablica", tytul: "Tablica etapów", tekst: "Sprawa idzie od lewej do prawej: Spotkanie umówione → Umowa otwarta / Agencyjna / Wyłączność → Oferta pracująca → Oferta realna → Przedwstępna → Faktura → Opłacono. <b>Przeciągnij kartę</b>, żeby zmienić etap; przeciągnięcie na dół = stracona (z powodem)." },
      { tytul: "Co się dzieje przy zmianie etapu", tekst: "<ul class='pp-tour-l'>" +
          "<li>Po spotkaniu system zapyta o <b>źródło leada</b> – bez niego sprawa nie pójdzie dalej.</li>" +
          "<li>Umowę pośrednictwa przygotujesz z karty: <b>„📝 Wygeneruj”</b> → Generator umów z danymi klienta.</li>" +
          "<li><b>Przedwstępna, Faktura, Opłacono</b> – okno z ceną i wynagrodzeniem; tam też <b>„📄 Poproś o fakturę”</b>.</li>" +
          "<li>Etap, kwoty i czynności zapisują się w HubSpot same.</li></ul>" },
      { el: "#bLead", tytul: "+ Nowa transakcja", tekst: "Klient z polecenia albo telefonu do biura: najpierw telefon / e-mail – sprawdzimy, czy klienta już nie ma – potem źródło i etap." },
      { el: "#q", tytul: "Szukaj", tekst: "Po nazwie, kliencie, telefonie albo lokalizacji. Stracone sprawy znajdziesz pod tablicą." },
      { tytul: "Karta transakcji", tekst: "Kliknięcie w kartę otwiera sprawę: <b>Notatka, Telefon, Zadanie, Spotkanie</b>, strony transakcji, ogłoszenia, umowy i oś czasu (z pocztą, jeśli połączysz Google). Przed spotkaniem pozyskowym – <b>„📋 Lista przed spotkaniem”</b>." }
    ] }
  ];

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
    return P.aplikacje(KONTO).some(function (a) { return a.obszar === o; });
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
    return NOWOSCI.filter(function (n) { return w.indexOf(n.id) < 0 && Date.parse(n.data) >= od && dlaMnie(n); });
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
    var n = nowe().length, t = trasaTu();
    var o = okno(
      '<button type="button" class="mi" data-m="cale"><b>🎓 Oprowadzanie po stronie</b><small>Strona główna → Zimne telefony → Transakcje – co gdzie jest</small></button>' +
      (t && t.id !== "glowna" ? '<button type="button" class="mi" data-m="tu"><b>Tylko ta strona – ' + t.nazwa + "</b><small>Oprowadzanie po tym, co widzisz teraz</small></button>" : "") +
      '<button type="button" class="mi" data-m="nowosci"><b>Co nowego' + (n ? '<span class="pp-sam-n">' + n + "</span>" : "") + "</b><small>Zmiany w pracawre.com z ostatnich tygodni</small></button>" +
      '<button type="button" class="mi" disabled><b>Ćwiczenie na przykładowym kliencie</b><small>Od zimnego telefonu do faktury – wkrótce</small></button>', true);
    o.querySelector('[data-m="cale"]').addEventListener("click", function () { zamknijOkno(); start("glowna", true); });
    var tu = o.querySelector('[data-m="tu"]'); if (tu) tu.addEventListener("click", function () { zamknijOkno(); start(t.id, false); });
    o.querySelector('[data-m="nowosci"]').addEventListener("click", function () { coNowego(true); });
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
          (n.start ? '<button type="button" data-start>Zacznij oprowadzanie →</button>' : n.pokaz ? '<button type="button" data-pokaz="' + n.id + '">Pokaż mi →</button>' : "") + "</div>";
      }).join("") +
      '<div class="po-d"><span>Wszystkie nowości: 🎓 → „Co nowego”</span><button type="button" class="pri" data-ok>Rozumiem</button></div>');
    o.querySelector("[data-ok]").addEventListener("click", function () { zamknijOkno(); oznaczWidziane(); });
    var s = o.querySelector("[data-start]"); if (s) s.addEventListener("click", function () { zamknijOkno(); oznaczWidziane(); start("glowna", true); });
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
  function znajdz(sel) { if (!sel) return null; var el = document.querySelector(sel); return widoczne(el) ? el : null; }

  var T = null;   // {trasa, kroki (dostępne), i, cale}
  function start(id, cale) {
    var t = TRASY.filter(function (x) { return x.id === id; })[0];
    if (!t) return;
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
  function nastepnaTrasa() {
    var i = TRASY.indexOf(T.trasa);
    for (var j = i + 1; j < TRASY.length; j++) if (maObszar(TRASY[j].obszar)) return TRASY[j];
    return null;
  }
  function zakoncz(gotowe) {
    ["pp-tour-tlo", "pp-tour-cel", "pp-tour-dym"].forEach(function (id) { var e = document.getElementById(id); if (e) e.remove(); });
    window.removeEventListener("keydown", klaw, true);
    window.removeEventListener("resize", pozycja); window.removeEventListener("scroll", pozycja, true);
    zapisz(KL_STAN, null);
    T = null;
    if (gotowe) {
      var o = okno('<div class="po-n">🎓 Samouczek</div><h2>Gotowe – znasz już najważniejsze miejsca</h2>' +
        "<p>Oprowadzanie włączysz ponownie przyciskiem <b>🎓</b> w pasku – tam też są <b>nowości</b>. Ćwiczenie na przykładowym kliencie (od zimnego telefonu do faktury) dodamy wkrótce.</p>" +
        '<div class="po-d"><span></span><button type="button" class="pri" data-ok>Wracam do pracy</button></div>');
      o.querySelector("[data-ok]").addEventListener("click", zamknijOkno);
    }
  }
  function klaw(e) {
    if (!T || e.defaultPrevented) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); zakoncz(false); }
    else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); dalej(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); wstecz(); }
  }
  function dalej() {
    if (!T) return;
    if (T.i < T.kroki.length - 1) { T.i++; zapisz(KL_STAN, { trasa: T.trasa.id, i: T.i, cale: T.cale, czas: Date.now() }); rysuj(); return; }
    var n = T.cale ? nastepnaTrasa() : null;
    if (n) { zapisz(KL_STAN, { trasa: n.id, i: 0, cale: true, czas: Date.now() }); location.href = n.sciezka; }
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
    var k = T.kroki[T.i], ost = T.i === T.kroki.length - 1, n = ost && T.cale ? nastepnaTrasa() : null;
    var d = document.getElementById("pp-tour-dym");
    d.innerHTML = '<div class="pt-n">' + T.trasa.nazwa + " · krok " + (T.i + 1) + " z " + T.kroki.length + "</div>" +
      "<h3>" + k.tytul + '</h3><div class="pt-t">' + k.tekst + "</div>" +
      '<div class="pt-p"><button type="button" class="pt-x" data-x>Zakończ</button><span class="pt-s"></span>' +
      '<button type="button" data-w' + (T.i ? "" : " disabled") + ">← Wstecz</button>" +
      '<button type="button" class="pt-d" data-d>' + (!ost ? "Dalej →" : n ? n.nazwa + " →" : "Gotowe ✓") + "</button></div>";
    d.querySelector("[data-x]").addEventListener("click", function () { zakoncz(false); });
    d.querySelector("[data-w]").addEventListener("click", wstecz);
    d.querySelector("[data-d]").addEventListener("click", dalej);
    var el = znajdz(k.el);
    if (el) {
      var r = el.getBoundingClientRect();
      if (r.top < 50 || r.bottom > innerHeight - 20) el.scrollIntoView({ block: r.height > innerHeight * 0.6 ? "start" : "center" });
    }
    pozycja();
    d.querySelector("[data-d]").focus({ preventScroll: true });
  }
  function pozycja() {
    if (!T) return;
    var k = T.kroki[T.i], el = znajdz(k.el), cel = document.getElementById("pp-tour-cel"), d = document.getElementById("pp-tour-dym");
    if (!cel || !d) return;
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
    if (innerHeight - bottom > dh + 16) y = bottom + 12;
    else if (top - 48 > dh + 16) y = top - dh - 12;
    else { y = Math.max(52, innerHeight - dh - 16); }
    x = Math.min(Math.max(12, r.left), innerWidth - dw - 12);
    if (y > top - dh && y < bottom && r.width > innerWidth - dw - 40) x = innerWidth - dw - 12;   // duży element – dymek w rogu
    d.style.left = x + "px"; d.style.top = y + "px";
  }
  function pokazJeden(p) {
    var t = { id: "pokaz", sciezka: p.sciezka, nazwa: "🎓 Nowość", kroki: [{ el: p.el, tytul: p.tytul, tekst: p.tekst }] };
    setTimeout(function () { T = { trasa: t, kroki: t.kroki, i: 0, cale: false }; rysuj(); }, 900);
  }

  // ---- przycisk w pasku ----
  function przycisk() {
    var r = document.querySelector("#pracawre-pasek .pp-r");
    if (!r || r.querySelector(".pp-sam")) return !!r;
    styl();
    var b = document.createElement("button");
    b.type = "button"; b.className = "pp-sam"; b.title = "Samouczek – oprowadzanie po stronie i nowości";
    b.innerHTML = '🎓<span class="pp-sam-t">Samouczek</span><span class="pp-sam-n" hidden></span>';
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
    if (st && st.trasa) {
      var t = TRASY.filter(function (x) { return x.id === st.trasa; })[0];
      if (t && ta(t.sciezka)) { start(t.id, st.cale); return; }
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

  window.PracawreSamouczek = { przycisk: przycisk, menu: menu, start: start, coNowego: coNowego, NOWOSCI: NOWOSCI, TRASY: TRASY };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
