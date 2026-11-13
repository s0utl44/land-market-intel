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
    { href: "/leady/", obszar: "leady", grupa: "sprzedaz", opis: "Prywatne ogłoszenia mieszkań, domów i gruntów", nazwa: "Zimne telefony", zastrzezony: true, ikona: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>' },
    { href: "/transakcje/", obszar: "transakcje", grupa: "sprzedaz", opis: "Lejek transakcji – Twoje sprawy, etapy i sumy", nazwa: "Transakcje", zastrzezony: true, ikona: '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="11" rx="1"/><rect x="17" y="4" width="4" height="7" rx="1"/>' },
    { href: "/odprawa/", obszar: "odprawa", grupa: "sprzedaz", opis: "Raporty – wyniki, podsumowania i dashboard", nazwa: "Raporty", zastrzezony: true, ikona: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>' },
    // 11.11 (decyzja użytkownika): podręcznik agenta – w grupie Biuro (nad Administracją), domyślnie nikt; dostęp nadaje administrator
    { href: "/wdrozenie/", obszar: "wdrozenie", grupa: "biuro", opis: "Podręcznik agenta – telefon, pozysk, rozwój", nazwa: "Wdrożenie", zastrzezony: true, ikona: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 21V5M8 7h7M8 11h5"/>' }
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
    // 30.10 (zgłoszenie: „przewinę do połowy, widzę błąd i muszę wracać na górę po ☰ / Zgłoś”): pasek pływa – zawsze na górze
    "#pracawre-pasek{flex:none;position:sticky;top:0;z-index:60}" +
    "html:not(.pw-sciagi) [data-sciaga]{display:none!important}" +
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
    ".pw-app{position:sticky;top:42px;z-index:30;box-sizing:border-box;display:flex;align-items:center;gap:6px;height:56px;min-width:0;" +
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
    "@media (max-width:900px){.pw-app{overflow-x:auto}.pw-app-tytul{display:none}}" +
    // edycja tekstu w całej witrynie (1.11, decyzja użytkownika – wzór „Edit message”): ramka edycji .pw-ed z pigułkami
    // „✕ Anuluj” / „✓ Zapisz” (.pw-ed-p, data-pw-anuluj / data-pw-zapisz – Esc i Ctrl+Enter), dymek z tekstem .pw-dym
    // (.pw-dym-b treść, .pw-dym-a ikonki Kopiuj / Edytuj pod spodem po najechaniu). Kolory ze zmiennych aplikacji (z zapasem).
    ".pw-ed{box-sizing:border-box;border-radius:16px;background:var(--card2,#faf8f4);border:1px solid var(--line2,#ece8df);padding:12px 14px;" +
    "transform-origin:top right;animation:pwEdIn .2s cubic-bezier(.23,1,.32,1)}" +
    ".pw-ed textarea{field-sizing:content;resize:none}" +
    ".pw-ed textarea.pw-ed-tx{display:block;width:100%;box-sizing:border-box;min-height:72px;border:0;outline:0;background:transparent;font:inherit;" +
    "font-size:14.5px;line-height:1.5;color:var(--ink,#1f1d1a);padding:2px}" +
    ".pw-ed-t{width:100%;box-sizing:border-box;border:0;border-bottom:1px solid var(--line,#e2ddd2);background:transparent;font:inherit;font-weight:800;" +
    "color:var(--ink,#1f1d1a);padding:4px 2px;margin-bottom:6px;outline:0}" +
    ".pw-ed-p{display:flex;align-items:center;justify-content:flex-end;gap:6px;margin-top:10px;flex-wrap:wrap}" +
    ".pw-ed-p .pw-ed-skr{margin-right:auto;color:var(--faint,#9a958b);font-size:11.5px}" +
    ".pw-ed-anul,.pw-ed-zap,.pw-ed-usun{all:unset;box-sizing:border-box;cursor:pointer;height:30px;padding:0 14px;border-radius:999px;font-weight:700;font-size:13px;" +
    "display:inline-flex;align-items:center;gap:5px;white-space:nowrap}" +
    ".pw-ed-anul,.pw-ed-usun{color:var(--muted,#6b665d)}.pw-ed-anul:hover,.pw-ed-usun:hover{background:var(--hover,#f7f3e8)}.pw-ed-usun:hover{color:#c62828}" +
    ".pw-ed-zap{color:#1a1a1a;background:linear-gradient(to bottom,color-mix(in srgb,var(--gold,#c9a03c) 70%,#fff),var(--gold,#c9a03c));" +
    "box-shadow:inset 0 1px 0 rgba(255,255,255,.2),0 1px 2px rgba(0,0,0,.18)}.pw-ed-zap:hover{filter:brightness(1.08)}" +
    ".pw-ed-zap[disabled],.pw-ed-zap:disabled{opacity:.5;pointer-events:none}" +
    ".pw-ed-anul:focus-visible,.pw-ed-zap:focus-visible,.pw-ed-usun:focus-visible{outline:2px solid var(--gold,#c9a03c);outline-offset:2px}" +
    ".pw-dym{display:flex;flex-direction:column;align-items:flex-start;gap:2px}" +
    ".pw-dym-b{max-width:100%;box-sizing:border-box;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:16px;padding:9px 13px;font-size:14.5px;line-height:1.5;" +
    "background:linear-gradient(to bottom,color-mix(in srgb,var(--gold-bg,rgba(201,160,60,.13)) 70%,var(--card,#fff)),var(--gold-bg,rgba(201,160,60,.13)));" +
    "color:var(--ink,#1f1d1a);animation:pwEdIn .2s cubic-bezier(.23,1,.32,1)}" +
    ".pw-dym-b.pusty{background:none;padding:2px 0;color:var(--faint,#9a958b);font-style:italic;cursor:pointer}" +
    ".pw-dym-a{display:flex;gap:2px;opacity:0;transition:opacity .15s}.pw-dym:hover .pw-dym-a,.pw-dym:focus-within .pw-dym-a{opacity:1}" +
    "@media (hover:none){.pw-dym-a{opacity:1}}" +
    ".pw-dym-a button{all:unset;cursor:pointer;width:26px;height:26px;border-radius:8px;display:grid;place-items:center;color:var(--muted,#6b665d);font-size:13px}" +
    ".pw-dym-a button:hover{background:var(--hover,#f7f3e8);color:var(--ink,#1f1d1a)}.pw-dym-a button:focus-visible{outline:2px solid var(--gold,#c9a03c)}" +
    "@keyframes pwEdIn{from{opacity:0;transform:scale(.98) translateY(3px)}to{opacity:1;transform:none}}" +
    "@media (prefers-reduced-motion:reduce){.pw-ed,.pw-dym-b{animation:none}}";

  // grupy zakładek – te same na pulpicie (strona główna) i w pasku (decyzja użytkownika 25.10)
  var GRUPY = [{ id: "dokumenty", nazwa: "Dokumenty" }, { id: "sprzedaz", nazwa: "Sprzedaż" }, { id: "rynek", nazwa: "Rynek" }];

  function styl() {
    if (document.getElementById("pracawre-pasek-styl")) return;
    var s = document.createElement("style");
    s.id = "pracawre-pasek-styl";
    s.textContent = CSS;
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
      svg(a.ikona) + "<span><b>" + a.nazwa + "</b><small>" + a.opis + '</small><span class="pp-l" data-l="' + a.obszar + '"></span></span></a>';
  }
  function zakladki(znane) {
    return GRUPY.map(function (g) {
      var w = APPS.filter(function (a) { return a.grupa === g.id; });
      return '<div class="pp-grp" data-grupa="' + g.id + '"><div class="pp-gt">' + g.nazwa + "</div>" +
        w.map(function (a) { return link(a, znane); }).join("") + "</div>";
    }).join("");
  }

  function wypelnij(el) {
    if (!el) return;
    styl();
    var znane = kontoZapamietane();
    var tu = APPS.filter(naStronie)[0] || (location.pathname.indexOf("/administracja") === 0 ? { nazwa: "Administracja" } : null);
    el.innerHTML =
      '<nav class="pp" aria-label="pracawre.com">' +
      '<button type="button" class="pp-otw" data-sz title="Menu – narzędzia, konto, zgłoś błąd" aria-haspopup="dialog" aria-expanded="false">' +
      svg('<path d="M4 6h16M4 12h16M4 18h16"/>') + '<i class="pp-kropka" hidden></i></button>' +
      '<a class="pp-dom" href="/" title="Strona główna"><img src="/wspolne/logo-wre.png" alt="WRE Nieruchomości"></a>' +
      (tu ? '<span class="pp-sep" aria-hidden="true"></span><span class="pp-tu">' + tu.nazwa + "</span>" : "") +
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
      zakladki(znane) +
      '<div class="pp-grp pp-biuro" hidden><div class="pp-gt">Biuro</div>' +
      APPS.filter(function (a) { return a.grupa === "biuro"; }).map(function (a) { return link(a, znane); }).join("") +
      '<a class="pp-z pp-adm" hidden href="/administracja/"' +
      (location.pathname.indexOf("/administracja") === 0 ? ' aria-current="page"' : "") + ">" +
      svg('<path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>') +
      '<span><b>Administracja</b><small>Konta, uprawnienia, zgłoszenia błędów, stan systemu</small><span class="pp-l" data-l="administracja"></span></span></a></div>' +
      "</div>" +
      '<div class="pp-sz-d"><div class="pp-motywy" role="group" aria-label="Motyw">' +
      ["auto", "light", "dark"].map(function (m) { return '<button type="button" data-motyw="' + m + '" aria-pressed="false">' + svg(IKONY[m]) + NAZWY_MOTYWOW[m] + "</button>"; }).join("") +
      "</div>" +
      '<button type="button" data-profil>' + svg('<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>') + "<span>Mój profil</span></button>" +
      '<button type="button" data-zglos>' + svg('<path d="M8 2l1.9 1.9M16 2l-1.9 1.9M9 7.1V6a3 3 0 1 1 6 0v1.1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6zM12 20v-9M6.5 13H3M21 13h-3.5M6 9.4 3.5 7.5M18 9.4l2.5-1.9M6 17.6 3.5 19.5M18 17.6l2.5 1.9"/>') +
      "<span>Zgłoś błąd albo uwagę</span></button>" +
      '<button type="button" class="pp-agent" data-agent hidden aria-pressed="false">' + svg('<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>') +
      "<span>Widok agenta</span><b>wył.</b></button>" +
      '<a href="/oauth2/sign_out?rd=%2F">' + svg('<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4"/>') + "<span>Wyloguj</span></a>" +
      "</div></aside>";
    var sz = el.querySelector(".pp-sz"), tlo = el.querySelector(".pp-sz-tlo");
    el.querySelectorAll("[data-sz]").forEach(function (b) { b.addEventListener("click", function () { otworz(el); }); });
    el.querySelector("[data-zamknij]").addEventListener("click", function () { zamknij(); });
    tlo.addEventListener("click", function () { zamknij(); });
    sz.addEventListener("click", function (e) { if (e.target.closest("a")) zamknij(true); });
    el.querySelectorAll("[data-motyw]").forEach(function (b) { b.addEventListener("click", function () { ustaw(b.dataset.motyw); }); });
    el.querySelector("[data-zglos]").addEventListener("click", function () { zamknij(); zglos(); });
    el.querySelector("[data-profil]").addEventListener("click", function () { zamknij(); profil(); });
    el.querySelector("[data-agent]").addEventListener("click", function () { ustawWidokAgenta(!widokAgenta()); });
    el.querySelector("[data-agent-wyl]").addEventListener("click", function () { ustawWidokAgenta(false); });
    odswiezMotyw();
    if (znane) uprawnieniaWPasku(el, znane);
    konto().then(function (k) { uprawnieniaWPasku(el, k); oknoSpotkan(k); alarmAdmina(el, k); if (k) notatnik(k); });
    samouczek();
    if (wlaczone(znane, "notatnik")) notatnik(znane);
  }
  // 12.11 (decyzja użytkownika: „jak się coś wykrzaczy, ma mnie informować i krzyczeć – nie zaglądam codziennie”): administrator na
  // KAŻDEJ stronie dostaje czerwony pasek pod paskiem witryny, gdy któraś aplikacja nie odpowiada albo pobieranie stoi. Sprawdzenie
  // najwyżej co 10 min (wynik w localStorage pracawre-alarm); „✕” chowa pasek, dopóki lista problemów się nie zmieni.
  var ALARM_CSS = ".pp-alarm{display:flex;align-items:center;gap:10px;padding:8px max(12px,env(safe-area-inset-right)) 8px 14px;background:#b3261e;color:#fff;" +
    "font:700 13.5px/1.35 Lato,'Segoe UI',system-ui,sans-serif}.pp-alarm a{color:#fff;text-decoration:underline;white-space:nowrap}.pp-alarm .t{flex:1;min-width:0}" +
    ".pp-alarm button{all:unset;cursor:pointer;width:26px;height:26px;border-radius:50%;display:grid;place-items:center}.pp-alarm button:hover{background:rgba(255,255,255,.18)}";
  function sprawdzAlarmy() {
    var j = function (u) { return fetch(u, { credentials: "same-origin", cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json().catch(function () { return {}; }); }); };
    var zdrowie = [["Generator umów", "/umowy/zdrowie"], ["Zarządzanie", "/protokoly/sb/zdrowie"], ["Kontakty", "/kartoteka/zdrowie"], ["Zimne", "/leady/zdrowie"],
      ["Raporty", "/odprawa/zdrowie"], ["Transakcje", "/transakcje/zdrowie"], ["Wdrożenie", "/wdrozenie/zdrowie"], ["Mój profil", "/profil/zdrowie"]];
    var h = function (t) { return Math.round((Date.now() - new Date(t)) / 36e5); };
    var spr = zdrowie.map(function (a) { return fetch(a[1], { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.ok ? null : a[0] + " nie odpowiada (" + r.status + ")"; }, function () { return a[0] + " nie odpowiada"; }); });
    spr.push(j("/leady/api/stan").then(function (d) {
      var out = [], ost = (d.przebiegi || [])[0];
      if (!d.trwa && (!ost || h(ost.koniec || ost.start) > 36)) out.push("Zimne – ogłoszenia nie pobierały się od " + (ost ? h(ost.koniec || ost.start) + " godz." : "dawna"));
      Object.keys((ost && ost.portale) || {}).forEach(function (k) {
        var w = ost.portale[k], st = [w.status].concat(Object.keys(w.rodzaje || {}).map(function (r) { return w.rodzaje[r].status; })).filter(Boolean);
        if (st.some(function (x) { return x !== "ok" && x !== "czesciowo"; })) out.push("Zimne – portal " + ((d.nazwy_portali || {})[k] || k) + ": błąd pobierania");
      });
      if (d.hubspot === false) out.push("Zimne – HubSpot niepodłączony");
      return out;
    }, function () { return []; }));
    spr.push(j("/transakcje/api/stan").then(function (d) { return !d.hubspot ? ["Transakcje – brak połączenia z HubSpot"] : d.blad ? ["Transakcje – błąd pobierania z HubSpot"] : []; }, function () { return []; }));
    spr.push(j("/odprawa/api/status").then(function (d) { return !d.token || !d.mapa ? ["Raporty – brak połączenia z HubSpot"] : d.ostatni_blad ? ["Raporty – ostatnie pobieranie z błędem"] : []; }, function () { return []; }));
    return Promise.all(spr).then(function (w) { return [].concat.apply([], w).filter(Boolean); });
  }
  function alarmAdmina(el, k) {
    if (!k || !k.admin || widokAgenta() || window.top !== window) return;
    var zap = null;
    try { zap = JSON.parse(localStorage.getItem("pracawre-alarm") || "null"); } catch (e) {}
    var pokaz = function (lista) {
      var stary = el.querySelector(".pp-alarm"); if (stary) stary.remove();
      var klucz = lista.join("|"), zamk = "";
      try { zamk = localStorage.getItem("pracawre-alarm-zamkniety") || ""; } catch (e) {}
      el.querySelector(".pp-kropka").hidden = !(lista.length || (k.zgloszeniaNowe && !widokAgenta()));
      if (!lista.length || zamk === klucz) return;
      if (!document.getElementById("pp-alarm-styl")) { var st = document.createElement("style"); st.id = "pp-alarm-styl"; st.textContent = ALARM_CSS; document.head.appendChild(st); }
      var a = document.createElement("div"); a.className = "pp-alarm"; a.setAttribute("role", "alert");
      a.innerHTML = '<span>⚠</span><span class="t">' + esc(lista.slice(0, 3).join(" · ")) + (lista.length > 3 ? " · i " + (lista.length - 3) + " więcej" : "") +
        '</span><a href="/administracja/#stan">Stan systemu →</a><button type="button" title="Schowaj, dopóki nie pojawi się nowy problem" aria-label="Schowaj">✕</button>';
      a.querySelector("button").addEventListener("click", function () { try { localStorage.setItem("pracawre-alarm-zamkniety", klucz); } catch (e) {} a.remove(); });
      el.querySelector(".pp").insertAdjacentElement("afterend", a);
    };
    if (zap && Date.now() - zap.czas < 600000) return pokaz(zap.lista || []);
    sprawdzAlarmy().then(function (lista) {
      try { localStorage.setItem("pracawre-alarm", JSON.stringify({ czas: Date.now(), lista: lista })); } catch (e) {}
      pokaz(lista);
    });
  }

  // 11.11 (decyzja użytkownika): samouczek – przycisk 🎓 obok konta, oprowadzanie i „Co nowego” (/wspolne/samouczek.js)
  function samouczek() {
    if (window.PracawreSamouczek) { window.PracawreSamouczek.przycisk(); return; }
    if (document.getElementById("pp-samouczek-js") || window.top !== window) return;
    var s = document.createElement("script"); s.id = "pp-samouczek-js"; s.src = "/wspolne/samouczek.js"; s.defer = true;
    (document.head || html).appendChild(s);
  }

  // 12.11 (decyzja użytkownika): Notatnik i Samouczek – każdy włącza / wyłącza sam w „Mój profil” (profil.ustawienia; domyślnie włączone)
  function wlaczone(k, co) { var u = k && k.profil && k.profil.ustawienia; return !(u && u[co] === false); }
  // 12.11 (decyzja użytkownika): notatnik – przycisk 📝 w pasku, pływające okno, karteczki na stronie głównej (/wspolne/notatnik.js)
  function notatnik(k) {
    if (window.top !== window) return;
    if (!wlaczone(k, "notatnik")) { if (window.PracawreNotatnik) window.PracawreNotatnik.wylacz(); return; }
    if (window.PracawreNotatnik) { window.PracawreNotatnik.wlacz(); return; }
    if (document.getElementById("pp-notatnik-js")) return;
    var s = document.createElement("script"); s.id = "pp-notatnik-js"; s.src = "/wspolne/notatnik.js"; s.defer = true;
    (document.head || html).appendChild(s);
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
    var sz = el.querySelector(".pp-sz"), tlo = el.querySelector(".pp-sz-tlo");
    sz.classList.remove("otw"); tlo.classList.remove("otw");
    el.querySelectorAll("[data-sz]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
    setTimeout(function () { if (otwarta !== el) { sz.hidden = true; tlo.hidden = true; } }, odRazu ? 0 : 230);
    if (!odRazu && przedKarta && przedKarta.focus) przedKarta.focus({ preventScroll: true });
  }
  // 8.11 (decyzja użytkownika: Escape zamyka TYLKO to, co jest na wierzchu): okienka paska łapią Escape pierwsze (faza przechwytywania
  // na window) i zatrzymują go – karta transakcji / leada pod spodem zostaje. Aplikacje sprawdzają e.defaultPrevented.
  function tylkoTo(e, fn) { if (e.key !== "Escape" || e.defaultPrevented) return false; e.preventDefault(); e.stopPropagation(); fn(); return true; }
  window.addEventListener("keydown", function (e) { if (otwarta) tylkoTo(e, zamknij); }, true);

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
    // 10.11 (decyzja użytkownika): przy „Zimnych telefonach” w menu BEZ liczb (ogłoszenia do wzięcia, do zadzwonienia, ponowne) – sama nazwa
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
    if (a.obszar === "leady" && k.zimne && !k.zimne.length && !k.admin) return false;   // 7.11: dyrektor – dane tak, zimne nie
    return a.zastrzezony ? p === "dostep" || p === "admin" : p !== "brak";
  }
  function naStronie(a) { return location.pathname.indexOf(a.href) === 0 || location.pathname + "/" === a.href; }
  // aplikacje, do których konto ma dostęp (kafelki strony głównej); k = null – tylko te bez zastrzeżeń
  function aplikacje(k) {
    return APPS.filter(function (a) { return k ? widoczny(a, k) : !a.zastrzezony; });
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
    // 11.11 (decyzja użytkownika): ściągi (📋 Skrypt i obiekcje, 📋 Lista przed spotkaniem) – tylko z dostępem „Ściągi” (rola Młody agent)
    var sc = (k.obszary || {}).sciagi;
    html.classList.toggle("pw-sciagi", sc === "dostep" || sc === "admin");
    APPS.forEach(function (a) {
      el.querySelectorAll('[data-obszar="' + a.obszar + '"]').forEach(function (link) { link.hidden = !widoczny(a, k); });
    });
    el.querySelectorAll(".pp-grp[data-grupa]").forEach(function (g) { g.hidden = !g.querySelector("a:not([hidden])"); });
    var nazwa = k.nazwa || (k.email || "").split("@")[0], ag = widokAgenta() && k.admin;
    el.querySelectorAll(".pp-av").forEach(function (a) { a.textContent = inicjaly(nazwa); });
    el.querySelector(".pp-konto").title = nazwa;
    el.querySelector(".pp-kto-t").innerHTML = "<b>" + esc(nazwa) + "</b><small>" + esc(k.email || "") + "</small>";
    el.querySelector(".pp-adm").hidden = !k.admin || ag;
    el.querySelector(".pp-biuro").hidden = !el.querySelector(".pp-biuro a:not([hidden])");
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

  // --- „Czy spotkania się odbyły?” (31.10, decyzja użytkownika – rozmowa z Dawidem): po wejściu na dowolną stronę lista
  // MOICH spotkań, których termin minął, bez oznaczonego wyniku (od chwili wdrożenia – nie wstecz). Przy każdym Tak / Nie;
  // bez oznaczenia wszystkich nie da się przejść dalej („Zapisz i przejdź do swoich spraw”). Dotyczy agentów zimnych telefonów
  // (dostęp do Zimnych i Transakcji). Dane: /transakcje/api/spotkania/… (Tak → odbyte, Nie → odwołane; zapis w HubSpot).
  var CSS_SP =
    "#pp-sp{position:fixed;inset:0;z-index:2147483002;background:rgba(15,14,12,.6);display:grid;place-items:center;padding:16px;" +
    "font:15px/1.45 Lato,'Segoe UI',system-ui,sans-serif;--k:#fff;--t:#1f1d1a;--m:#6b665d;--l:#e2ddd2;--p:#faf8f4;--z:#c9a03c;--zd:#9b7a26}" +
    "html[data-theme=dark] #pp-sp{--k:#212326;--t:#e8e5de;--m:#a39e94;--l:#33363a;--p:#1c1e21;--zd:#d9b55a}" +
    "#pp-sp *{box-sizing:border-box}" +
    "#pp-sp .spO{background:var(--k);color:var(--t);width:min(620px,100%);max-height:calc(100vh - 32px);overflow:auto;border-radius:18px;box-shadow:0 24px 70px rgba(0,0,0,.35);padding:22px 24px}" +
    "#pp-sp h2{margin:0 0 4px;font-size:20px;font-weight:900}#pp-sp .op{color:var(--m);font-size:13.5px;margin:0 0 14px}" +
    "#pp-sp .w{display:flex;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--l)}" +
    "#pp-sp .w .tx{flex:1;min-width:0}#pp-sp .w b{display:block;font-size:14.5px}#pp-sp .w small{color:var(--m);font-size:12.5px}" +
    "#pp-sp .sg{display:inline-flex;background:var(--p);border:1px solid var(--l);border-radius:999px;padding:3px;gap:2px;flex:none}" +
    "#pp-sp .sg button{all:unset;cursor:pointer;padding:6px 16px;border-radius:999px;font-weight:800;font-size:13.5px}" +
    "#pp-sp .sg button[data-v=tak][aria-pressed=true]{background:#2e7d32;color:#fff}#pp-sp .sg button[data-v=nie][aria-pressed=true]{background:#b3261e;color:#fff}" +
    "#pp-sp .st{display:flex;align-items:center;gap:10px;margin-top:16px}#pp-sp .st .in{margin-right:auto;font-size:12.5px;color:var(--m)}" +
    "#pp-sp .b{all:unset;cursor:pointer;display:inline-flex;align-items:center;height:40px;padding:0 18px;border-radius:999px;font-weight:800;background:var(--t);color:var(--k);white-space:nowrap;flex:none}" +
    "#pp-sp .b[disabled]{opacity:.35;pointer-events:none}#pp-sp .bl{color:#b3261e;font-size:13px;margin-top:8px}" +
    "@media (max-width:560px){#pp-sp .w{flex-wrap:wrap}}";
  var spotkaniaSpr = false;
  function oknoSpotkan(k) {
    if (spotkaniaSpr || !k || document.getElementById("pp-sp")) return;
    var o = k.obszary || {}, ma = function (x) { return o[x] === "dostep" || o[x] === "admin"; };
    if (!ma("leady") || !ma("transakcje")) return;
    try { if (Date.now() - Number(sessionStorage.getItem("pracawre-spotkania") || 0) < 180000) return; } catch (e) {}
    spotkaniaSpr = true;
    fetch("/transakcje/api/spotkania/do-oznaczenia", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { lista: [] }; })
      .then(function (d) {
        var lista = d.lista || [];
        if (!lista.length) { try { sessionStorage.setItem("pracawre-spotkania", String(Date.now())); } catch (e) {} return; }
        pokazSpotkania(lista);
      }).catch(function () {});
  }
  function pokazSpotkania(lista) {
    if (!document.getElementById("pp-sp-styl")) { var st = document.createElement("style"); st.id = "pp-sp-styl"; st.textContent = CSS_SP; document.head.appendChild(st); }
    var wyb = {};
    var t = document.createElement("div"); t.id = "pp-sp";
    // 8.11: okno „Czy spotkania się odbyły?” nie zamyka się Escape'em (najpierw odpowiedź), ale nie przepuszcza go do karty pod spodem
    window.addEventListener("keydown", function blokuj(e) {
      if (!document.body.contains(t)) return window.removeEventListener("keydown", blokuj, true);
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); }
    }, true);
    var kiedy = function (v) { var d = new Date(v); return isNaN(d) ? "" : d.toLocaleString("pl-PL", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); };
    t.innerHTML = '<div class="spO" role="dialog" aria-modal="true" aria-labelledby="pp-sp-t"><h2 id="pp-sp-t">Czy spotkania się odbyły?</h2>' +
      '<p class="op">Zaznacz przy każdym spotkaniu Tak albo Nie – to zajmie chwilę, a potem przejdziesz do swoich spraw.</p>' +
      lista.map(function (x) {
        return '<div class="w" data-id="' + esc(x.id) + '"><span class="tx"><b>' + esc(x.tytul || "Spotkanie") + "</b><small>" + esc(kiedy(x.start)) +
          (x.nazwa ? " · " + esc(x.nazwa) : "") + '</small></span><span class="sg" role="group" aria-label="Czy się odbyło">' +
          '<button type="button" data-v="tak" aria-pressed="false">Tak</button><button type="button" data-v="nie" aria-pressed="false">Nie</button></span></div>';
      }).join("") +
      '<div class="bl" hidden></div><div class="st"><span class="in">Tak = odbyło się · Nie = odwołane</span>' +
      '<button type="button" class="b" data-zapisz disabled>Zapisz i przejdź do swoich spraw</button></div></div>';
    document.body.appendChild(t);
    var zap = t.querySelector("[data-zapisz]"), bl = t.querySelector(".bl");
    t.addEventListener("click", function (e) {
      var b = e.target.closest("[data-v]");
      if (b) {
        var w = b.closest("[data-id]"); wyb[w.dataset.id] = b.dataset.v;
        w.querySelectorAll("[data-v]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        zap.disabled = lista.some(function (x) { return !wyb[x.id]; });
        return;
      }
      if (!e.target.closest("[data-zapisz]") || zap.disabled) return;
      zap.disabled = true; zap.textContent = "Zapisywanie…"; bl.hidden = true;
      fetch("/transakcje/api/spotkania/wyniki", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wyniki: lista.map(function (x) { return { id: x.id, odbylo: wyb[x.id] }; }) }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Błąd " + r.status); return j; }); })
        .then(function () {
          try { sessionStorage.setItem("pracawre-spotkania", String(Date.now())); } catch (er) {}
          t.remove();
          try { window.dispatchEvent(new CustomEvent("pracawre-spotkania")); } catch (er) {}
        })
        .catch(function (err) { bl.textContent = err.message || "Nie udało się zapisać – spróbuj jeszcze raz."; bl.hidden = false; zap.disabled = false; zap.textContent = "Zapisz i przejdź do swoich spraw"; });
    });
  }

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
    tlo.innerHTML = '<iframe title="Kontakty" src="/kartoteka/?' + q + '"></iframe>';
    var poprzedni = document.activeElement, przewijanie = document.documentElement.style.overflow;
    function zamknij() {
      tlo.remove(); window.removeEventListener("message", wiad); window.removeEventListener("keydown", klaw, true);
      document.documentElement.style.overflow = przewijanie;
      if (poprzedni && poprzedni.focus) poprzedni.focus();
      if (poZamknieciu) poZamknieciu();
    }
    function wiad(e) {
      if (e.origin !== location.origin || !e.data) return;
      if (e.data.typ === "kartoteka-zamknij") zamknij();
      if (e.data.typ === "kartoteka-wybor" && poWyborze) { zamknij(); poWyborze({ tabela: e.data.tabela, id: e.data.id }); }
    }
    function klaw(e) { tylkoTo(e, zamknij); }
    tlo.addEventListener("click", function (e) { if (e.target === tlo) zamknij(); });
    window.addEventListener("message", wiad); window.addEventListener("keydown", klaw, true);
    document.documentElement.style.overflow = "hidden";
    document.body.appendChild(tlo);
    tlo.querySelector("iframe").focus();
  }

  // --- Zgłoś błąd: jeden formularz dla całej witryny (obszary, rodzaj, opis, zrzut ekranu) → panel Administracja ---------
  var OBSZARY_ZGL = [
    { id: "ogolne", nazwa: "Ogólne", opis: "strona główna, logowanie, pasek" },
    { id: "umowy", nazwa: "Generator umów", sciezka: "/umowy" },
    { id: "protokoly", nazwa: "Zarządzanie", sciezka: "/protokoly" },
    { id: "kartoteka", nazwa: "Kontakty", sciezka: "/kartoteka" },
    { id: "radar", nazwa: "Radar działek", sciezka: "/radar" },
    { id: "leady", nazwa: "Zimne telefony", sciezka: "/leady" },
    { id: "transakcje", nazwa: "Transakcje", sciezka: "/transakcje" },
    { id: "odprawa", nazwa: "Raporty", sciezka: "/odprawa" },
    { id: "wdrozenie", nazwa: "Wdrożenie", sciezka: "/wdrozenie" }
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
    "#pp-zgl .pw-ed{background:var(--k);border-color:var(--l)}#pp-zgl .pw-ed:focus-within{border-color:var(--z);box-shadow:0 0 0 4px rgba(201,160,60,.15)}" +
    "#pp-zgl textarea.pw-ed-tx{min-height:110px;color:var(--t)}" +
    "#pp-zgl .zr{display:flex;align-items:center;gap:10px;flex-wrap:wrap}" +
    "#pp-zgl .zr img{display:block;max-height:70px;max-width:140px;border-radius:8px;border:1px solid var(--l)}" +
    "#pp-zgl .zj{position:relative;display:inline-block}#pp-zgl .zx{all:unset;cursor:pointer;position:absolute;top:-7px;right:-7px;width:22px;height:22px;border-radius:50%;" +
    "background:var(--t);color:var(--k);font-size:11px;font-weight:900;display:grid;place-items:center}" +
    "#pp-zgl .zh{font-size:12px;color:var(--m);margin-top:6px}" +
    "#pp-zgl .sk{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:rgba(201,160,60,.16);color:var(--zd);border-radius:12px;padding:8px 12px;font-weight:700;font-size:13.5px;margin:-6px 0 6px}" +
    "#pp-zgl .sk .b{height:30px;padding:0 12px;font-size:12.5px;margin-left:auto}" +
    "#pp-zgl .b{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:7px;height:38px;padding:0 16px;white-space:nowrap;border-radius:999px;border:1px solid var(--l);font-weight:700;font-size:14px}" +
    "#pp-zgl .b.p{background:var(--t);color:var(--k);border-color:var(--t)}#pp-zgl .b[disabled]{opacity:.5;pointer-events:none}" +
    "#pp-zgl .b.x{width:38px;padding:0;justify-content:center}" +
    "#pp-zgl .st{display:flex;gap:8px;justify-content:flex-end;align-items:center;margin-top:18px}#pp-zgl .st .in{margin-right:auto;font-size:12.5px;color:var(--m)}" +
    "#pp-zgl .bl{color:#b3261e;font-size:13px;margin-top:8px}" +
    "#pp-zgl details{margin-top:18px;border-top:1px solid var(--l);padding-top:12px}#pp-zgl summary{cursor:pointer;font-weight:700;font-size:14px}" +
    "#pp-zgl .mz{padding:9px 0;border-bottom:1px solid var(--l);font-size:13.5px}#pp-zgl .mz:last-child{border:0}" +
    "#pp-zgl .mz small{display:block;color:var(--m)}#pp-zgl .sz{font-size:11px;font-weight:900;padding:2px 8px;border-radius:999px;background:rgba(201,160,60,.16);color:var(--zd);margin-left:6px}";

  // --- Mój profil (1.11, decyzja użytkownika): każdy wpisuje link do SWOJEGO profilu agenta na Otodomie – Transakcje pokazują
  // z niego ogłoszenia do podpięcia przy transakcji („Nasze ogłoszenia”). Zapis: Kartoteka PUT /administracja/api/ja/profil.
  var PROF_CSS = "#pp-prof{position:fixed;inset:0;z-index:2147483001;background:rgba(15,14,12,.55);display:grid;place-items:center;padding:16px;" +
    "--k:#fff;--t:#1f1d1a;--m:#6b665d;--l:#e2ddd2;--z:#c9a03c;font:15px/1.45 Lato,system-ui,sans-serif}" +
    "html[data-theme=dark] #pp-prof{--k:#212326;--t:#e8e5de;--m:#a39e94;--l:#33363a}" +
    "#pp-prof *{box-sizing:border-box}#pp-prof .pk{background:var(--k);color:var(--t);width:min(620px,100%);max-height:calc(100vh - 32px);overflow:auto;border-radius:18px;padding:22px 22px 18px;box-shadow:0 20px 60px rgba(0,0,0,.35)}" +
    "#pp-prof .ph{margin-top:18px;border-top:1px solid var(--l);padding-top:14px}#pp-prof .ph h3{margin:0 0 8px;font-size:15px;font-weight:900}" +
    "#pp-prof details{border:1px solid var(--l);border-radius:12px;padding:8px 12px;margin-bottom:8px}#pp-prof summary{cursor:pointer;font-weight:700}" +
    "#pp-prof summary small{color:var(--m);font-weight:400}#pp-prof .pt h4{margin:10px 0 4px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--z)}" +
    "#pp-prof .pt ul{margin:0;padding-left:18px;font-size:13.5px}#pp-prof .pt li{margin:2px 0}#pp-prof .pt p{margin:0;color:var(--t);white-space:pre-wrap}" +
    "#pp-prof h2{margin:0 0 4px;font-size:20px;font-weight:900}#pp-prof p{color:var(--m);font-size:13.5px;margin:0 0 14px}" +
    "#pp-prof label{display:block;font-size:12.5px;font-weight:700;color:var(--m)}" +
    "#pp-prof input{display:block;width:100%;margin-top:6px;height:40px;border-radius:12px;border:1px solid var(--l);background:var(--k);color:var(--t);padding:0 12px;font:inherit;outline:none}" +
    "#pp-prof .pf{margin:-6px 0 12px}#pp-prof .pf a{font-weight:800;color:var(--z)}" +
    "#pp-prof .pu{margin-top:18px;border-top:1px solid var(--l);padding-top:14px}#pp-prof .pu h3{margin:0 0 2px;font-size:15px;font-weight:900}#pp-prof .pu p{margin:0 0 8px}" +
    "#pp-prof .pu label{display:flex;gap:12px;align-items:flex-start;padding:8px 0;cursor:pointer;color:var(--t);font-size:14px;font-weight:400}" +
    "#pp-prof .pu input{display:inline-block;width:18px;height:18px;margin:2px 0 0;flex:none;accent-color:#bd9302}#pp-prof .pu b{display:block}#pp-prof .pu small{color:var(--m);font-size:12.5px}" +
    "#pp-prof input:focus{border-color:var(--z);box-shadow:0 0 0 4px rgba(201,160,60,.15)}" +
    "#pp-prof .b{all:unset;cursor:pointer;display:inline-flex;align-items:center;height:38px;padding:0 16px;border-radius:999px;border:1px solid var(--l);font-weight:700;font-size:14px}" +
    "#pp-prof .b.p{background:var(--t);color:var(--k);border-color:var(--t)}#pp-prof .st{display:flex;gap:8px;justify-content:flex-end;margin-top:18px}" +
    "#pp-prof .bl{color:#b3261e;font-size:13px;margin-top:8px}" +
    "#pp-prof .pg{margin-top:18px;border-top:1px solid var(--l);padding-top:14px}#pp-prof .pg h3{margin:0 0 4px;font-size:15px;font-weight:900}" +
    "#pp-prof .pg .w{display:flex;align-items:center;gap:10px;flex-wrap:wrap}#pp-prof .pg .s{flex:1;min-width:180px;font-size:13.5px}" +
    "#pp-prof .pg .s b{color:#2e7d32}html[data-theme=dark] #pp-prof .pg .s b{color:#7cc59a}";
  function escHtml(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  // podsumowanie odprawy (struktura z Odprawy) – pulpit i „Mój profil”
  function podsumowanieHtml(d) {
    if (!d.liczby) return "<p>" + escHtml(d.tekst || "") + "</p>";
    function blok(t, x) { return x ? "<h4>" + t + "</h4>" + x : ""; }
    function lista(a, f) { return a && a.length ? "<ul>" + a.map(f).join("") + "</ul>" : ""; }
    var para = function (p) { return "<li><b>" + escHtml(p[0]) + "</b> – " + escHtml(p[1]) + "</li>"; };
    return blok("Wyniki", lista(d.liczby, function (p) { return "<li>" + escHtml(p[0]) + ": <b>" + escHtml(p[1]) + "</b></li>"; })) +
      blok("Ustalenia", lista(d.ustalenia, para)) + blok("Zadania (są w HubSpot)", lista(d.zadania, para)) +
      blok("Stracone transakcje", lista(d.straty, para)) +
      blok("Cele" + (d.celeMies ? " – " + escHtml(d.celeMies) : ""), lista(d.cele, function (p) { return "<li>" + escHtml(p[0]) + ": <b>" + escHtml(p[1]) + "</b></li>"; })) +
      blok("Dodatkowo", d.dodatkowo ? "<p>" + escHtml(d.dodatkowo) + "</p>" : "");
  }

  // 8.11 (decyzja użytkownika: „datę ustawiać scrollem, żeby przyspieszyć”): w CAŁEJ witrynie kółko myszy nad polem daty / godziny
  // zmienia wartość – dzień ±1 (Shift ±7), godzina ±15 min albo krok pola (Shift ±1 godz.); kółko w górę = później. Wyłączenie: data-bez-kolka.
  var kolkoSuma = 0;
  function dwa(n) { return (n < 10 ? "0" : "") + n; }
  function dzienTxt(d) { return d.getFullYear() + "-" + dwa(d.getMonth() + 1) + "-" + dwa(d.getDate()); }
  document.addEventListener("wheel", function (e) {
    var el = e.target, t = el && el.tagName === "INPUT" ? el.type : "";
    if ((t !== "date" && t !== "time" && t !== "datetime-local") || el.disabled || el.readOnly || el.hasAttribute("data-bez-kolka")) return;
    e.preventDefault();
    kolkoSuma += e.deltaY;
    if (Math.abs(kolkoSuma) < 40) return;                      // gładzik: drobne ruchy sumujemy, mysz: jeden ząbek = jeden krok
    var kier = kolkoSuma < 0 ? 1 : -1; kolkoSuma = 0;
    var krokMin = Math.max(1, Math.round((+el.step || 900) / 60)), teraz = new Date();
    if (t === "date") {
      var p = (el.value || dzienTxt(teraz)).split("-"), d = new Date(+p[0], +p[1] - 1, +p[2]);
      d.setDate(d.getDate() + kier * (e.shiftKey ? 7 : 1)); el.value = dzienTxt(d);
    } else if (t === "time") {
      var g = (el.value || dwa(teraz.getHours()) + ":00").split(":"), m = +g[0] * 60 + +g[1], k = e.shiftKey ? 60 : krokMin;
      m = Math.min(24 * 60 - k, Math.max(0, Math.round(m / k) * k + kier * k)); el.value = dwa(Math.floor(m / 60)) + ":" + dwa(m % 60);
    } else {
      var v = el.value || dzienTxt(teraz) + "T" + dwa(teraz.getHours()) + ":00", dt = new Date(v.slice(0, 16));
      if (isNaN(dt)) return;
      dt.setMinutes(Math.round(dt.getMinutes() / 15) * 15 + kier * (e.shiftKey ? 24 * 60 : 15));
      el.value = dzienTxt(dt) + "T" + dwa(dt.getHours()) + ":" + dwa(dt.getMinutes());
    }
    el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
  }, { passive: false });
  document.addEventListener("mouseover", function (e) {             // podpowiedź przy pierwszym najechaniu
    var el = e.target, t = el && el.tagName === "INPUT" ? el.type : "";
    if ((t === "date" || t === "time" || t === "datetime-local") && !el.title && !el.hasAttribute("data-bez-kolka"))
      el.title = t === "date" ? "Kółko myszy: ±1 dzień (Shift: ±1 tydzień)" : "Kółko myszy: ±15 min (Shift: " + (t === "time" ? "±1 godz.)" : "±1 dzień)");
  });

  // 7.11: Google agenta – każda aplikacja woła przez pasek (zawsze konto zalogowanej osoby; Kontakty /administracja/api/google)
  var googleP = null;
  function jsonLubBlad(r) {
    return r.json().catch(function () { return {}; }).then(function (j) {
      if (!r.ok) { var e = new Error(j.detail || "Błąd połączenia z Google."); e.status = r.status; e.kod = j.detail; throw e; }
      return j;
    });
  }
  var google = {
    stan: function () {
      if (!googleP) googleP = fetch("/administracja/api/google", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : { dostepne: false }; })
        .catch(function () { return { dostepne: false }; });
      return googleP;
    },
    // {tytul, od: "RRRR-MM-DDTGG:MM", do, miejsce, opis, link} → {id, link}; gdy niepołączone – null (bez błędu)
    kalendarz: function (d) {
      return google.stan().then(function (g) {
        if (!g.dostepne || !g.polaczone || !g.kalendarz) return null;
        return fetch("/administracja/api/google/kalendarz", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(d) }).then(jsonLubBlad);
      });
    },
    // 8.11: poprawka / usunięcie wydarzenia dodanego z kluczem (np. „hs-spotkanie:<id>”); gdy niepołączone – null
    zmien: function (klucz, d) {
      return google.stan().then(function (g) {
        if (!g.dostepne || !g.polaczone || !g.kalendarz || !klucz) return null;
        return fetch("/administracja/api/google/kalendarz", { method: "PATCH", credentials: "same-origin", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.assign({ klucz: klucz }, d)) }).then(jsonLubBlad);
      });
    },
    usun: function (klucz) {
      return google.stan().then(function (g) {
        if (!g.dostepne || !g.polaczone || !g.kalendarz || !klucz) return null;
        return fetch("/administracja/api/google/kalendarz?klucz=" + encodeURIComponent(klucz), { method: "DELETE", credentials: "same-origin" }).then(jsonLubBlad);
      });
    },
    // 8.11: pełna wiadomość (nagłówki, html / tekst, załączniki) i adres pobrania załącznika
    wiadomosc: function (id) {
      return fetch("/administracja/api/google/poczta/" + encodeURIComponent(id), { credentials: "same-origin" }).then(jsonLubBlad);
    },
    zalacznik: function (mid, aid, nazwa) {
      return "/administracja/api/google/poczta/" + encodeURIComponent(mid) + "/zalacznik/" + encodeURIComponent(aid) + "?nazwa=" + encodeURIComponent(nazwa || "");
    },
    // adresy e-mail stron → {maile: [...]}; gdy niepołączone – null
    poczta: function (adresy) {
      return google.stan().then(function (g) {
        if (!g.dostepne || !g.polaczone || !g.poczta) return null;
        return fetch("/administracja/api/google/poczta?adresy=" + encodeURIComponent([].concat(adresy).join(",")), { credentials: "same-origin" }).then(jsonLubBlad);
      });
    }
  };
  // powrót z okienka Google: usuń ?google=polaczone z adresu i pokaż „Mój profil” z potwierdzeniem
  try {
    var pg = new URLSearchParams(location.search);
    if (pg.get("google") === "polaczone") {
      pg.delete("google");
      history.replaceState(null, "", location.pathname + (pg.toString() ? "?" + pg : "") + location.hash);
      setTimeout(function () { profil(); }, 300);
    }
  } catch (e) {}

  function profil() {
    if (document.getElementById("pp-prof")) return;
    if (!document.getElementById("pp-prof-styl")) {
      var st = document.createElement("style"); st.id = "pp-prof-styl"; st.textContent = PROF_CSS; document.head.appendChild(st);
    }
    var o = document.createElement("div"); o.id = "pp-prof";
    o.innerHTML = '<div class="pk" role="dialog" aria-modal="true" aria-labelledby="pp-prof-t"><h2 id="pp-prof-t">Mój profil</h2>' +
      '<p class="pf" hidden><a href="/profil/">Faktury i przychody →</a></p>' +
      "<p>Link do Twojego profilu agenta na Otodomie – Twoje ogłoszenia pokażą się przy transakcjach do podpięcia jednym kliknięciem.</p>" +
      '<label>Profil na Otodomie<input id="pp-prof-o" inputmode="url" placeholder="https://www.otodom.pl/pl/profil/agenci-nieruchomosci/…"></label>' +
      '<div class="bl" hidden></div><div class="st"><button type="button" class="b" data-x>Anuluj</button><button type="button" class="b p" data-z>Zapisz</button></div>' +
      '<div class="pg" hidden><h3>Google – kalendarz i poczta</h3><p>Połącz swoje firmowe konto Google: umówione spotkania same trafią do Twojego ' +
      'kalendarza, a w karcie transakcji zobaczysz maile z klientami (tylko odczyt, nic nie zapisujemy). Możesz odłączyć w każdej chwili.</p>' +
      '<div class="w"><span class="s"></span><button type="button" class="b" data-gp></button></div></div>' +
      '<div class="pu"><h3>Narzędzia w pasku</h3><p>Włącz albo wyłącz – tylko u siebie, zmiana od razu.</p>' +
      '<label><input type="checkbox" data-ust="notatnik"><span><b>📝 Notatnik</b><small>Prywatne notatki z paska (Alt+N) i karteczki na stronie głównej</small></span></label>' +
      '<label><input type="checkbox" data-ust="samouczek"><span><b>🎓 Samouczek</b><small>Oprowadzanie i ćwiczenia (przycisk w pasku)</small></span></label></div>' +
      '<div class="ph" hidden><h3>Podsumowania od dyrektora</h3><div class="pl"></div></div></div>';
    document.body.appendChild(o);
    // 7.11 (decyzja użytkownika): Google (kalendarz i poczta) łączy każdy sam – tylko gdy serwer ma włączone połączenie
    function rysujGoogle(g) {
      var sek = o.querySelector(".pg"); if (!g || !g.dostepne) { sek.hidden = true; return; }
      sek.hidden = false;
      var b = sek.querySelector("[data-gp]");
      sek.querySelector(".s").innerHTML = g.polaczone ? "<b>✓ Połączone</b>" + (g.polaczono ? " od " + escHtml(new Date(g.polaczono).toLocaleDateString("pl-PL")) : "") +
        (g.kalendarz ? "" : " – bez kalendarza") + (g.poczta ? "" : " – bez poczty") : "Nie połączone";
      b.textContent = g.polaczone ? "Odłącz" : "Połącz z Google";
      b.className = "b" + (g.polaczone ? "" : " p");
      b.onclick = function () {
        if (!g.polaczone) { location.href = "/administracja/api/google/polacz?wroc=" + encodeURIComponent(location.pathname + location.search + location.hash); return; }
        b.disabled = true;
        fetch("/administracja/api/google/odlacz", { method: "POST", credentials: "same-origin" }).then(function () { googleP = null; return google.stan(); })
          .then(rysujGoogle).catch(function () { b.disabled = false; });
      };
    }
    google.stan().then(rysujGoogle);
    // 5.11 (decyzja użytkownika): historia podsumowań odpraw – także schowanych z pulpitu
    fetch("/transakcje/api/podsumowania/moje?wszystkie=1", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : []; })
      .then(function (l) {
        if (!l || !l.length) return;
        var h = o.querySelector(".ph"); h.hidden = false;
        h.querySelector(".pl").innerHTML = l.map(function (s, i) {
          return "<details" + (i ? "" : " open") + "><summary>" + escHtml(s.etykieta || s.okres) + " <small>" + escHtml(new Date(s.kiedy).toLocaleDateString("pl-PL")) +
            "</small></summary><div class=\"pt\">" + podsumowanieHtml(s.dane || {}) + "</div></details>";
        }).join("");
      }).catch(function () {});
    konto().then(function (k) { o.querySelectorAll("[data-ust]").forEach(function (c) { c.checked = wlaczone(k, c.dataset.ust); }); });
    // 13.11 (decyzja użytkownika): „Mój profil” – osobna aplikacja /profil/ (faktury i przychody z ClickUp), tylko z dostępem do obszaru „profil”
    konto().then(function (k) { var p = ((k && k.obszary) || {}).profil; o.querySelector(".pf").hidden = !(p === "dostep" || p === "admin"); });
    o.querySelectorAll("[data-ust]").forEach(function (c) {
      c.addEventListener("change", function () {
        var z = {}; z[c.dataset.ust] = c.checked; c.disabled = true;
        fetch("/administracja/api/ja/ustawienia", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(z) })
          .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
          .then(function (k) {
            try { sessionStorage.setItem("pracawre-konto", JSON.stringify(k)); } catch (e) {}
            kontoP = Promise.resolve(k); notatnik(k);
            if (window.PracawreSamouczek && window.PracawreSamouczek.odswiez) window.PracawreSamouczek.odswiez(k);
          })
          .catch(function () { c.checked = !c.checked; })
          .then(function () { c.disabled = false; });
      });
    });
    var inp = o.querySelector("#pp-prof-o"), bl = o.querySelector(".bl");
    konto().then(function (k) { if (k && k.profil && k.profil.otodom && !inp.value) inp.value = k.profil.otodom; });
    function zamk() { o.remove(); window.removeEventListener("keydown", esc_, true); }
    function esc_(e) { if (e.target && e.target.closest && e.target.closest(".pw-ed")) return; tylkoTo(e, zamk); }
    window.addEventListener("keydown", esc_, true);
    o.addEventListener("click", function (e) { if (e.target === o || e.target.closest("[data-x]")) zamk(); });
    o.querySelector("[data-z]").addEventListener("click", function () {
      bl.hidden = true;
      fetch("/administracja/api/ja/profil", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otodom: inp.value.trim() }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Nie udało się zapisać."); return j; }); })
        .then(function (k) {
          try { sessionStorage.setItem("pracawre-konto", JSON.stringify(k)); } catch (e) {}
          kontoP = Promise.resolve(k); zamk();
          window.dispatchEvent(new CustomEvent("pracawre-profil", { detail: k }));
        })
        .catch(function (e) { bl.textContent = e.message; bl.hidden = false; });
    });
    setTimeout(function () { inp.focus(); }, 0);
  }

  function zglos() {
    if (document.getElementById("pp-zgl")) return;
    if (!document.getElementById("pp-zgl-styl")) {
      var st = document.createElement("style"); st.id = "pp-zgl-styl";
      st.textContent = CSS_ZGL + "@keyframes pkPoj{from{opacity:0}to{opacity:1}}"; document.head.appendChild(st);
    }
    var tu = OBSZARY_ZGL.filter(function (o) { return o.sciezka && location.pathname.indexOf(o.sciezka) === 0; })[0];
    // 13.11 (zgłoszenie A. Sikorskiej): kilka zrzutów (do MAX_ZRZ) i SZKIC – zgłoszenie zapisuje się na bieżąco w przeglądarce
    // (localStorage SZKIC_ZGL), więc zamknięcie okna, żeby zrobić kolejny zrzut, nic nie gubi; szkic znika po wysłaniu albo „Zacznij od nowa”
    var stan = { obszary: [tu ? tu.id : "ogolne"], rodzaj: "blad", zrzuty: [], opis: "", adres: location.href, strona: document.title };
    var szkic = szkicZgl(), przywrocony = false;
    if (szkic) { przywrocony = true; ["obszary", "rodzaj", "zrzuty", "opis", "adres", "strona"].forEach(function (k) { if (szkic[k] != null) stan[k] = szkic[k]; }); }
    var bezMiejsca = false;
    function zapiszSzkic() {
      var tx = tlo.querySelector("textarea"); if (tx) stan.opis = tx.value;
      var pusty = !stan.opis.trim() && !stan.zrzuty.length;
      try {
        if (pusty) { localStorage.removeItem(SZKIC_ZGL); return; }
        var d = { obszary: stan.obszary, rodzaj: stan.rodzaj, opis: stan.opis, adres: stan.adres, strona: stan.strona, czas: Date.now() };
        try { localStorage.setItem(SZKIC_ZGL, JSON.stringify(Object.assign({ zrzuty: stan.zrzuty }, d))); bezMiejsca = false; }
        catch (e) { localStorage.setItem(SZKIC_ZGL, JSON.stringify(Object.assign({ zrzuty: [] }, d))); bezMiejsca = true; }
      } catch (e) { bezMiejsca = true; }
      var u = tlo.querySelector(".zu"); if (u) u.hidden = !bezMiejsca || !stan.zrzuty.length;
    }
    var tlo = document.createElement("div"); tlo.id = "pp-zgl";
    var poprzedni = document.activeElement;
    function zamknij() { tlo.remove(); window.removeEventListener("keydown", klaw, true); document.removeEventListener("paste", wklej); if (poprzedni && poprzedni.focus) poprzedni.focus(); }
    function klaw(e) { if (e.target && e.target.closest && e.target.closest(".pw-ed") && e.target.value) return; tylkoTo(e, zamknij); }
    function rysuj(dostepne) {
      var tx = tlo.querySelector("textarea"), opis = tx ? tx.value : stan.opis;
      tlo.innerHTML = '<div class="ok" role="dialog" aria-modal="true" aria-labelledby="pp-zgl-t">' +
        '<h2 id="pp-zgl-t">Zgłoś błąd albo uwagę<button type="button" class="b x" data-x title="Zamknij">✕</button></h2>' +
        '<p class="op">Trafi do administratora. Opisz, co nie działa – im dokładniej, tym szybciej to poprawimy.</p>' +
        (przywrocony ? '<div class="sk">↺ Wróciło Twoje niewysłane zgłoszenie<button type="button" class="b" data-nowe>Zacznij od nowa</button></div>' : "") +
        '<div class="et">Czego dotyczy (możesz zaznaczyć kilka)</div><div class="cz">' +
        dostepne.map(function (o) { return '<button type="button" data-o="' + o.id + '" aria-pressed="' + (stan.obszary.indexOf(o.id) >= 0) + '"' + (o.opis ? ' title="' + o.opis + '"' : "") + ">" + o.nazwa + "</button>"; }).join("") +
        '</div><div class="et">Rodzaj</div><div class="sg">' +
        RODZAJE_ZGL.map(function (r) { return '<button type="button" data-r="' + r[0] + '" aria-pressed="' + (stan.rodzaj === r[0]) + '">' + r[1] + "</button>"; }).join("") +
        '</div><div class="et">Opis</div><div class="pw-ed"><textarea class="pw-ed-tx" aria-label="Opis" placeholder="Krok po kroku: co zostało zrobione, co się stało i co powinno się stać.">' + esc(opis) + "</textarea>" +
        '<div class="pw-ed-p" style="margin-top:4px"><span class="pw-ed-skr">Ctrl+Enter – wyślij · Esc – zamknij</span></div></div>' +
        '<div class="et">Zrzuty ekranu (opcjonalnie, do ' + MAX_ZRZ + ' – możesz też wkleić Ctrl+V)</div><div class="zr">' +
        stan.zrzuty.map(function (z, i) { return '<span class="zj"><img alt="zrzut ekranu ' + (i + 1) + '" src="' + z + '"><button type="button" class="zx" data-bez="' + i + '" title="Usuń ten zrzut" aria-label="Usuń zrzut ' + (i + 1) + '">✕</button></span>'; }).join("") +
        (stan.zrzuty.length < MAX_ZRZ ? '<label class="b">' + (stan.zrzuty.length ? "+ Kolejny obraz" : "Dodaj obraz") + '<input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden></label>' : "") +
        '</div><div class="zh">Możesz zamknąć to okno, żeby zrobić kolejny zrzut – opis i zrzuty zostaną do wysłania.</div>' +
        '<div class="bl zu" hidden>Zrzuty nie mieszczą się w pamięci przeglądarki – nie zamykaj okna przed wysłaniem (opis zostanie).</div>' +
        '<div class="bl" data-bl hidden></div>' +
        '<div class="st"><span class="in">Dołączymy adres tej strony i rodzaj przeglądarki.</span><button type="button" class="pw-ed-anul" data-x data-pw-anuluj>✕ Anuluj</button>' +
        '<button type="button" class="pw-ed-zap" data-wyslij data-pw-zapisz>✓ Wyślij zgłoszenie</button></div>' +
        '<details><summary>Twoje zgłoszenia</summary><div class="mzl">Wczytywanie…</div></details></div>';
      var t2 = tlo.querySelector("textarea"); t2.addEventListener("input", zapiszSzkic); t2.focus(); t2.setSelectionRange(t2.value.length, t2.value.length);
      var plik = tlo.querySelector("input[type=file]");
      if (plik) plik.addEventListener("change", function () { [].slice.call(plik.files).forEach(obraz); });
      var u = tlo.querySelector(".zu"); if (u) u.hidden = !bezMiejsca || !stan.zrzuty.length;
      tlo.querySelector("details").addEventListener("toggle", moje, { once: true });
    }
    function obraz(f) {                // zmniejszenie do 1600 px (JPEG) – zrzuty z dużych ekranów są ciężkie, a szkic musi się zmieścić
      var r = new FileReader();
      r.onload = function () {
        var im = new Image();
        im.onload = function () {
          if (stan.zrzuty.length >= MAX_ZRZ) return;
          var sk = Math.min(1, 1600 / im.width), c = document.createElement("canvas");
          c.width = Math.round(im.width * sk); c.height = Math.round(im.height * sk);
          c.getContext("2d").drawImage(im, 0, 0, c.width, c.height);
          stan.zrzuty.push(c.toDataURL("image/jpeg", 0.8)); zapiszSzkic(); rysuj(dostepneObszary);
        };
        im.src = r.result;
      };
      r.readAsDataURL(f);
    }
    function wklej(e) { var it = [].slice.call((e.clipboardData || {}).items || []).filter(function (i) { return i.type.indexOf("image/") === 0; }); if (it.length) { e.preventDefault(); it.forEach(function (i) { obraz(i.getAsFile()); }); } }
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
      if (o) { var i = stan.obszary.indexOf(o.dataset.o); if (i >= 0) stan.obszary.splice(i, 1); else stan.obszary.push(o.dataset.o); o.setAttribute("aria-pressed", String(i < 0)); zapiszSzkic(); return; }
      if (r) { stan.rodzaj = r.dataset.r; tlo.querySelectorAll("[data-r]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === r)); }); zapiszSzkic(); return; }
      var bz = e.target.closest("[data-bez]");
      if (bz) { zapiszSzkic(); stan.zrzuty.splice(+bz.dataset.bez, 1); zapiszSzkic(); rysuj(dostepneObszary); return; }
      if (e.target.closest("[data-nowe]")) {
        try { localStorage.removeItem(SZKIC_ZGL); } catch (er) { /* bez pamięci */ }
        przywrocony = false; stan.zrzuty = []; stan.opis = ""; stan.adres = location.href; stan.strona = document.title; stan.rodzaj = "blad";
        stan.obszary = [tu && dostepneObszary.some(function (x) { return x.id === tu.id; }) ? tu.id : "ogolne"];
        var t0 = tlo.querySelector("textarea"); if (t0) t0.value = "";
        rysuj(dostepneObszary); return;
      }
      var w = e.target.closest("[data-wyslij]");
      if (!w) return;
      var bl = tlo.querySelector("[data-bl]"), opis = tlo.querySelector("textarea").value.trim();
      function blad(t) { bl.textContent = t; bl.hidden = false; }
      if (!stan.obszary.length) return blad("Zaznacz, czego dotyczy zgłoszenie.");
      if (opis.length < 3) return blad("Opisz, co nie działa.");
      w.disabled = true; w.textContent = "Wysyłanie…";
      fetch("/administracja/api/zgloszenia", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ obszary: stan.obszary, rodzaj: stan.rodzaj, opis: opis, zrzuty: stan.zrzuty, adres: stan.adres,
          strona: stan.strona, przegladarka: navigator.userAgent, ekran: innerWidth + "×" + innerHeight }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Błąd " + r.status); return j; }); })
        .then(function () {
          try { localStorage.removeItem(SZKIC_ZGL); } catch (er) { /* bez pamięci */ }
          tlo.querySelector(".ok").innerHTML = '<h2>Dziękujemy!<button type="button" class="b x" data-x>✕</button></h2>' +
            '<p class="op" style="margin:8px 0 0">Zgłoszenie trafiło do administratora. Jego stan zobaczysz w tym oknie, w „Twoich zgłoszeniach”.</p>' +
            '<div class="st"><button type="button" class="b p" data-x>Zamknij</button></div>';
        })
        .catch(function (err) { w.disabled = false; w.textContent = "Wyślij zgłoszenie"; blad(err.message || "Nie udało się wysłać – spróbuj ponownie."); });
    });
    window.addEventListener("keydown", klaw, true); document.addEventListener("paste", wklej);
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
  var SZKIC_ZGL = "pracawre-zgloszenie-szkic", MAX_ZRZ = 5;
  function szkicZgl() {              // niewysłane zgłoszenie (7 dni)
    try {
      var d = JSON.parse(localStorage.getItem(SZKIC_ZGL) || "null");
      if (d && Date.now() - (d.czas || 0) < 7 * 864e5 && ((d.opis || "").trim() || (d.zrzuty || []).length)) return d;
    } catch (e) { /* bez pamięci */ }
    return null;
  }


  // --- pływający przycisk „Zacznij dzwonić” (1.11, decyzje użytkownika): JEDYNE miejsce startu trybu „Dzwonię” – pulpit i Zimne.
  // Lew WRE „oddycha”, złote fale, cel dnia z paskiem (/leady/api/cele/moje – obowiązuje cel dyrektora); przesuwany myszą / palcem
  // (próg 6 px, miejsce w localStorage pracawre-dzwon-miejsce); bez rysowanej obwódki; na telefonie samo kółko. naKlik – w Zimnych
  // start trybu na tej samej stronie (bez przeładowania); html.pw-dzwonie (tryb otwarty) ukrywa przycisk.
  var CSS_DZ =
    "#dzwonPrz{position:fixed;z-index:900;right:22px;bottom:22px;display:flex;align-items:center;gap:14px;padding:9px 22px 9px 9px;border-radius:999px;" +
    "  background:#1f1d1a;color:#fff;text-decoration:none;box-shadow:0 12px 30px rgba(31,29,26,.35),0 0 0 1px rgba(201,160,60,.5);" +
    "  touch-action:none;user-select:none;-webkit-user-select:none;cursor:grab;transition:transform .2s,background .2s}" +
    "#dzwonPrz:hover{transform:scale(1.04);background:#2a2316}" +
    "#dzwonPrz.ciagnij{cursor:grabbing;transition:none;transform:scale(1.04)}" +
    ':root[data-theme="dark"] #dzwonPrz{background:#0f1012;box-shadow:0 12px 30px rgba(0,0,0,.6),0 0 0 1px rgba(217,181,90,.55)}' +
    '@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) #dzwonPrz{background:#0f1012;box-shadow:0 12px 30px rgba(0,0,0,.6),0 0 0 1px rgba(217,181,90,.55)}}' +
    "#dzwonPrz .lew{position:relative;flex:none;width:58px;height:58px;border-radius:50%;display:grid;place-items:center;" +
    "  background:radial-gradient(circle at 50% 40%,#2a2722,#141311);box-shadow:inset 0 0 0 2px #c9a03c}" +
    "#dzwonPrz .lew img{width:36px;pointer-events:none;animation:dzOddech 2.4s ease-in-out infinite;filter:drop-shadow(0 0 6px rgba(217,181,90,.35))}" +
    '#dzwonPrz .lew::before,#dzwonPrz .lew::after{content:"";position:absolute;inset:-2px;border-radius:50%;border:2px solid #d9b55a;opacity:0;' +
    "  animation:dzFala 2.4s cubic-bezier(.2,.6,.3,1) infinite}" +
    "#dzwonPrz .lew::after{animation-delay:1.2s}" +
    "@keyframes dzOddech{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}" +
    "@keyframes dzFala{0%{transform:scale(1);opacity:.75}100%{transform:scale(1.75);opacity:0}}" +
    "#dzwonPrz .tx{display:flex;flex-direction:column;line-height:1.15;min-width:0}" +
    "#dzwonPrz .tx b{font-size:1.15rem;font-weight:900;letter-spacing:.01em;transition:letter-spacing .2s}" +
    "#dzwonPrz:hover .tx b{letter-spacing:.04em}" +
    "#dzwonPrz .tx small{font-size:.78rem;color:#d9b55a;font-weight:700;margin-top:3px;white-space:nowrap}" +
    "#dzwonPrz .pas{display:block;height:4px;border-radius:9px;background:rgba(255,255,255,.12);margin-top:5px;overflow:hidden;width:150px}" +
    "#dzwonPrz .pas i{display:block;height:100%;width:0;background:linear-gradient(90deg,#bd9302,#e8c86a);transition:width .6s}" +
    "@media (max-width:640px){#dzwonPrz{padding:6px;gap:0}#dzwonPrz .tx{display:none}}" +
    "@media (prefers-reduced-motion:reduce){#dzwonPrz .lew img,#dzwonPrz .lew::before,#dzwonPrz .lew::after{animation:none}}" +
    "@media print{#dzwonPrz{display:none}}html.pw-dzwonie #dzwonPrz{display:none}";
  // 1.11 (decyzja użytkownika): „Zacznij dzwonić” TYLKO u agentów (rola agent); administrator widzi go w „Widoku agenta”,
  // dyrektor i zarządzanie – nie
  var dzOpcje = null;
  function przyciskDzwonienia(opcje) {
    if (!dzOpcje) window.addEventListener("pracawre-widok-agenta", function () { przyciskDzwonienia(dzOpcje); });
    dzOpcje = opcje || {};
    konto().then(function (k) {
      if (!k) return;
      var agent = k.rola === "agent" || k.rola === "administracja" || (k.admin && widokAgenta());   // 6.11: administracja dzwoni do leadów z marketingu
      if (agent) przyciskDzwonieniaPokaz(opcje);
      else { var b = document.getElementById("dzwonPrz"); if (b) b.remove(); }
    });
  }
  function przyciskDzwonieniaPokaz(opcje) {
    opcje = opcje || {};
    var b = document.getElementById("dzwonPrz");
    if (!b) {
      if (!document.getElementById("pp-dz-styl")) { var st = document.createElement("style"); st.id = "pp-dz-styl"; st.textContent = CSS_DZ; document.head.appendChild(st); }
      b = document.createElement("a");
      b.id = "dzwonPrz"; b.href = "/leady/#dzwonie"; b.setAttribute("aria-label", "Zacznij dzwonić");
      b.title = "Zacznij dzwonić – przytrzymaj i przeciągnij, żeby przesunąć";
      b.innerHTML = '<span class="lew"><img src="/wspolne/lew-wre.png" alt=""></span><span class="tx"><b>Zacznij dzwonić</b><small id="dzwonCel"></small>' +
        '<span class="pas" id="dzwonPas" hidden><i></i></span></span>';
      document.body.appendChild(b);
      var KL = "pracawre-dzwon-miejsce";
      var ustaw = function (x, y) {
        var w = b.offsetWidth, h = b.offsetHeight;
        x = Math.min(Math.max(8, x), innerWidth - w - 8); y = Math.min(Math.max(50, y), innerHeight - h - 8);
        b.style.left = x + "px"; b.style.top = y + "px"; b.style.right = "auto"; b.style.bottom = "auto";
      };
      var zMiejsca = function () { try { var m = JSON.parse(localStorage.getItem(KL) || "null"); if (m) ustaw(m.x * innerWidth, m.y * innerHeight); } catch (e) {} };
      b._zMiejsca = zMiejsca;
      zMiejsca(); addEventListener("resize", zMiejsca);
      var start = null, przesunal = false;
      b.addEventListener("pointerdown", function (e) { if (e.button) return; var r = b.getBoundingClientRect();
        start = { x: e.clientX, y: e.clientY, dx: e.clientX - r.left, dy: e.clientY - r.top }; przesunal = false; b.setPointerCapture(e.pointerId); });
      b.addEventListener("pointermove", function (e) {
        if (!start) return;
        if (!przesunal && Math.hypot(e.clientX - start.x, e.clientY - start.y) < 6) return;
        przesunal = true; b.classList.add("ciagnij"); ustaw(e.clientX - start.dx, e.clientY - start.dy);
      });
      var koniec = function () {
        if (!start) return; start = null; b.classList.remove("ciagnij");
        if (przesunal) { var r = b.getBoundingClientRect(); try { localStorage.setItem(KL, JSON.stringify({ x: r.left / innerWidth, y: r.top / innerHeight })); } catch (e) {} }
      };
      b.addEventListener("pointerup", koniec); b.addEventListener("pointercancel", koniec);
      b.addEventListener("click", function (e) {
        if (przesunal) { e.preventDefault(); przesunal = false; return; }
        if (b._naKlik) { e.preventDefault(); b._naKlik(); }
      });
      b.addEventListener("dragstart", function (e) { e.preventDefault(); });
    }
    b._naKlik = opcje.naKlik || null;
    fetch("/leady/api/cele/moje", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (m) {
      if (!m) return;
      var z = m.dzien.zrobione, c = m.dzien.obowiazuje || {};
      var cz = [c.odebrane ? z.zimne + " z " + c.odebrane + " rozmów" : z.zimne + " rozmów dziś", c.spotkania ? z.spotkania + " z " + c.spotkania + " spotkań" : ""];
      document.getElementById("dzwonCel").textContent = (c.odebrane || c.spotkania ? "Cel dnia: " : "") + cz.filter(Boolean).join(" · ");
      var p = document.getElementById("dzwonPas");
      if (c.odebrane) { p.hidden = false; p.firstElementChild.style.width = Math.min(100, Math.round(z.zimne / c.odebrane * 100)) + "%"; }
      b._zMiejsca();
    }).catch(function () {});
    return b;
  }

  // Esc / Ctrl+Enter w ramce edycji .pw-ed – w każdej aplikacji tak samo (przed jej własnymi skrótami: Esc nie zamyka karty)
  document.addEventListener("keydown", function (e) {
    var ed = e.target && e.target.closest && e.target.closest(".pw-ed");
    if (!ed || e.isComposing) return;
    var sel = e.key === "Escape" ? "[data-pw-anuluj]" : e.key === "Enter" && (e.ctrlKey || e.metaKey) ? "[data-pw-zapisz]" : null;
    if (!sel) return;
    var okno = ed.closest("[role=dialog]");                     // ramka w oknie – przyciski w stopce okna
    var cel = ed.querySelector(sel) || (okno && okno.querySelector(sel));
    if (!cel) return;
    e.preventDefault(); e.stopPropagation(); cel.click();
  }, true);


  // --- Ściągi z podręcznika (11.11, decyzja użytkownika: dla WSZYSTKICH agentów) -----------------------------------------------
  // PracawrePasek.sciaga("telefon" | "spotkanie") – boczny panel (bez zasłaniania strony) z treścią z /wdrozenie/api/sciagi/<rodzaj>
  // (trasa Traefika bez wre-wdrozenie). Treść = aktualny podręcznik z poprawkami dyrektora. Esc / ✕ / ponowne wywołanie zamyka.
  var CSS_SC = "#pp-sc{position:fixed;top:42px;right:0;bottom:0;z-index:2147481000;width:min(520px,100vw);box-sizing:border-box;" +
    "background:var(--card,#fff);color:var(--ink,#1f1d1a);border-left:1px solid var(--line,#e2ddd2);box-shadow:-12px 0 32px rgba(0,0,0,.12);" +
    "display:flex;flex-direction:column;font:14px/1.5 Lato,'Segoe UI',system-ui,sans-serif}" +
    "#pp-sc .pp-sc-g{display:flex;align-items:center;gap:8px;padding:12px 14px 12px 18px;border-bottom:1px solid var(--line,#e2ddd2)}" +
    "#pp-sc .pp-sc-g b{flex:1;font-size:15px}#pp-sc .pp-sc-g a{font-size:12.5px;color:var(--gold-d,#7a5f1c)}" +
    "#pp-sc .pp-sc-x{all:unset;cursor:pointer;width:34px;height:34px;border-radius:10px;display:grid;place-items:center}" +
    "#pp-sc .pp-sc-x:hover{background:var(--hover,#f7f3e8)}#pp-sc .pp-sc-x svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2}" +
    "#pp-sc .pp-sc-w{overflow:auto;padding:12px 16px 24px;overscroll-behavior:contain}" +
    "#pp-sc details{border:1px solid var(--line,#e2ddd2);border-radius:12px;margin-top:10px}" +
    "#pp-sc summary{cursor:pointer;font-weight:800;padding:10px 14px}#pp-sc .pp-sc-c{padding:0 14px 12px}" +
    "#pp-sc .pp-sc-c p{margin:6px 0}#pp-sc .pp-sc-c ul,#pp-sc .pp-sc-c ol{margin:6px 0;padding-left:20px}#pp-sc li+li{margin-top:3px}" +
    "#pp-sc .pp-sc-k{background:var(--gold-bg,#fbf6e8);border-radius:10px;padding:8px 12px}" +
    "#pp-sc .pp-sc-t{display:flex;flex-direction:column;gap:8px}#pp-sc .pp-sc-r{border:1px solid var(--line2,#ece8df);border-radius:10px;padding:8px 10px}" +
    "#pp-sc .pp-sc-r b{display:block}#pp-sc .pp-sc-r span{display:block;color:var(--muted,#6b665d);font-size:12.5px;margin-top:2px}" +
    "#pp-sc .pp-sc-r i{font-style:normal}";
  function mdLinia(t) {
    return esc(t).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/`([^`]+)`/g, "$1");
  }
  // uproszczony Markdown ściąg: akapity, listy (z ptaszkami), cytat „W skrócie”, tabele jako karty (1. kolumna = nagłówek karty)
  function mdSciagi(md) {
    var L = String(md || "").split("\n"), o = [], i = 0, par = [];
    function akapit() { if (par.length) { o.push("<p>" + mdLinia(par.join(" ")) + "</p>"); par = []; } }
    function kom(l) { return l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (x) { return x.trim(); }); }
    while (i < L.length) {
      var l = L[i];
      if (!l.trim()) { akapit(); i++; continue; }
      if (/^>/.test(l)) { akapit(); var w = []; while (i < L.length && /^>/.test(L[i])) w.push(L[i++].replace(/^>\s?/, "")); o.push('<div class="pp-sc-k">' + mdSciagi(w.join("\n")) + "</div>"); continue; }
      if (/^\s*\|/.test(l) && /^\s*\|[\s:|-]+\|\s*$/.test(L[i + 1] || "")) {
        akapit(); var nag = kom(l), r = []; i += 2;
        while (i < L.length && /^\s*\|/.test(L[i])) r.push(kom(L[i++]));
        o.push('<div class="pp-sc-t">' + r.map(function (w) {
          return '<div class="pp-sc-r"><b>' + mdLinia(w[0]) + "</b>" + w.slice(1).map(function (k, j) {
            return "<span><i>" + mdLinia(nag[j + 1] || "") + ":</i> " + mdLinia(k) + "</span>"; }).join("") + "</div>"; }).join("") + "</div>");
        continue;
      }
      var m = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(l);
      if (m) {
        akapit(); var num = /\d/.test(m[2]), el = [];
        while (i < L.length) {
          var k2 = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(L[i]);
          if (k2) { el.push(k2[3]); i++; continue; }
          if (L[i].trim() && /^\s{2,}\S/.test(L[i]) && el.length) { el[el.length - 1] += " " + L[i].trim(); i++; continue; }
          break;
        }
        o.push((num ? "<ol>" : "<ul>") + el.map(function (t) { return "<li>" + mdLinia(t.replace(/^\[( |x)\]\s+/i, "☐ ")) + "</li>"; }).join("") + (num ? "</ol>" : "</ul>"));
        continue;
      }
      if (/^#{1,6}\s/.test(l)) { akapit(); o.push("<p><b>" + mdLinia(l.replace(/^#+\s+/, "")) + "</b></p>"); i++; continue; }
      par.push(l.trim()); i++;
    }
    akapit();
    return o.join("");
  }
  var scOtwarta = null;
  function zamknijSciage() { var el = document.getElementById("pp-sc"); if (el) el.remove(); window.removeEventListener("keydown", klawSc, true); scOtwarta = null; }
  function klawSc(e) { if (document.getElementById("pp-sc")) tylkoTo(e, zamknijSciage); }
  function sciaga(rodzaj) {
    if (scOtwarta === rodzaj) return zamknijSciage();
    zamknijSciage(); styl();
    if (!document.getElementById("pp-sc-styl")) { var st = document.createElement("style"); st.id = "pp-sc-styl"; st.textContent = CSS_SC; document.head.appendChild(st); }
    var el = document.createElement("aside");
    el.id = "pp-sc"; el.setAttribute("aria-label", "Ściąga");
    el.innerHTML = '<div class="pp-sc-g"><b>Ściąga</b><button type="button" class="pp-sc-x" title="Zamknij (Esc)" aria-label="Zamknij">' +
      svg('<path d="M6 6l12 12M18 6 6 18"/>') + '</button></div><div class="pp-sc-w"><p>Wczytywanie…</p></div>';
    document.body.appendChild(el); scOtwarta = rodzaj;
    el.querySelector(".pp-sc-x").addEventListener("click", zamknijSciage);
    window.addEventListener("keydown", klawSc, true);
    fetch("/wdrozenie/api/sciagi/" + encodeURIComponent(rodzaj), { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        el.querySelector(".pp-sc-g b").textContent = d.tytul;
        el.querySelector(".pp-sc-w").innerHTML = d.czesci.map(function (c, n) {
          return "<details" + (n < 2 ? " open" : "") + "><summary>" + esc(c.tytul) + '</summary><div class="pp-sc-c">' + mdSciagi(c.md) + "</div></details>";
        }).join("");
      })
      .catch(function () { el.querySelector(".pp-sc-w").innerHTML = "<p>Nie udało się wczytać ściągi – spróbuj za chwilę.</p>"; });
  }

  // 12.11 (decyzja użytkownika: „po kliknięciu czegokolwiek, jak jesteśmy wylogowani – wyrzuca do logowania”): zapytanie aplikacji
  // zamiast danych dostało stronę logowania → od razu odświeżenie strony = logowanie Google i powrót w to samo miejsce. Okienko
  // „Sesja wygasła” tylko gdy to samo zdarzy się drugi raz w ciągu minuty (zabezpieczenie przed pętlą odświeżania).
  (function () {
    if (!window.fetch || window.fetch.__sesja) return;
    var f0 = window.fetch, pokazane = false;
    function oknoSesji() {
      if (pokazane || document.getElementById("pp-sesja")) return;
      pokazane = true;
      var ost = 0;
      try { ost = +sessionStorage.getItem("pracawre-sesja-odswiez") || 0; } catch (e) {}
      // agent właśnie coś pisze (pole tekstowe z treścią) – nie odświeżamy w ciemno, tylko okienko: najpierw skopiuje tekst
      var a = document.activeElement, pisze = a && /^(TEXTAREA|INPUT)$/.test(a.tagName) && !/^(button|checkbox|radio|submit|hidden)$/.test(a.type || "") && (a.value || "").trim().length > 3;
      if (!pisze && Date.now() - ost > 60000) {
        try { sessionStorage.setItem("pracawre-sesja-odswiez", String(Date.now())); } catch (e) {}
        location.reload();
        return;
      }
      var o = document.createElement("div");
      o.id = "pp-sesja"; o.setAttribute("role", "dialog"); o.setAttribute("aria-modal", "true");
      o.innerHTML = '<div class="pp-ses-k"><div style="font-size:34px">🔒</div><h2>Sesja wygasła</h2>' +
        "<p>Ze względów bezpieczeństwa logowanie co jakiś czas wygasa. Zaloguj się ponownie – wrócisz w to samo miejsce. Niezapisany tekst skopiuj przed kliknięciem.</p>" +
        '<button type="button" data-ses>Zaloguj się ponownie</button></div>';
      var st = document.createElement("style");
      st.textContent = "#pp-sesja{position:fixed;inset:0;z-index:2147483600;background:rgba(15,14,12,.6);display:grid;place-items:center;padding:16px;font:15px/1.5 Lato,system-ui,sans-serif}" +
        "#pp-sesja .pp-ses-k{background:#fff;color:#1f1d1a;border-radius:18px;padding:24px 26px;max-width:420px;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.35)}" +
        "html[data-theme=dark] #pp-sesja .pp-ses-k{background:#212326;color:#e8e5de}#pp-sesja h2{margin:6px 0 8px;font-size:21px}" +
        "#pp-sesja button{all:unset;cursor:pointer;margin-top:12px;height:42px;padding:0 22px;border-radius:999px;background:#c9a03c;color:#141518;font-weight:800;display:inline-flex;align-items:center}";
      document.head.appendChild(st); document.body.appendChild(o);
      o.querySelector("[data-ses]").addEventListener("click", function () { location.reload(); });
    }
    var f = function (u, opt) {
      return f0.apply(this, arguments).then(function (r) {
        try {
          var url = new URL(typeof u === "string" ? u : (u && u.url) || "", location.href);
          if (url.origin === location.origin && (r.status === 401 || r.status === 403) && /text\/html/.test(r.headers.get("content-type") || "")) {
            r.clone().text().then(function (t) { if (/oauth2\/start|oauth2\/sign_in/.test(t)) oknoSesji(); }).catch(function () {});
          }
        } catch (e) {}
        return r;
      });
    };
    f.__sesja = true; window.fetch = f;
  })();

  window.PracawrePasek = { sciaga: sciaga, liczby: liczby, przyciskDzwonienia: przyciskDzwonienia, widokAgenta: widokAgenta, ustawWidokAgenta: ustawWidokAgenta, wypelnij: wypelnij, ustaw: ustaw, wybor: wybor, ciemny: ciemny, kartoteka: kartoteka, konto: konto, zglos: zglos, profil: profil, google: google, aplikacje: aplikacje, grupy: GRUPY };
  if (mq && mq.addEventListener) mq.addEventListener("change", zastosuj);
  window.addEventListener("storage", function (e) { if (e.key === KLUCZ) zastosuj(); if (e.key === KLUCZ_AGENT) zmianaWidoku(); });
  html.classList.toggle("pw-agent", widokAgenta());
  styl();
  zastosuj();
  // 1.11 (decyzja użytkownika): karta przeglądarki na każdej stronie WRE = „WRE Nieruchomości” z lwem (bez Radaru działek –
  // osobny projekt); strony mają to w <title> i <link rel=icon>, tu zapas dla stron bez ikonki
  if (location.pathname.indexOf("/radar") !== 0 && !document.querySelector('link[rel~="icon"]')) {
    var ik = document.createElement("link"); ik.rel = "icon"; ik.type = "image/png"; ik.href = "/wspolne/lew-wre.png";
    document.head.appendChild(ik);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sam); else sam();
})();
