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
    { href: "/umowy/", nazwa: "Generator umów", krotko: "Umowy", ikona: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>' },
    { href: "/protokoly/", nazwa: "Protokoły", krotko: "Protokoły", ikona: '<path d="M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1z"/><path d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><path d="m9 14 2 2 4-4"/>' },
    { href: "/radar/", nazwa: "Radar działek", krotko: "Radar", ikona: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12l6-6"/>' }
  ];
  var IKONY = {
    auto: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none"/>',
    light: '<circle cx="12" cy="12" r="4.5"/><path d="M12 1.5v2.5M12 20v2.5M1.5 12H4M20 12h2.5M4.6 4.6l1.8 1.8M17.6 17.6l1.8 1.8M4.6 19.4l1.8-1.8M17.6 6.4l1.8-1.8"/>',
    dark: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'
  };
  var OPIS = { auto: "automatyczny (jak w systemie)", light: "jasny", dark: "ciemny" };
  var KOLEJNY = { auto: "light", light: "dark", dark: "auto" };

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
    odswiezPrzycisk();
    try { window.dispatchEvent(new CustomEvent("pracawre-motyw", { detail: { ciemny: c, wybor: wybor() } })); } catch (e) {}
  }
  function ustaw(w) { try { localStorage.setItem(KLUCZ, w); } catch (e) {} zastosuj(); }

  var CSS =
    "@view-transition{navigation:auto}" +
    "::view-transition-old(root),::view-transition-new(root){animation-duration:.22s}" +
    "#pracawre-pasek{flex:none;position:relative;z-index:60}" +
    ".pp{view-transition-name:pracawre-pasek;box-sizing:border-box;display:flex;align-items:center;gap:4px;height:40px;" +
    "padding:0 max(12px,env(safe-area-inset-right)) 0 max(12px,env(safe-area-inset-left));background:#141518;color:#d9d5cc;" +
    "border-bottom:2px solid #c9a03c;font:600 13px/1 Lato,'Segoe UI',system-ui,-apple-system,sans-serif;letter-spacing:.01em}" +
    ".pp *{box-sizing:border-box}" +
    ".pp a,.pp button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:7px;height:30px;padding:0 10px;" +
    "border-radius:8px;color:#bdb8ad;white-space:nowrap;transition:background .15s,color .15s}" +
    ".pp a:hover,.pp button:hover{background:rgba(255,255,255,.07);color:#fff}" +
    ".pp a:focus-visible,.pp button:focus-visible{outline:2px solid #c9a03c;outline-offset:-2px}" +
    ".pp svg{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}" +
    ".pp .pp-dom{color:#f3efe6;padding-left:6px}.pp .pp-dom b{color:#c9a03c;font-weight:700}" +
    ".pp .pp-sep{width:1px;height:18px;background:rgba(255,255,255,.16);margin:0 6px;flex:none}" +
    ".pp .pp-apps{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;min-width:0}.pp .pp-apps::-webkit-scrollbar{display:none}" +
    ".pp .pp-apps a[aria-current=page]{color:#fff;background:rgba(201,160,60,.16);box-shadow:inset 0 -2px 0 #c9a03c}" +
    ".pp .pp-apps a .k{display:none}" +
    ".pp .pp-r{margin-left:auto;display:flex;gap:2px;flex:none}" +
    ".pp .pp-wyl{color:#dcb874}" +
    "@media (max-width:720px){.pp .pp-apps a .d{display:none}.pp .pp-apps a .k{display:inline}.pp .pp-dom span{display:none}.pp .pp-wyl span{display:none}}" +
    "@media (max-width:420px){.pp .pp-apps a .k{display:none}}" +
    "@media print{#pracawre-pasek{display:none!important}}";

  function styl() {
    if (document.getElementById("pracawre-pasek-styl")) return;
    var s = document.createElement("style");
    s.id = "pracawre-pasek-styl";
    s.textContent = CSS;
    (document.head || html).appendChild(s);
  }

  function svg(d) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + d + "</svg>"; }

  function odswiezPrzycisk() {
    var b = document.querySelector(".pp-motyw");
    if (!b) return;
    var w = wybor();
    b.innerHTML = svg(IKONY[w]);
    b.title = "Motyw: " + OPIS[w] + " – kliknij: " + OPIS[KOLEJNY[w]];
    b.setAttribute("aria-label", b.title);
  }

  function wypelnij(el) {
    if (!el) return;
    styl();
    var sciezka = location.pathname;
    var apps = APPS.map(function (a) {
      var akt = sciezka.indexOf(a.href) === 0 || sciezka + "/" === a.href;
      return '<a href="' + a.href + '"' + (akt ? ' aria-current="page"' : "") + ">" + svg(a.ikona) +
        '<span class="d">' + a.nazwa + '</span><span class="k">' + a.krotko + "</span></a>";
    }).join("");
    el.innerHTML =
      '<nav class="pp" aria-label="pracawre.com">' +
      '<a class="pp-dom" href="/" title="Strona główna">' + svg('<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>') +
      "<span><b>pracawre</b>.com</span></a>" +
      '<span class="pp-sep" aria-hidden="true"></span>' +
      '<div class="pp-apps">' + apps + "</div>" +
      '<div class="pp-r"><button type="button" class="pp-motyw"></button>' +
      '<a class="pp-wyl" href="/oauth2/sign_out?rd=%2F" title="Wyloguj">' +
      svg('<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4"/>') + "<span>Wyloguj</span></a></div>" +
      "</nav>";
    el.querySelector(".pp-motyw").addEventListener("click", function () { ustaw(KOLEJNY[wybor()]); });
    odswiezPrzycisk();
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

  window.PracawrePasek = { wypelnij: wypelnij, ustaw: ustaw, wybor: wybor, ciemny: ciemny };
  if (mq && mq.addEventListener) mq.addEventListener("change", zastosuj);
  window.addEventListener("storage", function (e) { if (e.key === KLUCZ) zastosuj(); });
  styl();
  zastosuj();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sam); else sam();
})();
