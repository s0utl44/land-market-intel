/* Wspólny pasek pracawre.com: powrót na stronę główną, przełączanie podstron, jeden motyw jasny/ciemny dla całej
   witryny i płynne przejścia między stronami. Dołączany w <head> każdej podstrony:
     <script src="/wspolne/pasek.js"></script>
   - motyw: localStorage "pracawre-motyw" = auto | light | dark (wspólny, bo wszystkie podstrony są w jednej domenie);
     na <html> ustawia data-theme="light|dark" i klasę "dark" (Tailwind) – każda aplikacja reaguje po swojemu;
   - pasek: wstawiany sam na początku <body>; aplikacja React (hydratacja) ustawia <html data-pasek="react">,
     renderuje pusty <div id="pracawre-pasek"> i po zamontowaniu woła PracawrePasek.wypelnij(el). */
(function () {
  "use strict";
  var KLUCZ = "pracawre-motyw";
  var html = document.documentElement;
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  var APPS = [
    { href: "/umowy/", obszar: "umowy", grupa: "dokumenty", opis: "Sprzedaż · najem · zarządzanie · PL / EN", nazwa: "Generator umów", ikona: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>' },
    { href: "/protokoly/", obszar: "protokoly", grupa: "dokumenty", opis: "Protokoły ze zdjęciami · weryfikacja najemcy", nazwa: "Zarządzanie", ikona: '<path d="M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1z"/><path d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><path d="m9 14 2 2 4-4"/>' },
    { href: "/radar/", obszar: "radar", grupa: "rynek", opis: "Działki na Dolnym Śląsku – oferty, ceny, pozwolenia", nazwa: "Radar działek", zastrzezony: true, ikona: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12l6-6"/>' },
    { href: "/leady/", obszar: "leady", grupa: "sprzedaz", opis: "Zimne telefony – prywatne ogłoszenia mieszkań", nazwa: "Zimne", zastrzezony: true, ikona: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>' },
    { href: "/transakcje/", obszar: "transakcje", grupa: "sprzedaz", opis: "Lejek transakcji – Twoje sprawy, etapy i sumy", nazwa: "Transakcje", zastrzezony: true, ikona: '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="11" rx="1"/><rect x="17" y="4" width="4" height="7" rx="1"/>' },
    { href: "/odprawa/", obszar: "odprawa", grupa: "sprzedaz", opis: "Tygodniowy raport pracy agentów z HubSpot", nazwa: "Odprawa", zastrzezony: true, tylkoAdmin: true, ikona: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>' }
  ];
  // grupa i opis – zakładki w grupach (pasek) i kafelki na pulpicie (strona główna)
  // zastrzezony: zakładka ukryta, dopóki konto (panel Administracja) nie potwierdzi dostępu – bez mignięcia u osób bez uprawnień
  // (Radar działek – decyzja użytkownika 25.10: zakładka i kafelek tylko u osób z dostępem; logowanie bez logo DoneHome)
  var IKONY = {
    auto: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none"/>',
    light: '<circle cx="12" cy="12" r="4.5"/><path d="M12 1.5v2.5M12 20v2.5M1.5 12H4M20 12h2.5M4.6 4.6l1.8 1.8M17.6 17.6l1.8 1.8M4.6 19.4l1.8-1.8M17.6 6.4l1.8-1.8"/>',
    dark: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'
  };
  var NAZWY_MOTYWOW = { auto: "Auto", light: "Jasny", dark: "Ciemny" };

  function wybor() {
    try { var w = localStorage.getItem(KLUCZ); return w === "light" || w === "dark" ? w : "auto"; } catch (e) { return "auto"; }
  }
  function ciemny() { var w = wybor(); return w === "dark" || (w === "auto" && !!(mq && mq.matches)); }

  function zastosuj() {
    var c = ciemny();
    html.setAttribute("data-theme", c ? "dark" : "light");
    html.setAttribute("data-motyw", wybor());
    if (html.classList) html.classList.toggle("dark", c);
    html.style.colorScheme = c ? "dark" : "light";
    odswiezMotyw();
    try { window.dispatchEvent(new CustomEvent("pracawre-motyw", { detail: { ciemny: c, wybor: wybor() } })); } catch (e) {}
  }
  function ustaw(w) { try { localStorage.setItem(KLUCZ, w); } catch (e) {} zastosuj(); }

  // Widok agenta (28.10, decyzja użytkownika): administrator ogląda całą witrynę tak, jak agent – przełącznik w menu konta,
  // pamiętany w localStorage (wspólny dla wszystkich podstron). Aplikacje pytają PracawrePasek.widokAgenta() i słuchają
  // zdarzenia „pracawre-widok-agenta”. Tylko wygląd strony – uprawnienia serwera bez zmian.
  var KLUCZ_AGENT = "pracawre-widok-agenta";
  function widokAgenta() { try { return localStorage.getItem(KLUCZ_AGENT) === "1"; } catch (e) { return false; } }
  function ustawWidokAgenta(v) {
    try { localStorage.setItem(KLUCZ_AGENT, v ? "1" : "0"); } catch (e) {}
    zmianaWidoku();
  }
  function zmianaWidoku() {
    html.classList.toggle("pw-agent", widokAgenta());
    document.querySelectorAll("#pracawre-pasek").forEach(function (el) { var k = kontoZapamietane(); if (k) uprawnieniaWPasku(el, k); });
    try { window.dispatchEvent(new CustomEvent("pracawre-widok-agenta", { detail: { agent: widokAgenta() } })); } catch (e) {}
  }

  var CSS =
    "@view-transition{navigation:auto}" +
    "::view-transition-old(root),::view-transition-new(root){animation-duration:.22s}" +
    "#pracawre-pasek{flex:none;position:relative;z-index:60}" +
    // 28.10 (decyzja użytkownika): górny pasek = tylko ☰, logo i nazwa otwartego narzędzia; wszystko inne (narzędzia z liczbami,
    // konto, motyw, zgłoś błąd, widok agenta, administracja, wyloguj) w wysuwanej karcie z lewej na całą wysokość
    ".pp{view-transition-name:pracawre-pasek;box-sizing:border-box;display:flex;align-items:center;gap:4px;height:40px;" +
    "padding:0 max(12px,env(safe-area-inset-right)) 0 max(8px,env(safe-area-inset-left));background:#141518;color:#d9d5cc;" +
    "border-bottom:2px solid #c9a03c;font:600 13px/1 Lato,'Segoe UI',system-ui,-apple-system,sans-serif;letter-spacing:.01em}" +
    ".pp *,.pp-sz *{box-sizing:border-box}" +
    ".pp a,.pp button,.pp-sz a,.pp-sz button{all:unset;box-sizing:border-box;cursor:pointer;display:inline-flex;align-items:center;gap:8px;height:30px;padding:0 10px;" +
    "border-radius:8px;color:#bdb8ad;white-space:nowrap;transition:background .15s,color .15s}" +
    ".pp a:hover,.pp button:hover,.pp-sz a:hover,.pp-sz button:hover{background:rgba(255,255,255,.07);color:#fff}" +
    ".pp a:focus-visible,.pp button:focus-visible,.pp-sz a:focus-visible,.pp-sz button:focus-visible{outline:2px solid #c9a03c;outline-offset:-2px}" +
    ".pp svg,.pp-sz svg{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}" +
    ".pp .pp-dom{padding:0 8px 0 4px}.pp .pp-dom img{height:24px;width:auto;display:block}" +
    ".pp .pp-sep{width:1px;height:18px;background:rgba(255,255,255,.16);margin:0 6px;flex:none}" +
    ".pp [hidden],.pp-sz [hidden]{display:none!important}" +
    ".pp .pp-otw{position:relative;width:34px;padding:0;justify-content:center}.pp .pp-otw svg{width:19px;height:19px}" +
    ".pp .pp-tu{color:#f3efe6;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}" +
    ".pp .pp-r{margin-left:auto;display:flex;gap:6px;align-items:center;flex:none}" +
    ".pp-kropka{position:absolute;top:3px;right:3px;width:9px;height:9px;border-radius:50%;background:#e5534b;border:2px solid #141518}" +
    ".pp .pp-ag{height:24px;padding:0 9px;border-radius:999px;background:#c9a03c;color:#141518;font-size:11.5px;font-weight:900}" +
    ".pp .pp-ag:hover{background:#e0b850;color:#141518}" +
    ".pp .pp-av,.pp-sz .pp-av{width:26px;height:26px;border-radius:50%;background:#c9a03c;color:#141518;display:grid;place-items:center;font-size:11px;font-weight:900;flex:none}" +
    ".pp .pp-konto{padding:0 4px}" +
    // karta z lewej
    ".pp-sz-tlo{position:fixed;inset:0;z-index:2147482000;background:rgba(10,10,9,.45);opacity:0;transition:opacity .2s}" +
    ".pp-sz{position:fixed;top:0;bottom:0;left:0;z-index:2147482001;width:min(380px,92vw);display:flex;flex-direction:column;" +
    "background:#17181b;color:#d9d5cc;border-right:1px solid #2c2e33;box-shadow:24px 0 60px rgba(0,0,0,.35);transform:translateX(-102%);" +
    "transition:transform .22s ease;font:600 13.5px/1.25 Lato,'Segoe UI',system-ui,-apple-system,sans-serif;overflow:hidden}" +
    ".pp-sz.otw{transform:none}.pp-sz-tlo.otw{opacity:1}" +
    ".pp-sz .pp-sz-g{display:flex;align-items:center;gap:8px;padding:12px 12px 10px 16px;border-bottom:2px solid #c9a03c;flex:none}" +
    ".pp-sz .pp-sz-g a{padding:0}.pp-sz .pp-sz-g img{height:28px;display:block}.pp-sz .pp-sz-x{margin-left:auto;width:34px;padding:0;justify-content:center}" +
    ".pp-sz .pp-sz-w{flex:1;overflow:auto;padding:10px 10px 6px;display:flex;flex-direction:column;gap:2px}" +
    ".pp-sz .pp-sz-w>*{flex:none}" +
    ".pp-sz .pp-kto{display:flex;align-items:center;gap:11px;padding:10px 8px 14px}.pp-sz .pp-kto .pp-av{width:38px;height:38px;font-size:14px}" +
    ".pp-sz .pp-kto b{display:block;color:#f3efe6;font-size:15px}.pp-sz .pp-kto small{display:block;color:#8d887e;font-weight:400;font-size:12px;margin-top:2px}" +
    ".pp-sz .pp-gt{font-size:10.5px;font-weight:900;letter-spacing:.2em;text-transform:uppercase;color:#8d887e;padding:14px 10px 6px}" +
    ".pp-sz a.pp-z{height:auto;min-height:46px;padding:9px 10px;align-items:flex-start;white-space:normal}" +
    ".pp-sz .pp-z>svg{margin-top:1px;width:18px;height:18px;color:#c9a03c}" +
    ".pp-sz .pp-z>span{display:flex;flex-direction:column;gap:3px;min-width:0}.pp-sz .pp-z b{color:#f3efe6;font-size:14px}" +
    ".pp-sz .pp-z small{font-weight:400;font-size:12px;color:#8d887e;line-height:1.35}" +
    ".pp-sz .pp-z[aria-current=page]{background:rgba(201,160,60,.14);box-shadow:inset 3px 0 0 #c9a03c}" +
    ".pp-sz .pp-l{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}.pp-sz .pp-l:empty{display:none}" +
    ".pp-sz .pp-l i{font-style:normal;font-size:11px;font-weight:800;padding:2px 8px;border-radius:999px;background:#2a2c31;color:#e6e3dc}" +
    ".pp-sz .pp-l i.w{background:#c9a03c;color:#141518}" +
    ".pp-sz .pp-sz-d{flex:none;border-top:1px solid #2c2e33;padding:10px;display:flex;flex-direction:column;gap:2px}" +
    ".pp-sz .pp-sz-d>button,.pp-sz .pp-sz-d>a{height:36px;width:100%}" +
    ".pp-sz .pp-motywy{display:flex;gap:2px;margin:0 0 6px;background:#101113;border-radius:9px;padding:3px}" +
    ".pp-sz .pp-motywy button{flex:1;justify-content:center;height:28px;padding:0 6px;font-size:12px}" +
    ".pp-sz .pp-motywy button[aria-pressed=true]{background:#33363c;color:#fff}" +
    ".pp-sz .pp-agent[aria-pressed=true]{color:#fff;background:rgba(201,160,60,.16)}" +
    ".pp-sz .pp-agent b,.pp-sz .pp-n{margin-left:auto;font-size:11px;color:#8d887e}" +
    ".pp-sz .pp-n{background:#c9a03c;color:#141518;border-radius:999px;padding:1px 7px;font-weight:900}" +
    "@media (prefers-reduced-motion:reduce){.pp-sz,.pp-sz-tlo{transition:none}}" +
    "@media print{#pracawre-pasek,.pw-app{display:none!important}}" +
    // pasek aplikacji pod wspólnym paskiem (Generator umów, Zarządzanie) – decyzja użytkownika 25.10: wszędzie jednakowy,
    // bez własnego logo (logo WRE jest we wspólnym pasku). Aplikacja daje tylko znaczniki: .pw-app > .pw-app-tytul,
    // .pw-app-nav > .pw-app-link (aria-current=page), .pw-app-akcje > .pw-app-btn (.pri – główna akcja, .ikona – sama ikona)
    ".pw-app{position:sticky;top:0;z-index:30;box-sizing:border-box;display:flex;align-items:center;gap:6px;height:56px;min-width:0;" +
    "padding:0 max(16px,env(safe-area-inset-right)) 0 max(16px,env(safe-area-inset-left));background:rgba(248,246,241,.92);" +
    "backdrop-filter:blur(10px);border-bottom:1px solid #e2ddd2;color:#1f1d1a;font:600 14px/1 Lato,'Segoe UI',system-ui,sans-serif}" +
    "html[data-theme=dark] .pw-app{background:rgba(23,24,26,.92);border-color:#2e3034;color:#e6e3dc}" +
    ".pw-app *{box-sizing:border-box}" +
    ".pw-app-tytul{flex:none;font-size:16px;font-weight:900;white-space:nowrap;margin-right:10px;color:inherit;text-decoration:none}" +
    ".pw-app-nav{display:flex;align-items:center;gap:2px;min-width:0;overflow-x:auto;scrollbar-width:none}.pw-app-nav::-webkit-scrollbar{display:none}" +
    ".pw-app-link,.pw-app-btn{all:unset;box-sizing:border-box;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:7px;" +
    "height:36px;padding:0 14px;border-radius:999px;white-space:nowrap;font-weight:600;transition:background .15s,border-color .15s,color .15s}" +
    ".pw-app-link{color:#6b665d}.pw-app-link:hover{background:rgba(0,0,0,.05);color:#1f1d1a}" +
    ".pw-app-link[aria-current=page]{background:#1f1d1a;color:#fff}" +
    "html[data-theme=dark] .pw-app-link{color:#a39e94}html[data-theme=dark] .pw-app-link:hover{background:rgba(255,255,255,.06);color:#fff}" +
    "html[data-theme=dark] .pw-app-link[aria-current=page]{background:#e6e3dc;color:#17181a}" +
    ".pw-app-akcje{margin-left:auto;display:flex;align-items:center;gap:8px;flex:none}" +
    ".pw-app-btn{position:relative;border:1px solid #e2ddd2;background:#fff;color:#1f1d1a}.pw-app-btn:hover{border-color:#c9a03c}" +
    ".pw-app-btn.pri{background:#1f1d1a;border-color:#1f1d1a;color:#fff;font-weight:700}.pw-app-btn.pri:hover{background:#9b7a26;border-color:#9b7a26}" +
    ".pw-app-btn.ikona{width:36px;padding:0}" +
    "html[data-theme=dark] .pw-app-btn{background:#222427;border-color:#3a3c40;color:#e6e3dc}" +
    "html[data-theme=dark] .pw-app-btn.pri{background:#e6e3dc;border-color:#e6e3dc;color:#17181a}html[data-theme=dark] .pw-app-btn.pri:hover{background:#d9b55a;border-color:#d9b55a}" +
    ".pw-app-link svg,.pw-app-btn svg{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}" +
    ".pw-app-link:focus-visible,.pw-app-btn:focus-visible{outline:2px solid #c9a03c;outline-offset:2px}" +
    "@media (max-width:1250px){.pw-app-link svg,.pw-app-btn:not(.pri):not(.ikona) svg{display:none}.pw-app-link,.pw-app-btn{padding:0 11px}.pw-app-btn.ikona{padding:0}}" +
    "@media (max-width:900px){.pw-app{overflow-x:auto}.pw-app-tytul{display:none}}";

  // grupy zakładek – te same na pulpicie (strona główna) i w pasku (decyzja użytkownika 25.10)
  var GRUPY = [{ id: "dokumenty", nazwa: "Dokumenty" }, { id: "sprzedaz", nazwa: "Sprzedaż" }, { id: "rynek", nazwa: "Rynek" }];

  // --- Układ witryny (30.10, decyzja użytkownika: super administrator – obszar „uklad” w Kartotece – układa menu i stronę
  // główną: kolejność, grupy, nazwy). Dokument z /administracja/api/uklad, w sessionStorage jak konto (bez mrugania).
  // Brak układu = domyślne APPS i GRUPY; narzędzie, którego nie ma w układzie (nowe), trafia do swojej grupy domyślnej.
  var UKLAD = null, UKLAD_NR = 0, ukladP = null;
  function ukladZapamietany() {
    try { var u = JSON.parse(sessionStorage.getItem("pracawre-uklad") || "null"); if (u) { UKLAD = u.uklad || {}; UKLAD_NR = u.nr || 0; } return u; } catch (e) { return null; }
  }
  function ukladZapisz(d) {
    UKLAD = d.uklad || {}; UKLAD_NR = d.nr || 0;
    try { sessionStorage.setItem("pracawre-uklad", JSON.stringify({ uklad: UKLAD, nr: UKLAD_NR })); } catch (e) {}
  }
  function uklad(swiezy) {
    if (ukladP && !swiezy) return ukladP;
    var zap = ukladZapamietany();
    var p = fetch("/administracja/api/uklad", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return { uklad: UKLAD || {}, nr: UKLAD_NR };
        var zmiana = JSON.stringify(d.uklad) !== JSON.stringify(UKLAD);
        ukladZapisz(d);
        if (zmiana) { przerysujMenu(); try { window.dispatchEvent(new CustomEvent("pracawre-uklad", { detail: d })); } catch (e) {} }
        return d;
      }).catch(function () { return { uklad: UKLAD || {}, nr: UKLAD_NR }; });
    ukladP = zap && !swiezy ? Promise.resolve(zap) : p;
    return ukladP;
  }
  // narzędzia z nazwami i opisami z układu
  function appsUkladu() {
    var nazwy = ((UKLAD || {}).menu || {}).aplikacje || {};
    return APPS.map(function (a) {
      var z = nazwy[a.obszar] || {}, o = {};
      for (var k in a) o[k] = a[k];
      if (z.nazwa) o.nazwa = String(z.nazwa); if (z.opis != null) o.opis = String(z.opis);
      return o;
    });
  }
  // grupy menu: [{id, nazwa, apps: [narzędzie]}] – w kolejności z układu
  function menu() {
    var apps = appsUkladu(), m = (UKLAD || {}).menu || {};
    var grupy = (m.grupy && m.grupy.length ? m.grupy : GRUPY.map(function (g) {
      return { id: g.id, nazwa: g.nazwa, aplikacje: APPS.filter(function (a) { return a.grupa === g.id; }).map(function (a) { return a.obszar; }) };
    })).map(function (g) { return { id: String(g.id), nazwa: String(g.nazwa || ""), aplikacje: (g.aplikacje || []).slice() }; });
    var uzyte = {};
    grupy.forEach(function (g) { g.aplikacje = g.aplikacje.filter(function (o) { if (uzyte[o]) return false; uzyte[o] = 1; return true; }); });
    apps.forEach(function (a) {
      if (uzyte[a.obszar]) return;
      var g = grupy.filter(function (x) { return x.id === a.grupa; })[0] || grupy[grupy.length - 1];
      if (!g) { g = { id: a.grupa, nazwa: a.grupa, aplikacje: [] }; grupy.push(g); }
      g.aplikacje.push(a.obszar);
    });
    return grupy.map(function (g) {
      return { id: g.id, nazwa: g.nazwa, apps: g.aplikacje.map(function (o) { return apps.filter(function (a) { return a.obszar === o; })[0]; }).filter(Boolean) };
    });
  }
  function przerysujMenu() {
    document.querySelectorAll("#pracawre-pasek").forEach(function (el) {
      var w = el.querySelector(".pp-grupy"); if (!w || el.querySelector(".pp-ed")) return;
      w.innerHTML = zakladki(kontoZapamietane());
      var k = kontoZapamietane(); if (k) uprawnieniaWPasku(el, k);
      var tu = appsUkladu().filter(naStronie)[0], t = el.querySelector(".pp-tu"); if (tu && t) t.textContent = tu.nazwa;
    });
  }

  function styl(id, css) {
    if (document.getElementById(id || "pracawre-pasek-styl")) return;
    var s = document.createElement("style");
    s.id = id || "pracawre-pasek-styl";
    s.textContent = css || CSS;
    (document.head || html).appendChild(s);
  }

  function svg(d) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + d + "</svg>"; }
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }

  function odswiezMotyw() {
    document.querySelectorAll(".pp-motywy [data-motyw]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.motyw === wybor())); });
  }

  function link(a, znane) {
    var ukryj = znane ? !widoczny(a, znane) : a.zastrzezony;
    return '<a class="pp-z" href="' + a.href + '" data-obszar="' + a.obszar + '"' + (naStronie(a) ? ' aria-current="page"' : "") + (ukryj ? " hidden" : "") + ">" +
      svg(a.ikona) + "<span><b>" + esc(a.nazwa) + "</b><small>" + esc(a.opis) + '</small><span class="pp-l" data-l="' + a.obszar + '"></span></span></a>';
  }
  function zakladki(znane) {
    return menu().map(function (g) {
      return '<div class="pp-grp" data-grupa="' + esc(g.id) + '"><div class="pp-gt">' + esc(g.nazwa) + "</div>" +
        g.apps.map(function (a) { return link(a, znane); }).join("") + "</div>";
    }).join("");
  }

  function wypelnij(el) {
    if (!el) return;
    styl();
    styl("pracawre-uklad-styl", CSS_ED);
    var znane = kontoZapamietane();
    ukladZapamietany();
    var tu = appsUkladu().filter(naStronie)[0] || (location.pathname.indexOf("/administracja") === 0 ? { nazwa: "Administracja" } : null);
    el.innerHTML =
      '<nav class="pp" aria-label="pracawre.com">' +
      '<button type="button" class="pp-otw" data-sz title="Menu – narzędzia, konto, zgłoś błąd" aria-haspopup="dialog" aria-expanded="false">' +
      svg('<path d="M4 6h16M4 12h16M4 18h16"/>') + '<i class="pp-kropka" hidden></i></button>' +
      '<a class="pp-dom" href="/" title="Strona główna"><img src="/wspolne/logo-wre.png" alt="WRE Nieruchomości"></a>' +
      (tu ? '<span class="pp-sep" aria-hidden="true"></span><span class="pp-tu">' + esc(tu.nazwa) + "</span>" : "") +
      '<div class="pp-r"><button type="button" class="pp-ag" data-agent-wyl hidden title="Wyłącz widok agenta">Widok agenta ✕</button>' +
      '<button type="button" class="pp-konto" data-sz title="Konto"><span class="pp-av">?</span></button></div></nav>' +
      // wysuwana karta (position:fixed) – poza .pp, żeby przejścia stron (view-transition) jej nie ruszały
      '<div class="pp-sz-tlo" hidden></div>' +
      '<aside class="pp-sz" role="dialog" aria-modal="true" aria-label="Menu" hidden>' +
      '<div class="pp-sz-g"><a href="/" title="Strona główna"><img src="/wspolne/logo-wre.png" alt="WRE Nieruchomości"></a>' +
      '<button type="button" class="pp-sz-x" data-zamknij title="Zamknij (Esc)">' + svg('<path d="M6 6l12 12M18 6 6 18"/>') + "</button></div>" +
      '<div class="pp-sz-w"><div class="pp-kto"><span class="pp-av">?</span><span class="pp-kto-t"><b>Konto</b><small></small></span></div>' +
      '<a class="pp-z" href="/"' + (location.pathname === "/" ? ' aria-current="page"' : "") + ">" + svg('<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/>') +
      "<span><b>Strona główna</b><small>Moje zadania i to, co czeka na zrobienie</small></span></a>" +
      '<div class="pp-grupy">' + zakladki(znane) + "</div>" +
      '<div class="pp-grp pp-biuro" hidden><div class="pp-gt">Biuro</div><a class="pp-z pp-adm" href="/administracja/"' +
      (location.pathname.indexOf("/administracja") === 0 ? ' aria-current="page"' : "") + ">" +
      svg('<path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>') +
      '<span><b>Administracja</b><small>Konta, uprawnienia, zgłoszenia błędów, stan systemu</small><span class="pp-l" data-l="administracja"></span></span></a></div>' +
      "</div>" +
      '<div class="pp-sz-d"><div class="pp-motywy" role="group" aria-label="Motyw">' +
      ["auto", "light", "dark"].map(function (m) { return '<button type="button" data-motyw="' + m + '" aria-pressed="false">' + svg(IKONY[m]) + NAZWY_MOTYWOW[m] + "</button>"; }).join("") +
      "</div>" +
      '<button type="button" data-zglos>' + svg('<path d="M8 2l1.9 1.9M16 2l-1.9 1.9M9 7.1V6a3 3 0 1 1 6 0v1.1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6zM12 20v-9M6.5 13H3M21 13h-3.5M6 9.4 3.5 7.5M18 9.4l2.5-1.9M6 17.6 3.5 19.5M18 17.6l2.5 1.9"/>') +
      "<span>Zgłoś błąd albo uwagę</span></button>" +
      '<button type="button" class="pp-agent" data-agent hidden aria-pressed="false">' + svg('<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>') +
      "<span>Widok agenta</span><b>wył.</b></button>" +
      '<button type="button" data-ukl-menu hidden>' + svg('<path d="M4 6h10M4 12h16M4 18h7"/><path d="m17 3 4 4-8 8h-4v-4z"/>') + "<span>Ułóż menu</span></button>" +
      '<a href="/oauth2/sign_out?rd=%2F">' + svg('<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4"/>') + "<span>Wyloguj</span></a>" +
      "</div></aside>";
    var sz = el.querySelector(".pp-sz"), tlo = el.querySelector(".pp-sz-tlo");
    el.querySelectorAll("[data-sz]").forEach(function (b) { b.addEventListener("click", function () { otworz(el); }); });
    el.querySelector("[data-zamknij]").addEventListener("click", function () { zamknij(); });
    tlo.addEventListener("click", function () { zamknij(); });
    sz.addEventListener("click", function (e) { if (e.target.closest("a") && !ED) zamknij(true); });
    el.querySelectorAll("[data-motyw]").forEach(function (b) { b.addEventListener("click", function () { ustaw(b.dataset.motyw); }); });
    el.querySelector("[data-zglos]").addEventListener("click", function () { zamknij(); zglos(); });
    el.querySelector("[data-agent]").addEventListener("click", function () { ustawWidokAgenta(!widokAgenta()); });
    el.querySelector("[data-agent-wyl]").addEventListener("click", function () { ustawWidokAgenta(false); });
    el.querySelector("[data-ukl-menu]").addEventListener("click", function () { edytujMenu(el); });
    odswiezMotyw();
    if (znane) uprawnieniaWPasku(el, znane);
    konto().then(function (k) { uprawnieniaWPasku(el, k); });
    uklad();
  }

  // karta z lewej: ☰ albo awatar otwiera; ✕, klik obok, Esc albo wybór pozycji zamyka
  var otwarta = null, przedKarta = null;
  function otworz(el) {
    var sz = el.querySelector(".pp-sz"), tlo = el.querySelector(".pp-sz-tlo");
    otwarta = el; przedKarta = document.activeElement;
    sz.hidden = false; tlo.hidden = false;
    requestAnimationFrame(function () { sz.classList.add("otw"); tlo.classList.add("otw"); });
    el.querySelectorAll("[data-sz]").forEach(function (b) { b.setAttribute("aria-expanded", "true"); });
    sz.querySelector("[data-zamknij]").focus({ preventScroll: true });
    konto().then(function (k) { if (k) liczby(k, function (obszar, lista) { wpiszLiczby(el, obszar, lista); }); });
  }
  function zamknij(odRazu) {
    var el = otwarta; if (!el) return;
    otwarta = null;
    if (ED && !odRazu) { ED = null; setTimeout(function () { if (!otwarta) wypelnij(el); }, 240); }   // edycja menu bez zapisu
    var sz = el.querySelector(".pp-sz"), tlo = el.querySelector(".pp-sz-tlo");
    sz.classList.remove("otw"); tlo.classList.remove("otw");
    el.querySelectorAll("[data-sz]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
    setTimeout(function () { if (otwarta !== el) { sz.hidden = true; tlo.hidden = true; } }, odRazu ? 0 : 230);
    if (!odRazu && przedKarta && przedKarta.focus) przedKarta.focus({ preventScroll: true });
  }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && otwarta) zamknij(); });

  // Liczby „do zrobienia” z aplikacji – w karcie przy narzędziach i na pulpicie (ta sama funkcja). naKazde(obszar, [[n, tekst, ważne]]).
  // Błąd albo brak odpowiedzi aplikacji = bez liczb. Wyniki w pamięci na minutę (karta otwierana wiele razy).
  var odm = function (n, jedna, kilka, wiele) { return n + " " + (n === 1 ? jedna : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? kilka : wiele); };
  var LICZBY = {}, liczbyCzas = 0;
  function liczby(k, naKazde) {
    var widac = function (o) { return aplikacje(k).some(function (a) { return a.obszar === o; }); };
    var agent = widokAgenta();
    var dalej = function (obszar, lista) { LICZBY[obszar] = lista.filter(function (x) { return x[0] > 0; }); naKazde(obszar, LICZBY[obszar]); };
    if (Date.now() - liczbyCzas < 60000) { Object.keys(LICZBY).forEach(function (o) { naKazde(o, LICZBY[o]); }); return; }
    liczbyCzas = Date.now();
    var json = function (url, opcje) { return fetch(url, Object.assign({ credentials: "same-origin" }, opcje)).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); };
    if (widac("leady")) json("/leady/api/pulpit").then(function (d) {
      // 29.10: „Leady” → „Zimne” (moje zimne na dziś: do zadzwonienia / zadzwoń ponownie; bez „zakwalifikowanych”)
      dalej("leady", [[d.do_wziecia, odm(d.do_wziecia, "ogłoszenie do wzięcia", "ogłoszenia do wzięcia", "ogłoszeń do wzięcia")],
        [d.moje.nowy, d.moje.nowy + " do zadzwonienia dziś", true],
        [d.moje.ponownie, d.moje.ponownie + " do ponownego telefonu", true]]);
    }).catch(function () {});
    if (widac("umowy")) json("/umowy/api/szkiceLista", { method: "POST", headers: { "Content-Type": "application/json" }, body: "[]" }).then(function (d) {
      var n = (d.wynik || []).length;
      dalej("umowy", [[n, odm(n, "niezapisana umowa", "niezapisane umowy", "niezapisanych umów"), true]]);
    }).catch(function () {});
    if (k.admin && !agent) dalej("administracja", [[k.zgloszeniaNowe || 0, odm(k.zgloszeniaNowe || 0, "nowe zgłoszenie", "nowe zgłoszenia", "nowych zgłoszeń"), true]]);
  }
  function wpiszLiczby(el, obszar, lista) {
    var m = el.querySelector('.pp-l[data-l="' + obszar + '"]');
    if (m) m.innerHTML = lista.map(function (x) { return '<i class="' + (x[2] ? "w" : "") + '">' + esc(x[1]) + "</i>"; }).join("");
  }

  // Uprawnienia (panel Administracja): bez dostępu do obszaru – podstrona znika z paska; administrator – przycisk panelu.
  // Pamięć w sessionStorage, żeby pasek nie mrugał przy przechodzeniu między stronami.
  var kontoP = null;
  function kontoZapamietane() {
    try { return JSON.parse(sessionStorage.getItem("pracawre-konto") || "null"); } catch (e) { return null; }
  }
  function widoczny(a, k) {
    var p = (k.obszary || {})[a.obszar];
    if (a.tylkoAdmin && k.admin && widokAgenta()) return false;   // widok agenta: bez zakładek tylko dla administratorów
    return a.zastrzezony ? p === "dostep" || p === "admin" : p !== "brak";
  }
  function mozeUklad(k) { return !!k && (k.obszary || {}).uklad === "admin" && !widokAgenta(); }
  function naStronie(a) { return location.pathname.indexOf(a.href) === 0 || location.pathname + "/" === a.href; }
  // aplikacje, do których konto ma dostęp (kafelki strony głównej); k = null – tylko te bez zastrzeżeń
  function aplikacje(k) {
    var kol = [];
    menu().forEach(function (g) { kol = kol.concat(g.apps); });
    return kol.filter(function (a) { return k ? widoczny(a, k) : !a.zastrzezony; });
  }
  function konto() {
    if (kontoP) return kontoP;
    var zap = kontoZapamietane();
    var swieze = fetch("/administracja/api/ja", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (k) { if (k) try { sessionStorage.setItem("pracawre-konto", JSON.stringify(k)); } catch (e) {} return k; })
      .catch(function () { return null; });
    kontoP = zap ? Promise.resolve(zap) : swieze;
    if (zap) swieze.then(function (k) { if (k) { kontoP = Promise.resolve(k); document.querySelectorAll("#pracawre-pasek").forEach(function (el) { uprawnieniaWPasku(el, k); }); } });
    return kontoP;
  }
  function uprawnieniaWPasku(el, k) {
    if (!k || !el) return;
    APPS.forEach(function (a) {
      el.querySelectorAll('[data-obszar="' + a.obszar + '"]').forEach(function (link) { link.hidden = !widoczny(a, k); });
    });
    el.querySelectorAll(".pp-grp[data-grupa]").forEach(function (g) { g.hidden = !g.querySelector("a:not([hidden])"); });
    el.querySelector("[data-ukl-menu]").hidden = !mozeUklad(k);
    var nazwa = k.nazwa || (k.email || "").split("@")[0], ag = widokAgenta() && k.admin;
    el.querySelectorAll(".pp-av").forEach(function (a) { a.textContent = inicjaly(nazwa); });
    el.querySelector(".pp-konto").title = nazwa;
    el.querySelector(".pp-kto-t").innerHTML = "<b>" + esc(nazwa) + "</b><small>" + esc(k.email || "") + "</small>";
    el.querySelector(".pp-biuro").hidden = !k.admin || ag;
    el.querySelector(".pp-adm").href = k.zgloszeniaNowe ? "/administracja/#zgloszenia" : "/administracja/";
    el.querySelector(".pp-kropka").hidden = !(k.admin && !ag && k.zgloszeniaNowe);
    var przel = el.querySelector("[data-agent]");
    przel.hidden = !k.admin;
    przel.setAttribute("aria-pressed", String(ag));
    przel.querySelector("b").textContent = ag ? "wł." : "wył.";
    el.querySelector("[data-agent-wyl]").hidden = !ag;
  }
  function inicjaly(nazwa) {
    var cz = nazwa.split(/[\s.]+/).filter(Boolean);
    return ((cz[0] || "?")[0] + (cz.length > 1 ? cz[cz.length - 1][0] : "")).toUpperCase();
  }

  function sam() {
    if (html.getAttribute("data-pasek") === "react") return;   // aplikacja React wstawia pasek sama, po hydratacji
    var el = document.getElementById("pracawre-pasek");
    if (!el) {
      el = document.createElement("div");
      el.id = "pracawre-pasek";
      document.body.insertBefore(el, document.body.firstChild);
    }
    wypelnij(el);
  }

  // --- edycja menu w karcie z lewej (30.10, super administrator): przeciąganie za ⋮⋮ (albo strzałki), nazwy i opisy
  // w polach, nowa grupa, pusta grupa do usunięcia; Zapisz → /administracja/api/uklad (cały dokument, nr wersji)
  var CSS_ED =
    ".pp-ed{display:flex;flex-direction:column;gap:10px;padding:4px 2px}" +
    ".pp-ed .pp-ed-i{font-weight:400;font-size:12.5px;color:#8d887e;line-height:1.4;margin:2px 4px 4px}" +
    ".pp-ed .pp-eg{border:1px solid #2c2e33;border-radius:12px;padding:8px;background:#1b1c20}" +
    ".pp-ed .pp-eg.nad,.pp-ed .pp-eal.nad{outline:2px dashed #c9a03c;outline-offset:2px}" +
    ".pp-ed .pp-egh,.pp-ed .pp-ea{display:flex;align-items:center;gap:6px}" +
    ".pp-ed .pp-eal{display:flex;flex-direction:column;gap:6px;margin-top:8px;min-height:30px}" +
    ".pp-ed .pp-ea{background:#232429;border-radius:9px;padding:6px}" +
    ".pp-ed .pp-ea svg{color:#c9a03c;width:16px;height:16px}" +
    ".pp-ed .pp-ea>span:not(.uch){flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}" +
    ".pp-ed input{all:unset;box-sizing:border-box;width:100%;min-width:0;padding:4px 7px;border-radius:7px;border:1px solid transparent;color:#f3efe6;font-weight:700;font-size:13.5px}" +
    ".pp-ed input.op{font-weight:400;font-size:12px;color:#a8a399}" +
    ".pp-ed .pp-egh input{font-size:11px;font-weight:900;letter-spacing:.18em;text-transform:uppercase;color:#c9a03c}" +
    ".pp-ed input:hover{border-color:#3a3c42}.pp-ed input:focus{border-color:#c9a03c;background:#141518}" +
    ".pp-ed .uch{cursor:grab;color:#6f6a61;padding:4px 2px;font-size:14px;letter-spacing:-2px;user-select:none;flex:none}" +
    ".pp-ed .uch:hover{color:#c9a03c}" +
    ".pp-ed button.m{width:24px;height:24px;padding:0;justify-content:center;font-size:12px;flex:none;color:#8d887e}" +
    ".pp-ed .ciag{opacity:.4}" +
    ".pp-sz .pp-sz-d .pp-ed-st{display:flex;gap:6px;flex-wrap:wrap}" +
    ".pp-sz .pp-sz-d .pp-ed-st button{height:34px;flex:1;justify-content:center;border:1px solid #33363c}" +
    ".pp-sz .pp-sz-d .pp-ed-st button.pri{background:#c9a03c;color:#141518;border-color:#c9a03c}" +
    ".pp-sz .pp-sz-d .pp-ed-bl{color:#f08b82;font-size:12.5px;padding:4px}";
  var ED = null;      // {grupy:[{id, nazwa, aplikacje:[obszar]}], aplikacje:{obszar:{nazwa, opis}}}
  function edytujMenu(el) {
    var k = kontoZapamietane();
    if (!mozeUklad(k)) return;
    uklad(true).then(function () {
      var m = menu(), nazwy = {};
      appsUkladu().forEach(function (a) { nazwy[a.obszar] = { nazwa: a.nazwa, opis: a.opis }; });
      ED = { grupy: m.map(function (g) { return { id: g.id, nazwa: g.nazwa, aplikacje: g.apps.map(function (a) { return a.obszar; }) }; }), aplikacje: nazwy };
      if (otwarta !== el) otworz(el);
      rysujEd(el);
    });
  }
  function rysujEd(el) {
    var w = el.querySelector(".pp-sz-w"), d = el.querySelector(".pp-sz-d");
    var apps = {}; APPS.forEach(function (a) { apps[a.obszar] = a; });
    w.innerHTML = '<div class="pp-ed"><div class="pp-ed-i">Układ menu dla wszystkich. Przeciągnij za ⋮⋮ (albo strzałki) – kolejność grup i narzędzi, ' +
      'narzędzie do innej grupy. Kliknij nazwę albo opis, żeby zmienić. Każdy widzi tylko narzędzia, do których ma dostęp.</div>' +
      ED.grupy.map(function (g, gi) {
        return '<div class="pp-eg" data-g="' + gi + '"><div class="pp-egh"><span class="uch" title="Przeciągnij grupę">⋮⋮</span>' +
          '<input data-gn="' + gi + '" value="' + esc(g.nazwa) + '" aria-label="Nazwa grupy" placeholder="Nazwa grupy">' +
          '<button type="button" class="m" data-gm="' + gi + '|-1" title="Wyżej">↑</button><button type="button" class="m" data-gm="' + gi + '|1" title="Niżej">↓</button>' +
          (g.aplikacje.length ? "" : '<button type="button" class="m" data-gu="' + gi + '" title="Usuń pustą grupę">✕</button>') + "</div>" +
          '<div class="pp-eal" data-gl="' + gi + '">' + g.aplikacje.map(function (o) {
            var a = apps[o], n = ED.aplikacje[o] || {};
            return '<div class="pp-ea" data-a="' + o + '"><span class="uch" title="Przeciągnij narzędzie">⋮⋮</span>' + svg(a.ikona) +
              '<span><input data-an="' + o + '" value="' + esc(n.nazwa) + '" aria-label="Nazwa narzędzia"><input class="op" data-ao="' + o + '" value="' + esc(n.opis) + '" aria-label="Opis narzędzia" placeholder="opis"></span>' +
              '<button type="button" class="m" data-am="' + o + '|-1" title="Wyżej">↑</button><button type="button" class="m" data-am="' + o + '|1" title="Niżej">↓</button></div>';
          }).join("") + "</div></div>";
      }).join("") + '<button type="button" data-gnowa style="height:34px;justify-content:center;border:1px dashed #3a3c42">+ Nowa grupa</button></div>';
    d.hidden = false;
    var st = d.querySelector(".pp-ed-st");
    if (!st) {
      d.insertAdjacentHTML("afterbegin", '<div class="pp-ed-wr"><div class="pp-ed-bl" hidden></div><div class="pp-ed-st"><button type="button" class="pri" data-ezap>Zapisz menu</button>' +
        '<button type="button" data-eanul>Anuluj</button><button type="button" data-edom title="Układ menu jak na początku (domyślny)">Domyślne</button></div></div>');
      [].forEach.call(d.children, function (c) { if (!c.classList.contains("pp-ed-wr")) c.hidden = true; });
    }
  }
  function koniecEd(el, otwarte) {
    ED = null;
    zamknij(true);
    wypelnij(el);                                   // karta i grupy od nowa, z bieżącym układem
    if (otwarte) otworz(el);
  }
  function przesunApp(o, kier) {
    var gi = ED.grupy.findIndex(function (g) { return g.aplikacje.indexOf(o) >= 0; }), g = ED.grupy[gi], i = g.aplikacje.indexOf(o);
    g.aplikacje.splice(i, 1);
    if (i + kier >= 0 && i + kier <= g.aplikacje.length) g.aplikacje.splice(i + kier, 0, o);
    else if (ED.grupy[gi + kier]) { var c = ED.grupy[gi + kier].aplikacje; if (kier < 0) c.push(o); else c.unshift(o); }
    else g.aplikacje.splice(i, 0, o);
  }
  function zapiszMenu(el, domyslne) {
    var bl = el.querySelector(".pp-ed-bl");
    var nowy = JSON.parse(JSON.stringify(UKLAD || {}));
    if (domyslne) delete nowy.menu;
    else {
      var bazowe = {}; APPS.forEach(function (a) { bazowe[a.obszar] = a; });
      var nazwy = {};
      Object.keys(ED.aplikacje).forEach(function (o) {
        var n = ED.aplikacje[o], z = {};
        if (n.nazwa && n.nazwa.trim() && n.nazwa.trim() !== bazowe[o].nazwa) z.nazwa = n.nazwa.trim();
        if (n.opis != null && n.opis.trim() !== bazowe[o].opis) z.opis = n.opis.trim();
        if (z.nazwa || z.opis != null) nazwy[o] = z;
      });
      if (ED.grupy.some(function (g) { return !g.nazwa.trim(); })) { bl.textContent = "Każda grupa musi mieć nazwę."; bl.hidden = false; return; }
      nowy.menu = { grupy: ED.grupy.map(function (g) { return { id: g.id, nazwa: g.nazwa.trim(), aplikacje: g.aplikacje }; }), aplikacje: nazwy };
    }
    fetch("/administracja/api/uklad", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ uklad: nowy, nr: UKLAD_NR }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Błąd " + r.status); return j; }); })
      .then(function (j) {
        ukladZapisz({ uklad: nowy, nr: j.nr }); ukladP = null;
        koniecEd(el, true);
        try { window.dispatchEvent(new CustomEvent("pracawre-uklad", { detail: { uklad: nowy, nr: j.nr } })); } catch (e) {}
      })
      .catch(function (e) { bl.textContent = e.message; bl.hidden = false; });
  }
  // zdarzenia edytora – raz na dokument (karta może być przerysowana)
  var ciagniety = null;
  document.addEventListener("input", function (e) {
    if (!ED || !e.target.closest(".pp-ed")) return;
    var t = e.target;
    if (t.dataset.gn != null) ED.grupy[+t.dataset.gn].nazwa = t.value;
    if (t.dataset.an) ED.aplikacje[t.dataset.an].nazwa = t.value;
    if (t.dataset.ao) ED.aplikacje[t.dataset.ao].opis = t.value;
  });
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("#pracawre-pasek");
    if (!el || !ED) return;
    var b = e.target.closest("button"); if (!b) return;
    if (b.hasAttribute("data-ezap")) return zapiszMenu(el);
    if (b.hasAttribute("data-edom")) { if (confirm("Przywrócić domyślny układ menu (kolejność, grupy i nazwy)?")) zapiszMenu(el, true); return; }
    if (b.hasAttribute("data-eanul")) return koniecEd(el, true);
    if (b.hasAttribute("data-gnowa")) { ED.grupy.push({ id: "g" + Date.now().toString(36), nazwa: "Nowa grupa", aplikacje: [] }); rysujEd(el); var i = el.querySelectorAll("[data-gn]"); i[i.length - 1].select(); return; }
    if (b.dataset.gu != null) { ED.grupy.splice(+b.dataset.gu, 1); return rysujEd(el); }
    if (b.dataset.gm) { var p = b.dataset.gm.split("|"), gi = +p[0], c = gi + +p[1]; if (ED.grupy[c]) { var g = ED.grupy.splice(gi, 1)[0]; ED.grupy.splice(c, 0, g); } return rysujEd(el); }
    if (b.dataset.am) { var q = b.dataset.am.split("|"); przesunApp(q[0], +q[1]); return rysujEd(el); }
  }, true);
  // przeciąganie – tylko za uchwyt ⋮⋮ (pola tekstowe dalej da się zaznaczać)
  document.addEventListener("pointerdown", function (e) {
    var u = e.target.closest && e.target.closest(".pp-ed .uch");
    if (u) u.parentNode.closest("[data-a], [data-g]").draggable = true;
  });
  document.addEventListener("dragstart", function (e) {
    var x = e.target.closest && e.target.closest(".pp-ed [draggable=true]"); if (!x) return;
    ciagniety = x.dataset.a ? { a: x.dataset.a } : { g: +x.dataset.g };
    e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", "uklad"); } catch (er) {}
    x.classList.add("ciag"); e.stopPropagation();
  });
  document.addEventListener("dragend", function () {
    document.querySelectorAll(".pp-ed [draggable]").forEach(function (x) { x.draggable = false; x.classList.remove("ciag"); });
    document.querySelectorAll(".pp-ed .nad").forEach(function (x) { x.classList.remove("nad"); });
    ciagniety = null;
  });
  document.addEventListener("dragover", function (e) {
    if (!ciagniety || !ED) return;
    var cel = ciagniety.a ? e.target.closest(".pp-eal") : e.target.closest(".pp-eg");
    if (!cel) return;
    e.preventDefault();
    document.querySelectorAll(".pp-ed .nad").forEach(function (x) { x.classList.remove("nad"); });
    cel.classList.add("nad");
  });
  document.addEventListener("drop", function (e) {
    if (!ciagniety || !ED) return;
    var el = e.target.closest("#pracawre-pasek"); if (!el) return;
    e.preventDefault();
    if (ciagniety.a) {
      var lista = e.target.closest(".pp-eal"); if (!lista) return;
      var gi = +lista.dataset.gl, przed = e.target.closest("[data-a]"), o = ciagniety.a;
      ED.grupy.forEach(function (g) { var i = g.aplikacje.indexOf(o); if (i >= 0) g.aplikacje.splice(i, 1); });
      var docel = ED.grupy[gi].aplikacje, i2 = przed && przed.dataset.a !== o ? docel.indexOf(przed.dataset.a) : -1;
      if (i2 >= 0 && e.clientY > przed.getBoundingClientRect().top + przed.offsetHeight / 2) i2++;
      if (i2 >= 0) docel.splice(i2, 0, o); else docel.push(o);
    } else {
      var na = e.target.closest(".pp-eg"); if (!na) return;
      var z = ciagniety.g, c = +na.dataset.g;
      if (z !== c) { var g = ED.grupy.splice(z, 1)[0]; ED.grupy.splice(c, 0, g); }
    }
    ciagniety = null;
    rysujEd(el);
  });

  // Kartoteka (wspólna baza osób i mieszkań) – panel na całe okno w ramce, otwierany z Generatora i Protokołów
  // (bez linku w pasku – decyzja użytkownika). parametry: {osoba: id} albo {mieszkanie: id}; poZamknieciu – np. odświeżenie.
  // poWyborze – tryb wyboru (Generator „Z kartoteki”): karta ma przycisk „Wstaw”, który zamyka panel i oddaje {tabela, id}.
  function kartoteka(parametry, poZamknieciu, poWyborze) {
    if (document.getElementById("pracawre-kartoteka")) return;
    if (!document.getElementById("pracawre-kartoteka-styl")) {
      var st = document.createElement("style");
      st.id = "pracawre-kartoteka-styl";
      st.textContent = "#pracawre-kartoteka{position:fixed;inset:0;z-index:2147483000;background:rgba(15,14,12,.5);display:flex;padding:14px;" +
        "animation:pkPoj .18s ease-out}#pracawre-kartoteka iframe{flex:1;border:0;border-radius:16px;background:#f4f2ed;" +
        "box-shadow:0 24px 70px rgba(0,0,0,.35)}html[data-theme=dark] #pracawre-kartoteka iframe{background:#17181a}" +
        "@keyframes pkPoj{from{opacity:0;transform:scale(.985)}to{opacity:1;transform:none}}" +
        "@media (max-width:640px){#pracawre-kartoteka{padding:0}#pracawre-kartoteka iframe{border-radius:0}}";
      document.head.appendChild(st);
    }
    var q = "osadzona=1" + (poWyborze ? "&wybor=1" : "");
    for (var k in parametry || {}) q += "&" + encodeURIComponent(k) + "=" + encodeURIComponent(parametry[k]);
    var tlo = document.createElement("div");
    tlo.id = "pracawre-kartoteka";
    tlo.innerHTML = '<iframe title="Kartoteka" src="/kartoteka/?' + q + '"></iframe>';
    var poprzedni = document.activeElement, przewijanie = document.documentElement.style.overflow;
    function zamknij() {
      tlo.remove(); window.removeEventListener("message", wiad); document.removeEventListener("keydown", klaw);
      document.documentElement.style.overflow = przewijanie;
      if (poprzedni && poprzedni.focus) poprzedni.focus();
      if (poZamknieciu) poZamknieciu();
    }
    function wiad(e) {
      if (e.origin !== location.origin || !e.data) return;
      if (e.data.typ === "kartoteka-zamknij") zamknij();
      if (e.data.typ === "kartoteka-wybor" && poWyborze) { zamknij(); poWyborze({ tabela: e.data.tabela, id: e.data.id }); }
    }
    function klaw(e) { if (e.key === "Escape") zamknij(); }
    tlo.addEventListener("click", function (e) { if (e.target === tlo) zamknij(); });
    window.addEventListener("message", wiad); document.addEventListener("keydown", klaw);
    document.documentElement.style.overflow = "hidden";
    document.body.appendChild(tlo);
    tlo.querySelector("iframe").focus();
  }

  // --- Zgłoś błąd: jeden formularz dla całej witryny (obszary, rodzaj, opis, zrzut ekranu) → panel Administracja ---------
  var OBSZARY_ZGL = [
    { id: "ogolne", nazwa: "Ogólne", opis: "strona główna, logowanie, pasek" },
    { id: "umowy", nazwa: "Generator umów", sciezka: "/umowy" },
    { id: "protokoly", nazwa: "Zarządzanie", sciezka: "/protokoly" },
    { id: "kartoteka", nazwa: "Kartoteka", sciezka: "/kartoteka" },
    { id: "radar", nazwa: "Radar działek", sciezka: "/radar" },
    { id: "leady", nazwa: "Zimne", sciezka: "/leady" },
    { id: "transakcje", nazwa: "Transakcje", sciezka: "/transakcje" },
    { id: "odprawa", nazwa: "Odprawa", sciezka: "/odprawa" }
  ];
  var RODZAJE_ZGL = [["blad", "Błąd"], ["poprawka", "Poprawka"], ["pomysl", "Pomysł"]];
  var STANY_ZGL = { nowe: "Nowe", w_toku: "W toku", zrobione: "Zrobione", odrzucone: "Odrzucone" };
  var CSS_ZGL =
    "#pp-zgl{position:fixed;inset:0;z-index:2147483001;background:rgba(15,14,12,.55);display:grid;place-items:center;padding:16px;" +
    "font:15px/1.45 Lato,'Segoe UI',system-ui,sans-serif;animation:pkPoj .15s ease-out;--k:#fff;--t:#1f1d1a;--m:#6b665d;--l:#e2ddd2;--p:#faf8f4;--z:#c9a03c;--zd:#9b7a26}" +
    "html[data-theme=dark] #pp-zgl{--k:#212326;--t:#e8e5de;--m:#a39e94;--l:#33363a;--p:#1c1e21;--zd:#d9b55a}" +
    "#pp-zgl *{box-sizing:border-box}" +
    "#pp-zgl .ok{background:var(--k);color:var(--t);width:min(560px,100%);max-height:calc(100vh - 32px);overflow:auto;border-radius:18px;" +
    "box-shadow:0 24px 70px rgba(0,0,0,.35);padding:22px 24px}" +
    "#pp-zgl h2{margin:0 0 4px;font-size:20px;font-weight:900;display:flex;align-items:center;gap:10px}" +
    "#pp-zgl h2 button{margin-left:auto}" +
    "#pp-zgl .op{color:var(--m);font-size:13.5px;margin:0 0 16px}" +
    "#pp-zgl .et{font-size:12px;color:var(--m);margin:14px 0 6px;font-weight:700}" +
    "#pp-zgl .cz{display:flex;flex-wrap:wrap;gap:6px}" +
    "#pp-zgl .cz button,#pp-zgl .sg button{all:unset;cursor:pointer;padding:7px 13px;border-radius:999px;border:1px solid var(--l);font-weight:700;font-size:13px}" +
    "#pp-zgl .cz button[aria-pressed=true]{background:rgba(201,160,60,.16);border-color:var(--z);color:var(--zd)}" +
    "#pp-zgl .sg{display:inline-flex;background:var(--p);border:1px solid var(--l);border-radius:999px;padding:3px;gap:2px}" +
    "#pp-zgl .sg button{border:0;padding:6px 14px}#pp-zgl .sg button[aria-pressed=true]{background:var(--t);color:var(--k)}" +
    "#pp-zgl textarea{width:100%;min-height:120px;border-radius:12px;border:1px solid var(--l);background:var(--k);color:var(--t);padding:10px 12px;font:inherit;resize:vertical;outline:none}" +
    "#pp-zgl textarea:focus{border-color:var(--z);box-shadow:0 0 0 4px rgba(201,160,60,.15)}" +
    "#pp-zgl .zr{display:flex;align-items:center;gap:10px;flex-wrap:wrap}" +
    "#pp-zgl .zr img{max-height:70px;max-width:140px;border-radius:8px;border:1px solid var(--l)}" +
    "#pp-zgl .b{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:7px;height:38px;padding:0 16px;white-space:nowrap;border-radius:999px;border:1px solid var(--l);font-weight:700;font-size:14px}" +
    "#pp-zgl .b.p{background:var(--t);color:var(--k);border-color:var(--t)}#pp-zgl .b[disabled]{opacity:.5;pointer-events:none}" +
    "#pp-zgl .b.x{width:38px;padding:0;justify-content:center}" +
    "#pp-zgl .st{display:flex;gap:8px;justify-content:flex-end;align-items:center;margin-top:18px}#pp-zgl .st .in{margin-right:auto;font-size:12.5px;color:var(--m)}" +
    "#pp-zgl .bl{color:#b3261e;font-size:13px;margin-top:8px}" +
    "#pp-zgl details{margin-top:18px;border-top:1px solid var(--l);padding-top:12px}#pp-zgl summary{cursor:pointer;font-weight:700;font-size:14px}" +
    "#pp-zgl .mz{padding:9px 0;border-bottom:1px solid var(--l);font-size:13.5px}#pp-zgl .mz:last-child{border:0}" +
    "#pp-zgl .mz small{display:block;color:var(--m)}#pp-zgl .sz{font-size:11px;font-weight:900;padding:2px 8px;border-radius:999px;background:rgba(201,160,60,.16);color:var(--zd);margin-left:6px}";

  function zglos() {
    if (document.getElementById("pp-zgl")) return;
    if (!document.getElementById("pp-zgl-styl")) {
      var st = document.createElement("style"); st.id = "pp-zgl-styl";
      st.textContent = CSS_ZGL + "@keyframes pkPoj{from{opacity:0}to{opacity:1}}"; document.head.appendChild(st);
    }
    var tu = OBSZARY_ZGL.filter(function (o) { return o.sciezka && location.pathname.indexOf(o.sciezka) === 0; })[0];
    var stan = { obszary: [tu ? tu.id : "ogolne"], rodzaj: "blad", zrzut: null };
    var tlo = document.createElement("div"); tlo.id = "pp-zgl";
    var poprzedni = document.activeElement;
    function zamknij() { tlo.remove(); document.removeEventListener("keydown", klaw); document.removeEventListener("paste", wklej); if (poprzedni && poprzedni.focus) poprzedni.focus(); }
    function klaw(e) { if (e.key === "Escape") zamknij(); }
    function rysuj(dostepne) {
      var tx = tlo.querySelector("textarea"), opis = tx ? tx.value : "";
      tlo.innerHTML = '<div class="ok" role="dialog" aria-modal="true" aria-labelledby="pp-zgl-t">' +
        '<h2 id="pp-zgl-t">Zgłoś błąd albo uwagę<button type="button" class="b x" data-x title="Zamknij">✕</button></h2>' +
        '<p class="op">Trafi do administratora. Opisz, co nie działa – im dokładniej, tym szybciej to poprawimy.</p>' +
        '<div class="et">Czego dotyczy (możesz zaznaczyć kilka)</div><div class="cz">' +
        dostepne.map(function (o) { return '<button type="button" data-o="' + o.id + '" aria-pressed="' + (stan.obszary.indexOf(o.id) >= 0) + '"' + (o.opis ? ' title="' + o.opis + '"' : "") + ">" + o.nazwa + "</button>"; }).join("") +
        '</div><div class="et">Rodzaj</div><div class="sg">' +
        RODZAJE_ZGL.map(function (r) { return '<button type="button" data-r="' + r[0] + '" aria-pressed="' + (stan.rodzaj === r[0]) + '">' + r[1] + "</button>"; }).join("") +
        '</div><div class="et">Opis</div><textarea placeholder="Krok po kroku: co zostało zrobione, co się stało i co powinno się stać.">' + esc(opis) + "</textarea>" +
        '<div class="et">Zrzut ekranu (opcjonalnie – możesz też wkleić Ctrl+V)</div><div class="zr">' +
        (stan.zrzut ? '<img alt="zrzut ekranu" src="' + stan.zrzut + '"><button type="button" class="b" data-bez>Usuń zrzut</button>'
          : '<label class="b">Dodaj obraz<input type="file" accept="image/png,image/jpeg,image/webp" hidden></label>') +
        '</div><div class="bl" hidden></div>' +
        '<div class="st"><span class="in">Dołączymy adres tej strony i rodzaj przeglądarki.</span><button type="button" class="b" data-x>Anuluj</button>' +
        '<button type="button" class="b p" data-wyslij>Wyślij zgłoszenie</button></div>' +
        '<details><summary>Twoje zgłoszenia</summary><div class="mzl">Wczytywanie…</div></details></div>';
      var t2 = tlo.querySelector("textarea"); t2.focus(); t2.setSelectionRange(t2.value.length, t2.value.length);
      var plik = tlo.querySelector("input[type=file]");
      if (plik) plik.addEventListener("change", function () { if (plik.files[0]) obraz(plik.files[0]); });
      tlo.querySelector("details").addEventListener("toggle", moje, { once: true });
    }
    function obraz(f) {                // zmniejszenie do 1920 px (JPEG) – zrzuty z dużych ekranów są ciężkie
      var r = new FileReader();
      r.onload = function () {
        var im = new Image();
        im.onload = function () {
          var sk = Math.min(1, 1920 / im.width), c = document.createElement("canvas");
          c.width = Math.round(im.width * sk); c.height = Math.round(im.height * sk);
          c.getContext("2d").drawImage(im, 0, 0, c.width, c.height);
          stan.zrzut = c.toDataURL("image/jpeg", 0.85); rysuj(dostepneObszary);
        };
        im.src = r.result;
      };
      r.readAsDataURL(f);
    }
    function wklej(e) { var it = [].slice.call((e.clipboardData || {}).items || []).filter(function (i) { return i.type.indexOf("image/") === 0; })[0]; if (it) { e.preventDefault(); obraz(it.getAsFile()); } }
    function moje() {
      fetch("/administracja/api/zgloszenia/moje", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : []; }).then(function (l) {
        var el = tlo.querySelector(".mzl"); if (!el) return;
        el.innerHTML = l.length ? l.map(function (z) {
          return '<div class="mz">' + esc(z.opis.slice(0, 120)) + '<span class="sz">' + (STANY_ZGL[z.stan] || z.stan) + "</span><small>" +
            new Date(z.czas).toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" }) + (z.komentarz ? " · odpowiedź: " + esc(z.komentarz) : "") + "</small></div>";
        }).join("") : '<div class="mz"><small>Jeszcze nic nie zgłaszano z tego konta.</small></div>';
      });
    }
    // 25.10 (decyzja użytkownika): w zgłoszeniu tylko to, co osoba widzi w pasku – „Ogólne”, jej zakładki i Kartoteka
    // (otwierana z Generatora i Zarządzania); bez potwierdzonego konta – tylko zakładki niezastrzeżone
    function obszaryDla(k) {
      var widac = APPS.filter(function (a) { return k ? widoczny(a, k) : !a.zastrzezony; }).map(function (a) { return a.obszar; });
      if (widac.indexOf("umowy") >= 0 || widac.indexOf("protokoly") >= 0) widac.push("kartoteka");
      if (k && (k.obszary || {}).kartoteka === "brak") widac = widac.filter(function (o) { return o !== "kartoteka"; });
      return OBSZARY_ZGL.filter(function (o) { return o.id === "ogolne" || widac.indexOf(o.id) >= 0; });
    }
    var dostepneObszary = obszaryDla(kontoZapamietane());
    tlo.addEventListener("click", function (e) {
      if (e.target === tlo || e.target.closest("[data-x]")) return zamknij();
      var o = e.target.closest("[data-o]"), r = e.target.closest("[data-r]");
      if (o) { var i = stan.obszary.indexOf(o.dataset.o); if (i >= 0) stan.obszary.splice(i, 1); else stan.obszary.push(o.dataset.o); o.setAttribute("aria-pressed", String(i < 0)); return; }
      if (r) { stan.rodzaj = r.dataset.r; tlo.querySelectorAll("[data-r]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === r)); }); return; }
      if (e.target.closest("[data-bez]")) { stan.zrzut = null; rysuj(dostepneObszary); return; }
      var w = e.target.closest("[data-wyslij]");
      if (!w) return;
      var bl = tlo.querySelector(".bl"), opis = tlo.querySelector("textarea").value.trim();
      function blad(t) { bl.textContent = t; bl.hidden = false; }
      if (!stan.obszary.length) return blad("Zaznacz, czego dotyczy zgłoszenie.");
      if (opis.length < 3) return blad("Opisz, co nie działa.");
      w.disabled = true; w.textContent = "Wysyłanie…";
      fetch("/administracja/api/zgloszenia", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ obszary: stan.obszary, rodzaj: stan.rodzaj, opis: opis, zrzut: stan.zrzut, adres: location.href,
          strona: document.title, przegladarka: navigator.userAgent, ekran: innerWidth + "×" + innerHeight }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Błąd " + r.status); return j; }); })
        .then(function () {
          tlo.querySelector(".ok").innerHTML = '<h2>Dziękujemy!<button type="button" class="b x" data-x>✕</button></h2>' +
            '<p class="op" style="margin:8px 0 0">Zgłoszenie trafiło do administratora. Jego stan zobaczysz w tym oknie, w „Twoich zgłoszeniach”.</p>' +
            '<div class="st"><button type="button" class="b p" data-x>Zamknij</button></div>';
        })
        .catch(function (err) { w.disabled = false; w.textContent = "Wyślij zgłoszenie"; blad(err.message || "Nie udało się wysłać – spróbuj ponownie."); });
    });
    document.addEventListener("keydown", klaw); document.addEventListener("paste", wklej);
    document.body.appendChild(tlo);
    rysuj(dostepneObszary);
    konto().then(function (k) {      // tylko obszary, do których konto ma dostęp
      if (!k || !document.body.contains(tlo)) return;
      dostepneObszary = obszaryDla(k);
      stan.obszary = stan.obszary.filter(function (id) { return dostepneObszary.some(function (o) { return o.id === id; }); });
      if (!stan.obszary.length) stan.obszary = ["ogolne"];
      rysuj(dostepneObszary);
    });
  }

  window.PracawrePasek = { uklad: uklad, ukladZapisz: ukladZapisz, ukladNr: function () { return UKLAD_NR; }, mozeUklad: mozeUklad,
    edytujMenu: function () { var el = document.getElementById("pracawre-pasek"); if (el) edytujMenu(el); }, liczby: liczby, widokAgenta: widokAgenta, ustawWidokAgenta: ustawWidokAgenta, wypelnij: wypelnij, ustaw: ustaw, wybor: wybor, ciemny: ciemny, kartoteka: kartoteka, konto: konto, zglos: zglos, aplikacje: aplikacje, grupy: GRUPY };
  if (mq && mq.addEventListener) mq.addEventListener("change", zastosuj);
  window.addEventListener("storage", function (e) { if (e.key === KLUCZ) zastosuj(); if (e.key === KLUCZ_AGENT) zmianaWidoku(); });
  html.classList.toggle("pw-agent", widokAgenta());
  styl();
  zastosuj();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sam); else sam();
})();
