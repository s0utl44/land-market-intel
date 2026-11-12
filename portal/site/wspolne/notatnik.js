/* Notatnik pracawre.com (12.11.2026, decyzje użytkownika) – ładowany przez /wspolne/pasek.js na każdej stronie z paskiem.
   - przycisk „📝 Notatnik” w pasku u góry (obok 🎓) i skrót Alt+N → pływające okno spod paska: przeciągane za ciemny nagłówek,
     rozmiar zmieniany rogiem (mały = sama notatka, średni = lista + notatka, duży = kategorie + lista + notatka); miejsce, rozmiar
     i to, czy okno jest otwarte, pamięta przeglądarka (localStorage pracawre-notatnik-okno) – okno zostaje przy przechodzeniu stron.
   - notatki PRYWATNE (widzi tylko autor), zwykły tekst, własne kategorie (nazwa, kolor, kolejność), zapis automatyczny na koncie
     (Kontakty: /administracja/api/notatnik), kosz 30 dni. Bez przypomnień.
   - „📌 Przypnij na stronie głównej” – notatka staje się karteczką na stronie głównej: dowolne miejsce i kształt (przeciąganie,
     róg ⇲), pisanie wprost na karteczce; na telefonie karteczki jedna pod drugą.
   - włączany / wyłączany przez każdego w „Mój profil” (profil.ustawienia.notatnik). */
