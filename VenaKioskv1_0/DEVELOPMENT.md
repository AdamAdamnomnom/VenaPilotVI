# Rozwój — VENA Kiosk

Ten projekt jest **kioskiem produkcyjnym**. Stabilność na Futro jest ważniejsza niż czystość kodu. Zasady poniżej są dla człowieka i dla AI.

## Jak zacząć

1. [`README.md`](README.md) — co to jest i jak odpalić.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — jak elementy współpracują.
3. [`DECISIONS.md`](DECISIONS.md) — czego nie ruszać bez powodu.
4. [`PROJECT_MAP.md`](PROJECT_MAP.md) — gdzie jest która klasa.

Produkcja: **tylko** `VenaKioskv1_2.py`. Stare implementacje: [`archive/legacy/`](archive/legacy/README.md) albo tag `v1.2-baseline`.

## Zasady zmian

- Nie poświęcaj działającego zachowania dla „ładniejszego” kodu.
- Nie dziel `VenaKioskv1_2.py` na pakiet bez osobnej decyzji i testu na kiosku.
- Nie zmieniaj publicznych metod `ChromiumAppWindowManager` (`preload`, `show`, `hide`, `shutdown`, `reset_to_home`, pauza/play) bez sprawdzenia wszystkich wywołań w `KioskMainWindow`.
- Nie usuwaj kodu, bo „wygląda na martwy” — najpierw grep w całym repo (w tym `vena-watchdog.sh` i `naLinux.md`).
- Nie zmieniaj nazwy `VenaKioskv1_2.py` — Openbox i watchdog od niej zależą.
- Flagi Chromium, geometria 1024×768, stow vs unmap, margines Openbox = 0: patrz DECISIONS.
- PIN, `--no-sandbox`, hasło Wi-Fi w argv: znane ryzyka, nie „naprawiaj” przy okazji innego PR-a.
- Małe, logiczne commity. Bez `reset --hard` / rebase niszczącego historię. Tag `v1.2-baseline` zostaje.

## Środowisko

| Gdzie | Co działa |
|-------|-----------|
| Futro / Debian + X11 + Openbox | pełny kiosk |
| Linux z X11 (dev) | UI + przy szczęściu Chromium |
| Windows | częściowy podgląd UI; ALSA, nmcli, reboot, `--app` — nie |

Na Debianie produkcyjnym: pakiety apt (`python3-pyqt6`, `python3-xlib`), nie venv — mniej problemów z pluginami Qt.

## Debugowanie

Logi na kiosku (`/home/kiosk/vena/`):

```bash
tail -f logs/vena.log
tail -f logs/chromium.log
tail -f logs/vena_stdout.log   # stdout z vena-watchdog.sh
```

Tryb serwisowy: **MENU** → 7× klik w **`Vena Pilot V v1.2`** → PIN. Pokazuje ogon logów, CPU/RAM, stan Chromium. `vena_stdout.log` powstaje tylko gdy proces startuje **watchdog** (Openbox autostart), nie przy ręcznym `python3 VenaKioskv1_2.py`.

Przydatne komendy systemowe: w [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) i [`naLinux.md`](naLinux.md) §15.

Nie polegaj na `print`. `logger.info` / `warning` ląduje w `vena.log`. Chromium bez przekierowania stderr umierało po cichu (AMDGPU) — nie odłączaj `chromium.log`.

## Testowanie

**Automatyczne testy: brak.** Nie twierdź, że kiosk działa, jeśli nie sprawdziłeś na sprzęcie albo przynajmniej składni.

Przed commitem (dev):

```bash
python3 -m py_compile VenaKioskv1_2.py
sh -n vena-watchdog.sh
```

Na Windows (jeśli jest interpreter):

```bash
python -m py_compile VenaKioskv1_2.py
```

### Smoke na Futro (krytyczna ścieżka)

Tego **nie zastępuje** Windows ani sam `py_compile`. Po wgraniu `VenaKioskv1_2.py` (+ watchdog, jeśli ruszany):

1. Reboot → autologin → sidebar 1024×768, pozycja (0,0).
2. Preload: po kilku sekundach dwa procesy Chromium (okna poza ekranem).
3. Spotify: okno obok sidebara, Play ma dźwięk, suwak rusza ALSA.
4. Wejście w YouTube **nie** ucina od razu Spotify; pauza gdy YT faktycznie gra.
5. POWRÓT: home, muzyka dalej.
6. MENU → Wi-Fi: lista, łączenie.
7. EFEKTY: preset zmienia barwę, Off = 0%.
8. Serwis: MENU → 7× **`Vena Pilot V v1.2`** → PIN → RESET (`sudo -n reboot`) oraz wyjście CLI (`data/no_autorestart`).
9. Po rebootcie Spotify nadal zalogowane (`data/spotify_profile`).
10. Poweroff z MENU + sieć wraca przy następnym starcie.
11. Dłuższy bieg (godziny): czy sidebar zacina się przy słabej sieci (CDP/ONLINE na wątku UI — znane ryzyko, osobne zadanie).

Zmiany X11/CDP/flag Chromium **bez** punktów 1–9 nie są „gotowe”.

## Typowe pułapki przy rozwoju

- Edycja na Windows + wgranie tylko `.py` bez `vena-watchdog.sh` — OK dla logiki UI; nie zmieniaj nazwy pliku.
- Test UI na Windows nie wykryje wyścigu Openbox vs `move_and_resize`.
- CDP na wątku UI: dodatkowy `urlopen` w timerze może zaciąć sidebar. Nie dokładaj kolejnych synchronicznych wywołań CDP „bo szybko”.
- Nowy `X11WindowController()` w pętli / timerze otwiera kolejne `Display()` — używaj istniejącej instancji (znane ryzyko w `_pin_kiosk_geometry`).
- `pgrep` w watchdogu łapie `VenaKioskv1_2.py` — nie zmieniaj shebangu/nazwy bez poprawki skryptu.

## Git

- Remote: `https://github.com/AdamAdamnomnom/VenaPilotVI.git`, gałąź `main`.
- Tag **`v1.2-baseline`**: pierwszy commit (runtime v1.2). Nie zawiera późniejszej dokumentacji ani `archive/legacy/`.
- `main` po tagu: docs + archiwum starych `.py`. Runtime (`VenaKioskv1_2.py`, `vena-watchdog.sh`) zostaje na tagu, dopóki nie ma osobnego commita kodu.
- `git checkout v1.2-baseline` przywraca też **stary układ katalogów** (v0/v1 obok produkcji). Do samej starej aplikacji wystarczy `archive/legacy/` na `main`.
- Nie force-push do `main`. Nie `reset --hard` na współdzielonej historii.
- Profile `data/` i `logs/` (w tym `vena_stdout.log`) są w `.gitignore`.
