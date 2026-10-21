# pracawre.com: jedna domena, kilka podstron

| Adres | Co | Gdzie jest kod |
|---|---|---|
| `https://pracawre.com/` | strona startowa: kafelki DoneHome i WRE Nieruchomości | `portal/site/index.html` (to repo) |
| `https://pracawre.com/radar/` | Radar działek (DoneHome) | to repo |
| `https://pracawre.com/radar/metabase/` | Metabase (analizy radaru) | to repo |
| `https://pracawre.com/umowy/` | Generator umów (WRE Nieruchomości) | osobny projekt |
| `https://pracawre.com/oauth2/…` | logowanie Google (wspólne dla wszystkich) | `docker-compose.google.yml` |

Wszystko stoi na jednym VPS (187.77.108.209) za Traefikiem z HTTPS (Let's Encrypt).

## Logowanie (część wspólna)

- **oauth2-proxy** w trybie forwardAuth: middleware Traefika `lmi-google`.
  - Wpuszcza tylko konta Google z domeny firmy (`LMI_EMAIL_DOMAIN`).
  - Ciasteczko `_radar_auth` jest na całą domenę, więc jedno logowanie wystarcza do wszystkich podstron.
- **Aplikacja dostaje e-mail zalogowanego w nagłówku `X-Auth-Request-Email`.**
  - Traefik nadpisuje ten nagłówek, więc przeglądarka nie może go podrobić.
  - Uprawnienia (np. kto jest administratorem) sprawdza serwer aplikacji na podstawie tego e-maila, nigdy przeglądarka.
- **Wylogowanie:** `/oauth2/sign_out?rd=%2F`.

## Jak podpiąć nową podstronę (np. generator umów pod `/umowy`)

Kontener aplikacji w tym samym `docker compose` (albo osobnym, na tym samym serwerze) z etykietami:

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.umowy.rule=Host(`pracawre.com`) && (Path(`/umowy`) || PathPrefix(`/umowy/`))
  - traefik.http.routers.umowy.entrypoints=websecure
  - traefik.http.routers.umowy.tls.certresolver=letsencrypt
  - traefik.http.routers.umowy.middlewares=lmi-google,lmi-headers,umowy-slash,umowy-strip
  - traefik.http.routers.umowy.service=umowy
  - traefik.http.services.umowy.loadbalancer.server.port=<port aplikacji>
  - traefik.http.middlewares.umowy-slash.redirectregex.regex=^(https?://[^/]+/umowy)$$
  - traefik.http.middlewares.umowy-slash.redirectregex.replacement=$${1}/
  - traefik.http.middlewares.umowy-strip.stripprefix.prefixes=/umowy
```

Wymagania wobec aplikacji:
- adresy w stronie **względne** (`api/...`, nie `/api/...`), bo strona żyje pod `/umowy/`;
- tożsamość z nagłówka `X-Auth-Request-Email`, bez własnego logowania;
- środowisko Traefika: tryb sieci host, a middleware `lmi-google` i `lmi-headers` są zdefiniowane w projekcie radaru (`docker-compose.google.yml`, `docker-compose.web.yml`), więc projekt radaru musi być uruchomiony.

Kafelek na stronie startowej sam pokazuje „wkrótce”, dopóki pod `/umowy/` nic nie odpowiada.

## Przełączenie radaru na podstronę (jednorazowo)

W `/opt/lmi/.env`:
```
LMI_DOMAIN=pracawre.com
LMI_BASE_PATH=/radar
COMPOSE_FILE=docker-compose.yml:docker-compose.web.yml:docker-compose.google.yml:docker-compose.subpath.yml:docker-compose.portal.yml
```
potem `docker compose up -d` (web, metabase, portal, oauth2-proxy).

DoneHome ma później trafić na osobną domenę. Radar przeniesie się wtedy przez zmianę `LMI_DOMAIN` i `LMI_BASE_PATH` (albo usunięcie `docker-compose.subpath.yml`), a z `portal/site/index.html` usuwa się sekcję DoneHome.
