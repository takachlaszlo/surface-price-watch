# Surface Pro 11 árfigyelő

Naponta egyszer lekérdezi a beállított svájci, magyar, osztrák és német forrásokat,
kikeresi a **Microsoft Surface Pro 11 – Intel Core Ultra 5 / 16 GB RAM / 256 GB SSD**
ajánlatokat, elmenti az ártörténetet, és e-mailben elküldi országonként a 3 legolcsóbb
ajánlatot (árral, kereskedővel, közvetlen linkkel, az előző naphoz képesti változással),
az ártrendet és a források állapotát.

A program Synology NAS-on, a Container Manager „Projekt” funkciójával fut.

## Hogyan működik

* **Ár-összehasonlító oldalak** adják a lefedettség nagy részét. Ezek adatbázisában több
  száz (a Geizhalsnál és az idealónál több ezer) kereskedő szerepel; a program a figyelt
  SKU terméklapját kéri le, amelyen az összes, a terméket éppen áruló kereskedő ára egyszerre
  megérkezik (2026-09-30-án kb. 46 német, 16 osztrák, 11 svájci kereskedő).
* **Közvetlen webshopok** a `jsonld` adapterrel adhatók hozzá: bármely termékoldal,
  amely schema.org JSON-LD adatot tesz közzé (a legtöbb modern webshop), egyetlen URL
  megadásával figyelhető.
* **Pontos termékazonosítás**: az illesztés elsősorban gyártói cikkszám alapján történik
  (EP2-20112 platina / EP2-20095 fekete a DE-AT-CH piacon, EP2-20849 / EP2-20845
  Magyarországon), a címalapú szabályok kizárják a Snapdragon, Ultra 7, 32 GB, 512 GB,
  Surface Pro 10/12, használt/B-Ware és tartozék találatokat. A nem rendelhető ajánlatok
  („nicht lieferbar”, „auf Anfrage”) nem kerülnek a rangsorba.

### Figyelt források (config.yaml)

| Ország | Forrás | Mit ad |
|---|---|---|
| AT + DE | `geizhals_at` – geizhals.at | a legteljesebb osztrák lista + Ausztriába szállító német boltok |
| DE + AT | `heise_preisvergleich` – preisvergleich.heise.de | a Geizhals-adatbázis német nézete, 40+ német kereskedő (galaxus.de is) |
| AT | `idealo_at` – idealo.at | osztrák boltok (cyberport.at, galaxus.at, e-tec …) |
| DE | `idealo_de`, `billiger_de`, `hardwareschotte_de` | további német ár-összehasonlítók (a 3 napnál régebbi hardwareschotte-árak kiszűrve) |
| CH | `toppreise` – toppreise.ch | svájci kereskedők, **köztük a Galaxus és a digitec** (közvetlen Galaxus-linkkel) |
| CH | `shops_ch` – brack.ch, techstudio.ch | közvetlen bolti terméklapok (tartalék) |
| HU | `olcsobbat` – olcsobbat.hu | magyar ár-összehasonlító (iPon stb.) |
| HU | `shops_hu` – notebook.hu, bluechip.hu, emag.hu | közvetlen bolti terméklapok |
| AT | `shops_at` – e-tec.at | közvetlen bolti terméklap (tartalék) |
| DE/AT/CH | `microsoft_store` | hivatalos Microsoft Store katalógus-API (ma nem árulja ezt a konfigurációt) |

### Átvételi lehetőségek

A top 3 ajánlat alatt az „Átvétel” sor mutatja, hogyan juthatsz a készülékhez:

* **házhozszállítás** – vagy „csak üzletben vehető át” (bolti áras ajánlat);
* **személyes átvétel** – a bolt saját üzletében/átvevőpontján, a helyszínnel, ha a forrás közli;
* **csomagpont** – „igen” (a forrás vagy a bolt oldala kimondja, pl. Foxpost, PickMup, PickPoint),
  „lehetséges” (a bolt olyan futárszolgálattal szállít, amelynek van csomagpont-hálózata –
  hogy oda kérhető-e, a bolt pénztáránál derül ki), vagy „nincs adat”.