(function () {
  if (window.PracawreNotatnik || window.top !== window) return;
  var API = "/administracja/api/notatnik", KL_OKNO = "pracawre-notatnik-okno";
  var D = { notatki: [], kategorie: [], kolory: [], kosz: 0 }, zaladowane = null;
  var S = { kat: "all", przyp: false, q: "", id: null, zarz: false, kosz: null };
  var okno = null, warstwa = null, wlaczony = true;
  var czekaZapis = {}, zapisCzas = {}, swiezoUtworzona = null;
  var bc = null;
  try { bc = new BroadcastChannel("pracawre-notatnik"); bc.onmessage = function () { laduj(); }; } catch (e) {}

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function czytaj(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } }
  function zapisz(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function bezOgonkow(s) { return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l"); }
  function api(metoda, sciezka, cialo) {
    return fetch(API + (sciezka || ""), { method: metoda, credentials: "same-origin", headers: cialo ? { "Content-Type": "application/json" } : {},
      body: cialo ? JSON.stringify(cialo) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || "Błąd " + r.status); return j; }); });
  }
  function rozeslij() { if (bc) try { bc.postMessage(1); } catch (e) {} }
  function notatka(id) { return D.notatki.filter(function (n) { return n.id === id; })[0]; }
  function kategoria(id) { return D.kategorie.filter(function (k) { return k.id === id; })[0]; }
  function tytul(n) { var l = (n.tresc || "").split("\n").map(function (x) { return x.trim(); }).filter(Boolean); return { t: l[0] || "Nowa notatka", r: l.slice(1).join(" ") }; }
  function kiedy(iso) {
    if (!iso) return ""; var d = new Date(iso), t = new Date(), w = new Date(t); w.setDate(t.getDate() - 1);
    var g = d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
    if (d.toDateString() === t.toDateString()) return "dziś " + g;
    if (d.toDateString() === w.toDateString()) return "wczoraj " + g;
    return d.toLocaleDateString("pl-PL", { day: "numeric", month: "short" });
  }

  // ---------- dane ----------
  function laduj() {
    zaladowane = api("GET").then(function (d) {
      var stare = {}; D.notatki.forEach(function (n) { stare[n.id] = n; });
      d.notatki.forEach(function (n) { if (czekaZapis[n.id] && stare[n.id]) n.tresc = stare[n.id].tresc; });   // nie gubimy pisanego
      D = d;
      if (S.id && !notatka(S.id)) S.id = null;
      rysuj(); rysujKartki();
      return d;
    }).catch(function () { zaladowane = null; status("⚠ Brak połączenia – notatki niedostępne", "bl"); });
    return zaladowane;
  }
  function zmien(id, pola, odKogo) {
    var n = notatka(id); if (!n) return Promise.resolve();
    Object.keys(pola).forEach(function (k) { n[k] = pola[k]; });
    if ("tresc" in pola) {
      n.zmieniono = new Date().toISOString();
      czekaZapis[id] = true; status("Zapisywanie…", "");
      clearTimeout(zapisCzas[id]);
      zapisCzas[id] = setTimeout(function () { wyslij(id); }, 700);
      odswiezInne(id, odKogo);
      return Promise.resolve();
    }
    return api("PUT", "/notatki/" + id, pola).then(function (z) { if (czekaZapis[id]) z.tresc = n.tresc; Object.assign(n, z); rozeslij(); rysuj(); rysujKartki(); })
      .catch(function (e) { status("⚠ " + e.message, "bl"); });
  }
  function wyslij(id) {
    var n = notatka(id); if (!n) return Promise.resolve();
    clearTimeout(zapisCzas[id]);
    return api("PUT", "/notatki/" + id, { tresc: n.tresc }).then(function () {
      delete czekaZapis[id]; status("✓ Zapisano", "ok"); rozeslij();
    }).catch(function () {
      status("⚠ Nie zapisano – ponawiam…", "bl");
      zapisCzas[id] = setTimeout(function () { wyslij(id); }, 4000);
    });
  }
  function wyslijWszystko() { Object.keys(czekaZapis).forEach(function (id) { wyslij(+id); }); }
  window.addEventListener("pagehide", function () {
    Object.keys(czekaZapis).forEach(function (id) {
      var n = notatka(+id); if (!n) return;
      try { fetch(API + "/notatki/" + id, { method: "PUT", credentials: "same-origin", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tresc: n.tresc }) }); } catch (e) {}
    });
  });
  function odswiezInne(id, odKogo) {
    if (odKogo !== "okno" && okno) {
      var ta = okno.querySelector(".nt-t"); if (S.id === id && ta && document.activeElement !== ta) ta.value = notatka(id).tresc;
    }
    if (odKogo !== "kartka" && warstwa) {
      var k = warstwa.querySelector('.kt[data-id="' + id + '"] textarea'); if (k && document.activeElement !== k) k.value = notatka(id).tresc;
    }
    if (okno) rysujListe();
  }
  function nowa(pola) {
    var kat = typeof S.kat === "number" ? S.kat : null;
    return api("POST", "/notatki", Object.assign({ kategoria: kat }, pola || {})).then(function (n) {
      D.notatki.unshift(n); swiezoUtworzona = n.id; wybierz(n.id); rozeslij();
      setTimeout(function () { var ta = okno && okno.querySelector(".nt-t"); if (ta) ta.focus(); }, 30);
      return n;
    }).catch(function (e) { status("⚠ " + e.message, "bl"); });
  }
  function wybierz(id) {
    var stara = S.id;
    if (stara && stara !== id && stara === swiezoUtworzona) {            // pusta, dopiero co założona – sprzątamy
      var n = notatka(stara);
      if (n && !n.tresc.trim()) { D.notatki = D.notatki.filter(function (x) { return x.id !== stara; }); api("DELETE", "/notatki/" + stara).catch(function () {}); }
    }
    if (stara && czekaZapis[stara]) wyslij(stara);
    S.id = id; rysuj();
  }
  function usun(id) {
    var n = notatka(id); if (!n) return;
    if (n.tresc.trim() && !confirm("Usunąć notatkę „" + tytul(n).t + "”?\nPrzez 30 dni możesz ją przywrócić z kosza.")) return;
    clearTimeout(zapisCzas[id]); delete czekaZapis[id];
    api("DELETE", "/notatki/" + id).then(function () {
      D.notatki = D.notatki.filter(function (x) { return x.id !== id; });
      if (n.tresc.trim()) D.kosz++;
      if (S.id === id) S.id = null;
      rozeslij(); rysuj(); rysujKartki();
    }).catch(function (e) { status("⚠ " + e.message, "bl"); });
  }
  function przypnij(id, tak) {
    var n = notatka(id); if (!n) return;
    var pola = { przypieta: tak };
    if (tak && !(n.poz && n.poz.y)) {
      // nowa karteczka – z prawej strony ekranu, kolejne lekko przesunięte (potem agent przeciąga, gdzie chce)
      var ile = D.notatki.filter(function (x) { return x.przypieta; }).length, W = document.documentElement.clientWidth;
      pola.poz = { x: Math.max(0, (W - 270 - (ile % 5) * 28) / W), y: 110 + (ile % 5) * 44, w: 240, h: 190, z: 1 + ile };
    }
    zmien(id, pola);
  }
  function kopiuj(tekst, przycisk) {
    var ok = function () { if (przycisk) { var t = przycisk.textContent; przycisk.textContent = "✓ Skopiowano"; setTimeout(function () { przycisk.textContent = t; }, 1400); } };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(tekst).then(ok, function () {});
  }

  // ---------- wygląd ----------
  var CSS =
    "#pp-nt,.kt,#pp-kartki{--k:#fff;--k2:#faf8f3;--t:#1f1d1a;--m:#6b665d;--l:#e2ddd2;--z:#c9a03c;--zt:#7a5f1c;--zj:#fbf3d8}" +
    "html[data-theme=dark] #pp-nt{--k:#212326;--k2:#1a1c1e;--t:#e8e5de;--m:#a39e94;--l:#33363a;--zt:#e5c46b;--zj:#3a3220}" +
    "#pp-nt{position:fixed;z-index:2147481500;display:flex;flex-direction:column;background:var(--k2);color:var(--t);border:1px solid var(--l);border-radius:14px;" +
    "box-shadow:0 22px 60px rgba(0,0,0,.28);overflow:hidden;resize:both;min-width:260px;min-height:200px;max-width:calc(100vw - 8px);max-height:calc(100vh - 46px);" +
    "font:14px/1.45 Lato,system-ui,sans-serif;box-sizing:border-box}" +
    "#pp-nt *{box-sizing:border-box}#pp-nt button{font:inherit;color:inherit;cursor:pointer}" +
    "#pp-nt .nt-h{flex:none;display:flex;align-items:center;gap:8px;padding:7px 8px 7px 12px;background:#1f1d1a;color:#fff;cursor:move;user-select:none;touch-action:none}" +
    "#pp-nt .nt-h b{font-weight:800;white-space:nowrap}#pp-nt .nt-h kbd{font:11px Lato,sans-serif;color:#c9c3b6;border:1px solid #4a463d;border-radius:5px;padding:0 5px}" +
    "#pp-nt .nt-q{flex:1;min-width:60px;max-width:240px;margin-left:auto;height:28px;border-radius:999px;border:1px solid #4a463d;background:#2b2925;color:#fff;padding:0 12px;font:inherit;font-size:13px;outline:none;cursor:text}" +
    "#pp-nt .nt-q:focus{border-color:var(--z)}" +
    "#pp-nt .nt-x{all:unset;cursor:pointer;width:28px;height:28px;border-radius:999px;display:grid;place-items:center;color:#f3d98a;border:1px solid #4a463d}#pp-nt .nt-x:hover{background:#3a3220}" +
    "#pp-nt .nt-b{flex:1;min-height:0;display:grid;grid-template-columns:170px 215px minmax(0,1fr)}" +
    "#pp-nt.w2 .nt-b{grid-template-columns:200px minmax(0,1fr)}#pp-nt.w1 .nt-b{grid-template-columns:minmax(0,1fr)}" +
    "#pp-nt.w2 .nt-kat,#pp-nt.w1 .nt-kat,#pp-nt.w1 .nt-lis{display:none}#pp-nt .nt-kats,#pp-nt .nt-wyb{display:none}#pp-nt.w2 .nt-kats,#pp-nt.w1 .nt-wyb{display:block}" +
    "#pp-nt.w1 .nt-q,#pp-nt.w1 .nt-h kbd{display:none}#pp-nt.w1 .nt-h .nt-sp{flex:1}" +
    "#pp-nt .nt-kat{border-right:1px solid var(--l);padding:8px 6px;overflow:auto;display:flex;flex-direction:column;gap:1px}" +
    "#pp-nt .nt-c{all:unset;cursor:pointer;display:flex;align-items:center;gap:8px;padding:6px 9px;border-radius:9px;font-size:13.5px}#pp-nt .nt-c:hover{background:var(--k)}" +
    "#pp-nt .nt-c[aria-pressed=true]{background:var(--zj);font-weight:800}#pp-nt .nt-c i{margin-left:auto;font-style:normal;color:var(--m);font-size:12px;font-weight:400}" +
    "#pp-nt .cd{width:10px;height:10px;border-radius:3px;flex:none;display:inline-block}" +
    "#pp-nt .nt-sep{border-top:1px solid var(--l);margin:7px 4px}#pp-nt .nt-c.z{color:var(--zt);font-weight:800}#pp-nt .nt-c.m{color:var(--m);font-size:12.5px}" +
    "#pp-nt .nt-c input{accent-color:#bd9302;margin:0}" +
    "#pp-nt .nt-nk{display:flex;gap:4px;padding:2px 2px}#pp-nt .nt-nk input{flex:1;min-width:0;height:28px;border:1px solid var(--z);border-radius:8px;background:var(--k);color:var(--t);padding:0 8px;font:inherit;font-size:13px;outline:none}" +
    "#pp-nt .nt-lis{border-right:1px solid var(--l);display:flex;flex-direction:column;min-height:0}" +
    "#pp-nt .nt-lg{padding:8px 8px 6px;display:flex;flex-direction:column;gap:6px}" +
    "#pp-nt .nt-nowa{all:unset;cursor:pointer;text-align:center;height:32px;line-height:32px;border-radius:999px;background:#1f1d1a;color:#fff!important;font-weight:800;font-size:13px}" +
    "html[data-theme=dark] #pp-nt .nt-nowa{background:#c9a03c;color:#1f1d1a!important}" +
    "#pp-nt select{height:30px;border-radius:8px;border:1px solid var(--l);background:var(--k);color:var(--t);font:inherit;font-size:13px;padding:0 6px;max-width:100%}" +
    "#pp-nt .nt-l{flex:1;overflow:auto;padding:0 6px 8px;display:flex;flex-direction:column;gap:3px}" +
    "#pp-nt .nt-n{all:unset;cursor:pointer;display:block;padding:7px 9px;border-radius:10px;border:1px solid transparent;font-size:12.5px;color:var(--m);line-height:1.35}" +
    "#pp-nt .nt-n:hover{background:var(--k)}#pp-nt .nt-n[aria-current=true]{background:var(--k);border-color:#bd9302}" +
    "#pp-nt .nt-n b{display:flex;align-items:center;gap:6px;color:var(--t);font-size:13.5px;overflow:hidden;white-space:nowrap}#pp-nt .nt-n b span{overflow:hidden;text-overflow:ellipsis}" +
    "#pp-nt .nt-n .r{display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}#pp-nt .nt-n small{display:block;font-size:11px;margin-top:2px}" +
    "#pp-nt .nt-pusto{color:var(--m);font-size:13px;padding:14px 8px;text-align:center}" +
    "#pp-nt .nt-ed{display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--k)}" +
    "#pp-nt .nt-eh{display:flex;align-items:center;gap:6px;padding:8px 10px 0}#pp-nt .nt-eh .nt-wyb{flex:1;min-width:0}" +
    "#pp-nt .nt-pl{all:unset;cursor:pointer;width:30px;height:30px;border-radius:999px;display:none;place-items:center;background:#1f1d1a;color:#fff;font-weight:800}#pp-nt.w1 .nt-pl{display:grid}" +
    "#pp-nt .nt-katn{margin-left:auto}" +
    "#pp-nt .nt-t{flex:1;min-height:0;width:100%;border:0;outline:none;resize:none;background:transparent;color:var(--t);padding:10px 14px;font:14.5px/1.6 Lato,system-ui,sans-serif}" +
    "#pp-nt .nt-s{flex:none;display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:7px 10px;border-top:1px solid var(--l);font-size:12.5px}" +
    "#pp-nt .nt-p{all:unset;cursor:pointer;height:28px;padding:0 11px;border-radius:999px;border:1px solid var(--l);display:inline-flex;align-items:center;gap:5px;white-space:nowrap}" +
    "#pp-nt .nt-p:hover{border-color:var(--z)}#pp-nt .nt-p[aria-pressed=true]{background:var(--zj);border-color:#bd9302;color:var(--zt);font-weight:800}" +
    "#pp-nt .nt-st{margin-left:auto;color:var(--m);white-space:nowrap}#pp-nt .nt-st.ok{color:#4f8a3e}#pp-nt .nt-st.bl{color:#c0392b}" +
    "#pp-nt .nt-zero{flex:1;display:grid;place-items:center;text-align:center;color:var(--m);padding:20px}" +
    "#pp-nt .nt-zarz{position:absolute;inset:43px 0 0 0;background:var(--k);z-index:2;overflow:auto;padding:14px 16px}" +
    "#pp-nt .nt-zarz h3{margin:0 0 2px;font-size:16px}#pp-nt .nt-zarz p{margin:0 0 10px;color:var(--m);font-size:12.5px}" +
    "#pp-nt .nt-zr{display:flex;align-items:center;gap:6px;padding:6px 0;border-bottom:1px solid var(--l)}" +
    "#pp-nt .nt-zr input{flex:1;min-width:0;height:30px;border:1px solid var(--l);border-radius:8px;background:var(--k);color:var(--t);padding:0 8px;font:inherit}" +
    "#pp-nt .nt-zr .kol{all:unset;cursor:pointer;width:22px;height:22px;border-radius:6px;flex:none;box-shadow:inset 0 0 0 1px rgba(0,0,0,.15)}" +
    "#pp-nt .nt-zr .m{all:unset;cursor:pointer;width:26px;height:26px;border-radius:8px;display:grid;place-items:center;color:var(--m)}#pp-nt .nt-zr .m:hover{background:var(--k2)}" +
    "#pp-nt .nt-zr .m:disabled{opacity:.3;cursor:default}" +
    "#pp-nt .nt-zs{display:flex;gap:8px;margin-top:12px;align-items:center}" +
    "@media (max-width:600px){#pp-nt{left:0!important;top:42px!important;width:100vw!important;height:calc(100vh - 42px)!important;max-height:none;border-radius:0;resize:none}#pp-nt .nt-h{cursor:default}}" +
    // przycisk w pasku
    ".pp .pp-not{position:relative;height:28px;padding:0 11px;border-radius:999px;border:1px solid #8a6d1c;background:#2b2618;color:#f3d98a;font-size:12.5px;font-weight:800;cursor:pointer;display:inline-flex;align-items:center;gap:5px}" +
    ".pp .pp-not:hover,.pp .pp-not[aria-pressed=true]{background:#3a3220;color:#fff}.pp .pp-not[aria-pressed=true]{box-shadow:0 0 0 2px rgba(201,160,60,.45)}" +
    "@media (max-width:600px){.pp .pp-not .pp-not-t{display:none}.pp .pp-not{padding:0 8px}}" +
    // karteczki na stronie głównej
    "#pp-kartki{position:absolute;left:0;top:0;width:100%;height:0;z-index:40}" +
    ".kt{position:absolute;display:flex;flex-direction:column;box-sizing:border-box;padding:10px 12px 8px;border-radius:3px;color:#2b2820;" +
    "box-shadow:0 10px 22px rgba(0,0,0,.16),0 2px 4px rgba(0,0,0,.08);resize:both;overflow:hidden;min-width:140px;min-height:90px;transition:transform .15s,box-shadow .15s;font:14px/1.45 Lato,system-ui,sans-serif}" +
    ".kt:hover,.kt:focus-within,.kt.ciag{transform:none!important;box-shadow:0 18px 36px rgba(0,0,0,.22),0 2px 4px rgba(0,0,0,.1)}" +
    ".kt::before{content:'';position:absolute;top:5px;left:50%;margin-left:-6px;width:12px;height:12px;border-radius:50%;background:var(--pin,#c0392b);box-shadow:0 2px 3px rgba(0,0,0,.35)}" +
    ".kt .kt-h{display:flex;align-items:center;gap:2px;font-size:10.5px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:rgba(0,0,0,.45);cursor:move;user-select:none;touch-action:none;padding-top:8px;min-height:24px}" +
    ".kt .kt-h span{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}" +
    ".kt .kt-h button{all:unset;cursor:pointer;width:22px;height:22px;border-radius:6px;display:grid;place-items:center;font-size:12px;color:rgba(0,0,0,.5);opacity:0;transition:opacity .15s}" +
    ".kt:hover .kt-h button,.kt:focus-within .kt-h button{opacity:1}.kt .kt-h button:hover{background:rgba(0,0,0,.08);color:#000}" +
    ".kt textarea{flex:1;min-height:0;width:100%;border:0;outline:none;resize:none;background:transparent;color:inherit;font:inherit;padding:2px 0;margin:0}" +
    "@media (max-width:700px){#pp-kartki{position:static;height:auto;display:flex;flex-direction:column;gap:14px;padding:0 16px 24px}" +
    "#pp-kartki .kt{position:relative;left:auto!important;top:auto!important;width:auto!important;height:auto!important;min-height:110px;transform:none!important;resize:none}" +
    "#pp-kartki .kt textarea{min-height:80px}.kt .kt-h button{opacity:1}.kt .kt-h{cursor:default}}";
  function styl() { if (document.getElementById("pp-nt-styl")) return; var s = document.createElement("style"); s.id = "pp-nt-styl"; s.textContent = CSS; document.head.appendChild(s); }

  // ---------- przycisk w pasku ----------
  function przycisk() {
    var r = document.querySelector("#pracawre-pasek .pp-r");
    if (!r) return false;
    if (r.querySelector(".pp-not")) return true;
    styl();
    var b = document.createElement("button");
    b.type = "button"; b.className = "pp-not"; b.title = "Notatnik (Alt+N)"; b.setAttribute("aria-pressed", "false");
    b.innerHTML = '📝<span class="pp-not-t">Notatnik</span>';
    b.addEventListener("click", function () { przelacz(); });
    r.insertBefore(b, r.querySelector(".pp-sam") || r.querySelector(".pp-konto"));
    return true;
  }

  // ---------- okno ----------
  function polozenie() {
    var z = czytaj(KL_OKNO) || {}, W = innerWidth, H = innerHeight;
    var w = Math.min(z.w || 760, W - 16), h = Math.min(z.h || 520, H - 58);
    var x = z.x == null ? W - w - 16 : z.x, y = z.y == null ? 50 : z.y;
    x = Math.min(Math.max(x, 80 - w), W - 80); y = Math.min(Math.max(y, 42), H - 44);
    return { x: x, y: y, w: w, h: h };
  }
  function zapamietaj(pola) { zapisz(KL_OKNO, Object.assign(czytaj(KL_OKNO) || {}, pola)); }
  function otworz() {
    if (!wlaczony) return;
    styl();
    if (!okno) zbuduj();
    okno.hidden = false;
    var p = polozenie();
    Object.assign(okno.style, { left: p.x + "px", top: p.y + "px", width: p.w + "px", height: p.h + "px" });
    zapamietaj({ otw: true });
    document.querySelectorAll(".pp-not").forEach(function (b) { b.setAttribute("aria-pressed", "true"); });
    laduj().then(function () {
      if (!S.id) { var l = widoczne(); if (l[0]) S.id = l[0].id; rysuj(); }
      var ta = okno.querySelector(".nt-t"); if (ta && !okno.contains(document.activeElement)) ta.focus({ preventScroll: true });
    });
  }
  function zamknij() {
    if (!okno || okno.hidden) return;
    wybierz(S.id); wyslijWszystko();
    okno.hidden = true; zapamietaj({ otw: false });
    document.querySelectorAll(".pp-not").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
  }
  function przelacz() { if (okno && !okno.hidden) zamknij(); else otworz(); }

  function zbuduj() {
    okno = document.createElement("div");
    okno.id = "pp-nt"; okno.setAttribute("role", "dialog"); okno.setAttribute("aria-label", "Notatnik"); okno.hidden = true;
    okno.innerHTML =
      '<div class="nt-h" title="Przeciągnij, żeby przesunąć"><b>📝 Notatnik</b><kbd>Alt+N</kbd><span class="nt-sp"></span>' +
      '<input class="nt-q" type="search" placeholder="Szukaj w notatkach" aria-label="Szukaj w notatkach">' +
      '<button type="button" class="nt-x" data-zw title="Zwiń (Esc)" aria-label="Zwiń notatnik">—</button></div>' +
      '<div class="nt-b"><div class="nt-kat"></div>' +
      '<div class="nt-lis"><div class="nt-lg"><button type="button" class="nt-nowa" data-nowa>+ Nowa notatka</button><select class="nt-kats" aria-label="Kategoria"></select></div><div class="nt-l"></div></div>' +
      '<div class="nt-ed"></div></div>';
    document.body.appendChild(okno);
    // przeciąganie za nagłówek
    var h = okno.querySelector(".nt-h");
    h.addEventListener("pointerdown", function (e) {
      if (e.button || e.target.closest("input,button") || innerWidth <= 600) return;
      var sx = e.clientX - okno.offsetLeft, sy = e.clientY - okno.offsetTop;
      h.setPointerCapture(e.pointerId);
      var ruch = function (ev) {
        var x = Math.min(Math.max(ev.clientX - sx, 80 - okno.offsetWidth), innerWidth - 80), y = Math.min(Math.max(ev.clientY - sy, 42), innerHeight - 44);
        okno.style.left = x + "px"; okno.style.top = y + "px";
      };
      var koniec = function () { h.removeEventListener("pointermove", ruch); h.removeEventListener("pointerup", koniec); zapamietaj({ x: okno.offsetLeft, y: okno.offsetTop }); };
      h.addEventListener("pointermove", ruch); h.addEventListener("pointerup", koniec);
    });
    // rozmiar: układ 1 / 2 / 3 kolumny i zapamiętanie
    var rzCzas = null;
    var uklad = function () {
      var w = okno.offsetWidth;
      okno.classList.toggle("w1", w < 430); okno.classList.toggle("w2", w >= 430 && w < 640);
    };
    if (window.ResizeObserver) new ResizeObserver(function () {
      if (okno.hidden) return; uklad();
      if (innerWidth > 600 && okno.offsetLeft + okno.offsetWidth > innerWidth - 4) okno.style.left = Math.max(4, innerWidth - okno.offsetWidth - 4) + "px";
      clearTimeout(rzCzas); rzCzas = setTimeout(function () { if (innerWidth > 600) zapamietaj({ w: okno.offsetWidth, h: okno.offsetHeight }); }, 300);
    }).observe(okno);
    uklad();
    okno.querySelector(".nt-q").addEventListener("input", function (e) { S.q = e.target.value; rysujListe(); });
    okno.addEventListener("click", klik);
    okno.addEventListener("change", zmiana);
    okno.addEventListener("focusout", function (e) {     // wyjście z pola nazwy (Enter, klik obok) – zapis, także bez zmiany
      var t = e.target; if (t.matches && t.matches("[data-kedyt]") && S.edKat === +t.dataset.kedyt) zmienNazwe(+t.dataset.kedyt, t.value);
    });
    okno.addEventListener("input", function (e) { if (e.target.classList.contains("nt-t") && S.id) zmien(S.id, { tresc: e.target.value }, "okno"); });
    okno.addEventListener("keydown", function (e) {
      if (e.target.matches(".nt-nk input")) {
        if (e.key === "Enter") { e.preventDefault(); e.target.blur(); }     // zapis w „change” – jedno miejsce
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); S.nowaKat = false; S.edKat = null; rysujKategorie(); }
      }
    });
  }
  function widoczne() {
    var q = bezOgonkow(S.q).split(/\s+/).filter(Boolean);
    return D.notatki.filter(function (n) {
      if (S.kat === "none" ? n.kategoria != null : typeof S.kat === "number" && n.kategoria !== S.kat) return false;
      if (S.przyp && !n.przypieta) return false;
      var t = bezOgonkow(n.tresc); return q.every(function (s) { return t.indexOf(s) >= 0; });
    });
  }
  function status(t, kl) { var s = okno && okno.querySelector(".nt-st"); if (s) { s.textContent = t; s.className = "nt-st " + (kl || ""); } }
  function rysuj() { if (!okno) return; rysujKategorie(); rysujListe(); rysujEdytor(); if (S.zarz) rysujZarzadzanie(); }
  function rysujKategorie() {
    var ile = function (f) { return D.notatki.filter(f).length; };
    var bez = ile(function (n) { return n.kategoria == null; });
    var h = '<button type="button" class="nt-c" data-k="all" aria-pressed="' + (S.kat === "all") + '">Wszystkie<i>' + D.notatki.length + "</i></button>" +
      D.kategorie.map(function (k) {
        if (S.edKat === k.id) return '<div class="nt-nk"><input data-kedyt="' + k.id + '" maxlength="40" value="' + esc(k.nazwa) + '" aria-label="Nowa nazwa kategorii"></div>';
        return '<button type="button" class="nt-c" title="Dwa kliknięcia – zmień nazwę" data-k="' + k.id + '" aria-pressed="' + (S.kat === k.id) + '"><span class="cd" style="background:' + esc(k.kolor) + '"></span>' +
          esc(k.nazwa) + "<i>" + ile(function (n) { return n.kategoria === k.id; }) + "</i></button>";
      }).join("") +
      (bez && D.kategorie.length ? '<button type="button" class="nt-c" data-k="none" aria-pressed="' + (S.kat === "none") + '"><span class="cd" style="background:var(--l)"></span>Bez kategorii<i>' + bez + "</i></button>" : "") +
      '<div class="nt-sep"></div>' +
      (S.nowaKat ? '<div class="nt-nk"><input maxlength="40" placeholder="Nazwa kategorii" aria-label="Nazwa nowej kategorii"></div>' : '<button type="button" class="nt-c z" data-nkat>+ Kategoria</button>') +
      '<button type="button" class="nt-c m" data-zarz>⚙ Zarządzaj kategoriami</button>' +
      '<div class="nt-sep"></div>' +
      '<label class="nt-c m"><input type="checkbox" data-przyp' + (S.przyp ? " checked" : "") + '><span>Tylko przypięte do: <b>Strona główna</b></span></label>' +
      (D.kosz ? '<button type="button" class="nt-c m" data-kosz>🗑 Kosz<i>' + D.kosz + "</i></button>" : "");
    okno.querySelector(".nt-kat").innerHTML = h;
    var nk = okno.querySelector(".nt-nk input"); if (nk) { nk.focus(); if (nk.dataset.kedyt) nk.select(); }
    okno.querySelector(".nt-kats").innerHTML = '<option value="all">Wszystkie kategorie</option>' +
      D.kategorie.map(function (k) { return '<option value="' + k.id + '"' + (S.kat === k.id ? " selected" : "") + ">" + esc(k.nazwa) + "</option>"; }).join("") +
      (bez && D.kategorie.length ? '<option value="none"' + (S.kat === "none" ? " selected" : "") + ">Bez kategorii</option>" : "");
  }
  function rysujListe() {
    if (!okno) return;
    var l = widoczne();
    okno.querySelector(".nt-l").innerHTML = l.length ? l.map(function (n) {
      var t = tytul(n), k = kategoria(n.kategoria);
      return '<button type="button" class="nt-n" data-n="' + n.id + '" aria-current="' + (n.id === S.id) + '"><b>' +
        (k ? '<span class="cd" style="background:' + esc(k.kolor) + '"></span>' : "") + (n.przypieta ? "📌 " : "") + "<span>" + esc(t.t) + "</span></b>" +
        (t.r ? '<span class="r">' + esc(t.r.slice(0, 120)) + "</span>" : "") + "<small>" + esc(kiedy(n.zmieniono)) + "</small></button>";
    }).join("") : '<div class="nt-pusto">' + (S.q ? "Nic nie znaleziono." : "Brak notatek.") + "</div>";
    var w = okno.querySelector(".nt-wyb");
    if (w && document.activeElement !== w) w.innerHTML = (S.id ? "" : '<option value="">— wybierz notatkę —</option>') +
      l.concat(S.id && l.indexOf(notatka(S.id)) < 0 && notatka(S.id) ? [notatka(S.id)] : []).map(function (n) {
        return '<option value="' + n.id + '"' + (n.id === S.id ? " selected" : "") + ">" + (n.przypieta ? "📌 " : "") + esc(tytul(n).t.slice(0, 60)) + "</option>";
      }).join("");
  }
  function rysujEdytor() {
    var ed = okno.querySelector(".nt-ed"), n = notatka(S.id);
    var gora = '<div class="nt-eh"><select class="nt-wyb" aria-label="Notatka"></select><button type="button" class="nt-pl" data-nowa title="Nowa notatka" aria-label="Nowa notatka">+</button>';
    if (!n) {
      ed.innerHTML = gora + '</div><div class="nt-zero"><div>Wybierz notatkę z listy albo<br><button type="button" class="nt-p" data-nowa style="margin-top:10px">+ Nowa notatka</button></div></div><div class="nt-s"><span class="nt-st"></span></div>';
      rysujListe(); return;
    }
    var ta = ed.querySelector(".nt-t");
    if (ta && ed.dataset.id === String(n.id)) {      // ta sama notatka – nie przerysowujemy pola, w którym ktoś pisze
      if (document.activeElement !== ta && ta.value !== n.tresc) ta.value = n.tresc;
      ed.querySelector(".nt-katn").innerHTML = opcjeKategorii(n);
      var pb = ed.querySelector("[data-pin]"); pb.setAttribute("aria-pressed", String(n.przypieta)); pb.textContent = n.przypieta ? "📌 Przypięta na stronie głównej" : "📌 Przypnij na stronie głównej";
      rysujListe(); return;
    }
    ed.dataset.id = n.id;
    ed.innerHTML = gora + '<select class="nt-katn" aria-label="Kategoria notatki">' + opcjeKategorii(n) + "</select></div>" +
      '<textarea class="nt-t" spellcheck="true" placeholder="Pisz albo wklej (Ctrl+V)…" aria-label="Treść notatki"></textarea>' +
      '<div class="nt-s"><button type="button" class="nt-p" data-pin aria-pressed="' + n.przypieta + '">' + (n.przypieta ? "📌 Przypięta na stronie głównej" : "📌 Przypnij na stronie głównej") + "</button>" +
      '<button type="button" class="nt-p" data-kop>⧉ Kopiuj</button><button type="button" class="nt-p" data-usun title="Usuń notatkę" aria-label="Usuń notatkę">🗑</button>' +
      '<span class="nt-st">' + (czekaZapis[n.id] ? "Zapisywanie…" : "✓ Zapisano · zapis automatyczny") + "</span></div>";
    ed.querySelector(".nt-t").value = n.tresc;
    rysujListe();
  }
  function opcjeKategorii(n) {
    return '<option value="">Bez kategorii</option>' + D.kategorie.map(function (k) {
      return '<option value="' + k.id + '"' + (n.kategoria === k.id ? " selected" : "") + ">● " + esc(k.nazwa) + "</option>";
    }).join("");
  }
  function rysujZarzadzanie() {
    var z = okno.querySelector(".nt-zarz");
    if (!z) { z = document.createElement("div"); z.className = "nt-zarz"; okno.appendChild(z); }
    if (S.kosz) {
      z.innerHTML = "<h3>🗑 Kosz</h3><p>Usunięte notatki – przez 30 dni możesz je przywrócić, potem znikają na dobre.</p>" +
        (S.kosz.length ? S.kosz.map(function (n) {
          return '<div class="nt-zr"><span style="flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis"><b>' + esc(tytul(n).t) + '</b> <small style="color:var(--m)">usunięta ' +
            esc(kiedy(n.usunieto)) + '</small></span><button type="button" class="nt-p" data-przywroc="' + n.id + '">↺ Przywróć</button></div>';
        }).join("") : '<p>Kosz jest pusty.</p>') +
        '<div class="nt-zs"><button type="button" class="nt-p" data-zarz-x>← Wróć</button></div>';
      return;
    }
    z.innerHTML = "<h3>Moje kategorie</h3><p>Tylko Twoje – nikt inny ich nie widzi. Usunięcie kategorii nie usuwa notatek (trafiają do „Bez kategorii”).</p>" +
      D.kategorie.map(function (k, i) {
        return '<div class="nt-zr" data-kid="' + k.id + '"><button type="button" class="kol" data-kol title="Zmień kolor" aria-label="Zmień kolor" style="background:' + esc(k.kolor) + '"></button>' +
          '<input value="' + esc(k.nazwa) + '" maxlength="40" aria-label="Nazwa kategorii" data-knaz>' +
          '<button type="button" class="m" data-gora title="W górę" aria-label="W górę"' + (i ? "" : " disabled") + ">↑</button>" +
          '<button type="button" class="m" data-dol title="W dół" aria-label="W dół"' + (i < D.kategorie.length - 1 ? "" : " disabled") + ">↓</button>" +
          '<button type="button" class="m" data-kusun title="Usuń kategorię" aria-label="Usuń kategorię">🗑</button></div>';
      }).join("") +
      '<div class="nt-zs"><button type="button" class="nt-p" data-zarz-nowa>+ Dodaj kategorię</button><span style="flex:1"></span><button type="button" class="nt-p" data-zarz-x aria-pressed="true">Gotowe</button></div>';
  }
  function dodajKategorie(nazwa) {
    nazwa = (nazwa || "").trim(); S.nowaKat = false;
    if (!nazwa) { rysujKategorie(); return Promise.resolve(); }
    return api("POST", "/kategorie", { nazwa: nazwa }).then(function (k) { D.kategorie.push(k); S.kat = k.id; rozeslij(); rysuj(); })
      .catch(function (e) { alert(e.message); rysujKategorie(); });
  }
  function zmienNazwe(id, nazwa) {
    nazwa = (nazwa || "").trim(); S.edKat = null;
    var k = kategoria(id);
    if (!k || !nazwa || nazwa === k.nazwa) { rysujKategorie(); return; }
    k.nazwa = nazwa; rysuj(); rysujKartki();
    api("PUT", "/kategorie/" + id, { nazwa: nazwa }).then(rozeslij).catch(function (e) { alert(e.message); laduj(); });
  }
  function kolejnosc(i, o) {
    var l = D.kategorie.slice(), j = i + o; if (j < 0 || j >= l.length) return;
    var t = l[i]; l[i] = l[j]; l[j] = t; D.kategorie = l; rysuj();
    api("PUT", "/kolejnosc", { kategorie: l.map(function (k) { return k.id; }) }).then(function () { rozeslij(); rysujKartki(); }).catch(function () {});
  }
  function klik(e) {
    var b = e.target.closest("button"); if (!b) return;
    var d = b.dataset;
    if ("zw" in d) zamknij();
    else if ("nowa" in d) nowa();
    else if (d.k) {
      // 12.11 (decyzja użytkownika): dwa szybkie kliknięcia w kategorię = zmiana nazwy w miejscu
      var teraz = Date.now(), kid = d.k === "all" || d.k === "none" ? d.k : +d.k;
      if (typeof kid === "number" && S.ostKlik && S.ostKlik.k === kid && teraz - S.ostKlik.t < 450) { S.ostKlik = null; S.edKat = kid; rysujKategorie(); return; }
      S.ostKlik = { k: kid, t: teraz };
      if (S.kat !== kid) { S.kat = kid; rysuj(); }
    }
    else if (d.n) wybierz(+d.n);
    else if ("nkat" in d) { S.nowaKat = true; rysujKategorie(); }
    else if ("zarz" in d) { S.zarz = true; S.kosz = null; rysujZarzadzanie(); }
    else if ("kosz" in d) { S.zarz = true; api("GET", "/kosz").then(function (k) { S.kosz = k.notatki; rysujZarzadzanie(); }); }
    else if (d.przywroc) api("POST", "/kosz/" + d.przywroc).then(function (n) { S.kosz = S.kosz.filter(function (x) { return x.id !== n.id; }); D.kosz--; D.notatki.unshift(n); rozeslij(); rysuj(); });
    else if ("zarzX" in d) { S.zarz = false; S.kosz = null; var z = okno.querySelector(".nt-zarz"); if (z) z.remove(); rysuj(); }
    else if ("zarzNowa" in d) { var nazwa = prompt("Nazwa nowej kategorii:"); if (nazwa) dodajKategorie(nazwa); }
    else if ("pin" in d) przypnij(S.id, !notatka(S.id).przypieta);
    else if ("kop" in d) kopiuj(notatka(S.id).tresc, b);
    else if ("usun" in d) usun(S.id);
    else {
      var r = b.closest("[data-kid]"); if (!r) return;
      var id = +r.dataset.kid, k = kategoria(id), i = D.kategorie.indexOf(k);
      if ("kol" in d) {
        var kol = D.kolory[(D.kolory.indexOf(k.kolor) + 1) % D.kolory.length];
        k.kolor = kol; rysuj(); rysujKartki();
        api("PUT", "/kategorie/" + id, { kolor: kol }).then(rozeslij).catch(function () {});
      } else if ("gora" in d) kolejnosc(i, -1);
      else if ("dol" in d) kolejnosc(i, 1);
      else if ("kusun" in d) {
        var ile = D.notatki.filter(function (n) { return n.kategoria === id; }).length;
        if (!confirm("Usunąć kategorię „" + k.nazwa + "”?" + (ile ? "\n" + ile + " notat. zostanie bez kategorii." : ""))) return;
        api("DELETE", "/kategorie/" + id).then(function () {
          D.kategorie = D.kategorie.filter(function (x) { return x.id !== id; });
          D.notatki.forEach(function (n) { if (n.kategoria === id) n.kategoria = null; });
          if (S.kat === id) S.kat = "all"; rozeslij(); rysuj(); rysujKartki();
        });
      }
    }
  }
  function zmiana(e) {
    var t = e.target;
    if (t.matches("[data-przyp]")) { S.przyp = t.checked; rysujListe(); }
    else if (t.matches(".nt-kats")) { S.kat = t.value === "all" || t.value === "none" ? t.value : +t.value; rysuj(); }
    else if (t.matches(".nt-wyb")) { if (t.value) wybierz(+t.value); }
    else if (t.matches(".nt-katn")) zmien(S.id, { kategoria: t.value ? +t.value : null });
    else if (t.matches("[data-knaz]")) {
      var id = +t.closest("[data-kid]").dataset.kid, n = t.value.trim();
      if (!n) { t.value = kategoria(id).nazwa; return; }
      api("PUT", "/kategorie/" + id, { nazwa: n }).then(function (k) { Object.assign(kategoria(id), k); rozeslij(); rysujKategorie(); rysujEdytor(); rysujKartki(); })
        .catch(function (er) { alert(er.message); });
    } else if (t.matches("[data-kedyt]")) { if (S.edKat === +t.dataset.kedyt) zmienNazwe(+t.dataset.kedyt, t.value); }
    else if (t.matches(".nt-nk input")) dodajKategorie(t.value);
  }

  // ---------- karteczki na stronie głównej ----------
  function naGlownej() { return location.pathname === "/" || location.pathname === "/index.html"; }
  function jasny(kolor) { return "color-mix(in srgb, " + kolor + " 55%, #fffdf6)"; }
  function rysujKartki() {
    if (!naGlownej() || !wlaczony) return;
    var przyp = D.notatki.filter(function (n) { return n.przypieta; });
    if (!warstwa) {
      if (!przyp.length) return;
      styl();
      warstwa = document.createElement("div"); warstwa.id = "pp-kartki";
      document.body.appendChild(warstwa);
      warstwa.addEventListener("input", function (e) { var k = e.target.closest(".kt"); if (k) zmien(+k.dataset.id, { tresc: e.target.value }, "kartka"); });
      warstwa.addEventListener("click", function (e) {
        var b = e.target.closest("button"), k = e.target.closest(".kt"); if (!b || !k) return;
        var id = +k.dataset.id;
        if ("ed" in b.dataset) { S.id = id; otworz(); rysuj(); }
        else if ("kop" in b.dataset) kopiuj(notatka(id).tresc, null);
        else if ("odp" in b.dataset) zmien(id, { przypieta: false });
      });
      warstwa.addEventListener("pointerdown", ciagnij);
      if (window.ResizeObserver) warstwa._ro = new ResizeObserver(function (wp) {
        wp.forEach(function (w) {
          var el = w.target, n = notatka(+el.dataset.id); if (!n || innerWidth <= 700) return;
          var nw = el.offsetWidth, nh = el.offsetHeight;
          if (Math.abs(nw - (n.poz.w || 0)) < 2 && Math.abs(nh - (n.poz.h || 0)) < 2) return;
          clearTimeout(el._rz); el._rz = setTimeout(function () { n.poz.w = nw; n.poz.h = nh; api("PUT", "/notatki/" + n.id, { poz: { w: nw, h: nh } }).then(rozeslij).catch(function () {}); }, 400);
        });
      });
    }
    var W = document.documentElement.clientWidth, jest = {};
    przyp.forEach(function (n) {
      jest[n.id] = true;
      var el = warstwa.querySelector('.kt[data-id="' + n.id + '"]'), k = kategoria(n.kategoria), kol = k ? k.kolor : "#e9c46a", p = n.poz || {};
      if (!el) {
        el = document.createElement("div"); el.className = "kt"; el.dataset.id = n.id;
        el.innerHTML = '<div class="kt-h" title="Przeciągnij, żeby przesunąć"><span></span><button type="button" data-ed title="Otwórz w notatniku" aria-label="Otwórz w notatniku">✎</button>' +
          '<button type="button" data-kop title="Kopiuj" aria-label="Kopiuj">⧉</button><button type="button" data-odp title="Odepnij (notatka zostaje w notatniku)" aria-label="Odepnij">✕</button></div><textarea aria-label="Karteczka"></textarea>';
        warstwa.appendChild(el);
        if (warstwa._ro) warstwa._ro.observe(el);
      }
      el.style.left = Math.max(0, Math.min(Math.round((p.x || 0) * W), W - (p.w || 240))) + "px"; el.style.top = (p.y || 120) + "px";
      if (!el._rz) { el.style.width = (p.w || 240) + "px"; el.style.height = (p.h || 190) + "px"; }
      el.style.zIndex = p.z || 1; el.style.background = jasny(kol); el.style.setProperty("--pin", kol);
      el.style.transform = "rotate(" + (((n.id % 5) - 2) * 0.6) + "deg)";
      el.querySelector(".kt-h span").textContent = k ? k.nazwa : "Notatka";
      var ta = el.querySelector("textarea"); if (document.activeElement !== ta && ta.value !== n.tresc) ta.value = n.tresc;
    });
    warstwa.querySelectorAll(".kt").forEach(function (el) { if (!jest[el.dataset.id]) el.remove(); });
    if (innerWidth <= 700) {                         // telefon: karteczki jedna pod drugą pod pulpitem
      var m = document.querySelector("main"); if (m && warstwa.previousElementSibling !== m) m.insertAdjacentElement("afterend", warstwa);
    }
  }
  function ciagnij(e) {
    var el = e.target.closest(".kt"); if (!el || e.button || innerWidth <= 700) return;
    var n = notatka(+el.dataset.id); if (!n) return;
    var maxZ = Math.max.apply(null, D.notatki.map(function (x) { return (x.poz && x.poz.z) || 0; }));
    if ((n.poz.z || 0) < maxZ) { n.poz.z = maxZ + 1; el.style.zIndex = n.poz.z; api("PUT", "/notatki/" + n.id, { poz: { z: n.poz.z } }).catch(function () {}); }
    var h = e.target.closest(".kt-h"); if (!h || e.target.closest("button")) return;
    e.preventDefault();
    var sx = e.pageX - el.offsetLeft, sy = e.pageY - el.offsetTop, W = document.documentElement.clientWidth;
    el.classList.add("ciag"); h.setPointerCapture(e.pointerId);
    var ruch = function (ev) {
      el.style.left = Math.min(Math.max(ev.pageX - sx, 0), W - el.offsetWidth) + "px";
      el.style.top = Math.max(ev.pageY - sy, 46) + "px";
    };
    var koniec = function () {
      h.removeEventListener("pointermove", ruch); h.removeEventListener("pointerup", koniec); el.classList.remove("ciag");
      n.poz.x = Math.round(el.offsetLeft / W * 10000) / 10000; n.poz.y = el.offsetTop;
      api("PUT", "/notatki/" + n.id, { poz: { x: n.poz.x, y: n.poz.y } }).then(rozeslij).catch(function () {});
    };
    h.addEventListener("pointermove", ruch); h.addEventListener("pointerup", koniec);
  }
  var rzStrony = null;
  window.addEventListener("resize", function () { clearTimeout(rzStrony); rzStrony = setTimeout(rysujKartki, 150); });

  // ---------- klawisze ----------
  window.addEventListener("keydown", function (e) {
    if (!wlaczony) return;
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === "KeyN") { e.preventDefault(); przelacz(); return; }
    if (e.key !== "Escape" || e.defaultPrevented || !okno || okno.hidden || !okno.contains(document.activeElement)) return;
    e.preventDefault(); e.stopPropagation();
    if (S.zarz) { S.zarz = false; S.kosz = null; var z = okno.querySelector(".nt-zarz"); if (z) z.remove(); rysuj(); return; }
    zamknij();
  }, true);

  // ---------- włączanie / wyłączanie (Mój profil) ----------
  function wylacz() {
    wlaczony = false; wyslijWszystko();
    if (okno) { okno.remove(); okno = null; }
    if (warstwa) { warstwa.remove(); warstwa = null; }
    document.querySelectorAll(".pp-not").forEach(function (b) { b.remove(); });
  }
  function wlacz() {
    wlaczony = true;
    var n = 0;
    (function sprobuj() { if (!przycisk() && ++n < 40) setTimeout(sprobuj, 250); })();
    if ((czytaj(KL_OKNO) || {}).otw && innerWidth > 600) otworz();
    else if (naGlownej()) laduj();
  }

  window.PracawreNotatnik = { otworz: otworz, zamknij: zamknij, przelacz: przelacz, wlacz: wlacz, wylacz: wylacz, przycisk: przycisk };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wlacz); else wlacz();
})();