Honnan jön az adat: a Geizhals / heise sorai kiírják a személyes átvételt és azt, ha a bolt csak
belföldre szállít; az idealo a futárszolgálatokat; az olcsóbbat.hu a szállítási módokat. Ha egy
bolt több forrásban szerepel, az adatok összeadódnak. Amit a források nem közölnek, azt a
`config.yaml` `merchant_delivery:` listája pótolja a boltok saját szállítási oldalai alapján
(forráshivatkozással) – ez bővíthető. „Nincs adat” azt jelenti, hogy egyik forrás sem közli.

### Kézzel rögzített árak (Galaxus, digitec)

A galaxus.ch és a digitec.ch minden automatikus látogatót „Bist du ein Roboter?” ellenőrzésre
irányít; ezt a program nem kerüli meg. Amíg a Toppreise (amely a Galaxus árát is listázza) nem
érhető el, a böngészőben megnézett ár a projektmappa `data/kezi_arak.yaml` fájljába írható, és
7 napig részt vesz a rangsorban („kézi adat, dátum” jelöléssel):

```yaml
- merchant: Galaxus
  country: CH
  price: 1499
  url: https://www.galaxus.ch/de/s1/product/54161673
  variant: Platin
  date: 2026-10-01
```

**Amit a program nem tud lekérdezni**, mert az oldal bot-védelme elutasítja az automatikus
klienst: galaxus.ch / digitec.ch közvetlenül (captcha-átirányítás – az áruk a Toppreise-en
keresztül érkezik), arukereso.hu, argep.hu, alza.hu, mediamarkt, cyberport.at közvetlenül.
A Geizhals és a Toppreise is adhat időnként elutasítást (főleg sok lekérés után); ilyenkor
az adott napon a többi forrás pótolja, és a jelentés „Források állapota” része mutatja.
* **Udvarias, tisztességes lekérdezés**: a program saját nevén mutatkozik be
  (`SurfacePriceWatch/1.0`), tiszteletben tartja a `robots.txt`-t, legalább 3 másodpercet
  vár két lekérés között ugyanazon a kiszolgálón, és **nem kerüli meg a bot-védelmet**.
  Ha egy oldal elutasítja az automatikus lekérdezést (403, „Just a moment…” ellenőrző
  oldal), a jelentésben „letiltva (bot-védelem)” állapottal jelenik meg, és a program
  nem próbálkozik trükkökkel. Az ilyen oldalak (pl. a galaxus.ch közvetlenül) árai az
  ár-összehasonlítókon keresztül érkeznek.
* Az ártörténet SQLite adatbázisban gyűlik (`data/pricewatch.sqlite3`), így a jelentés
  mutatja az előző napi árat, a 30 napos minimumot és az eddigi legalacsonyabb árat.
* Az átváltás az EKB napi referencia-árfolyamával történik (csak az országok közötti
  összehasonlításhoz; a rangsor mindig a helyi árat használja).

## Telepítés a Synology NAS-ra

Ugyanaz a minta, mint a `hbd-inventory-watcher` projektnél: nincs képfordítás, a konténer a
kész `python:3.12-slim-bookworm` képből indul, induláskor letölti ezt a repót a GitHub-ról
(`main` ág), telepíti a függőségeket, majd a napi ütemezőt futtatja.

1. Hozd létre a NAS-on a `docker/surface-price-watch` mappát, benne egy üres `data`
   almappával, és másold bele a [`compose.yaml`](compose.yaml) fájlt.
   **Container Manager → Projekt → Létrehozás**: név `surface-price-watch`, útvonal
   `/volume1/docker/surface-price-watch` – a varázsló felismeri a meglévő `compose.yaml`-t.
2. Az `SMTP_PASSWORD` sorba írd be a `technikai` fiók jelszavát (a repóban csak helykitöltő
   van). A többi beállítás (`RUN_AT`, `MAIL_TO` stb.) ugyanott, az `environment:` alatt van.
3. **Első próba**: állítsd `RUN_ON_START: "true"`-ra – a konténer indulásakor azonnal lefut
   egy kör és megjön az első levél. Utána állítsd vissza `"false"`-ra (különben minden
   újraindításkor küld levelet).
4. A konténer naplója (Container Manager → Tároló → surface-price-watch → Napló)
   forrásonként mutatja, mi történt. Az ártörténet a projektmappa `data` almappájában
   marad meg (`pricewatch.sqlite3`, `last_report.html`, `pricewatch.log`).

**Frissítés / forráslista módosítása**: a `config/config.yaml` (és a program) a GitHub-repóból
jön, ezért módosítás után elég a változást a `main` ágra feltölteni és a projektet
újraindítani.

### Levelezés (Synology MailPlus Server)

A beállítás megegyezik a hbd-inventory-watcherével: `mail.home.arpa:587`, STARTTLS,
hitelesítés a `technikai` felhasználóval, a NAS saját aláírású tanúsítványa miatt
tanúsítvány-ellenőrzés nélkül (`SMTP_VERIFY_TLS: "false"`). A `mail.home.arpa` nevet az
`extra_hosts` sor köti a NAS címéhez (192.168.1.168).

Próbalevél (Container Manager → Tároló → surface-price-watch → Művelet → Terminál megnyitása,
vagy SSH-ból `docker exec`):

```bash
docker exec -it surface-price-watch sh -c "cd /app && python -m pricewatch test-mail"
```

## Parancsok

| Parancs | Mit csinál |
|---|---|
| `python -m pricewatch daemon` | folyamatos futás, napi ütemezés (a konténer alapparancsa) |
| `python -m pricewatch run` | egyszeri futás most, levéllel |
| `python -m pricewatch run --no-mail` | egyszeri futás, csak a `data/last_report.html` készül el |
| `python -m pricewatch run --only geizhals_at,toppreise` | csak a felsorolt források |
| `python -m pricewatch check <forrás-id>` | egy forrás ajánlatainak kiírása (hibakereséshez) |
| `python -m pricewatch sources` | a beállított források listája |
| `python -m pricewatch test-mail` | próbalevél |

A konténerben: `docker exec -it surface-price-watch sh -c "cd /app && python -m pricewatch check toppreise"`.

## A config.yaml felépítése

```yaml
product:
  name: "…"                 # a jelentés címe
  must_match: [ … ]         # regexek – MINDEGYIKNEK illeszkednie kell a címre
  must_not_match: [ … ]     # regexek – bármelyik illeszkedése kizárja az ajánlatot
  mpns: [ … ]               # ismert gyártói cikkszámok: ezek önmagukban is elfogadják az ajánlatot
  price_limits:             # pénznemenként ésszerű sáv – ami kívül esik, az hibás találat
    CHF: [700, 2500]
report:
  countries: [CH, HU, AT, DE]
  top_n: 3
  distinct_merchants: true  # egy kereskedő csak egyszer szerepeljen a top 3-ban
  rank_by: price            # price = termékár, total = ár + szállítás (ha ismert)
http:
  min_delay_seconds: 3
  respect_robots: true
sources:
  - id: geizhals_at         # egyedi azonosító (a jelentésben is ez látszik)
    adapter: geizhals       # melyik adapter dolgozza fel
    enabled: true
    options: { … }          # adapterfüggő (URL-ek, ország stb.)
```

Új közvetlen webshop hozzáadása: keresd meg a shop terméklapját, és vedd fel a
`jsonld` adapter `pages` listájába (`url`, `country`, `merchant`). A `check` paranccsal
azonnal ellenőrizhető, hogy a shop ad-e árat.

## Fejlesztés, tesztek

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt pytest
.venv/Scripts/python -m pytest -q
PRICEWATCH_CONFIG=config/config.yaml PRICEWATCH_DATA=data python -m pricewatch run --no-mail
```
