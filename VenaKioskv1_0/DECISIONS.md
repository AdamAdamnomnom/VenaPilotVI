# Decyzje architektoniczne — VENA Kiosk

Ten plik odpowiada na „dlaczego tak?” i „czego nie zmieniać bez powodu”. Alternatywy, które odrzucono, są tu po to, żeby nie wracać do nich w kolejnym refaktorze.

## Produkcja to jeden plik `VenaKioskv1_2.py`

**Decyzja:** nie dzielić aplikacji na pakiet `vena/` w tej fazie.

**Dlaczego:** działający kiosk zależy od ścisłej kolejności X11 (settle okna, stow, AlwaysOnTop, CDP, Openbox). Podział na moduły łatwo psuje importy, cykl życia `QTimer` i to, kto trzyma `Display()`.

**Alternatywa:** pakiet z `chromium.py`, `x11.py`, `ui.py`. Odrzucona do czasu smoke-testu na Futro i osobnej decyzji.

**Nie zmieniaj:** nazwy pliku produkcyjnego — [`vena-watchdog.sh`](vena-watchdog.sh) i Openbox `class="VenaKioskv1_2.py"` są do niej przywiązane.

## Chromium `--app`, nie WebEngine / nie oficjalne SDK

**Decyzja:** Spotify i YouTube to osobne procesy Chromium z `--app=URL`.

**Dlaczego:** pełny player webowy (DRM, login, aktualizacje serwisu) bez utrzymywania natywnego klienta. Osobne profile = osobne sesje.

**Alternatywy:** Qt WebEngine (inni GPU/sandbox, trudniejszy kiosk na AMD); Spotify Connect / API (brak pełnego UI web); electron (cięższy).

**Nie zmieniaj** bez testu na Futro: `--ozone-platform=x11 --disable-vulkan --disable-gpu --no-sandbox`. `--disable-gpu` obchodzi `VK_ERROR_INCOMPATIBLE_DRIVER` / Exit 1 na Radeon. `--no-sandbox` jest świadomym kompromisem bezpieczeństwa na koncie `kiosk`.

## Stow poza ekran, nie unmap i nie kill przy POWRÓT

**Decyzja:** `hide()` przesuwa okno na `x=1088`. Proces żyje.

**Dlaczego:** unmap/map psuje Chromium; kill przy POWRÓT gubi muzykę i wymusza zimny start.

**Nie zmieniaj** semantyki POWRÓT vs `shutdown()`. `shutdown()` tylko przy wyjściu z aplikacji.

## python-xlib zamiast wmctrl / xdotool

**Decyzja:** geometria i fokus przez `X11WindowController` + `dpy.sync()`.

**Dlaczego:** równoległe CLI X11 wyścigały się; szukanie po tytule było kruche. Teraz: `--class=` + `_NET_WM_PID`.

**Nie zmieniaj** na Wayland — stos kiosku jest X11-only (Openbox).

## Klawiatura wbudowana (PyQt + XTest), nie matchbox/onboard

**Decyzja:** własny panel, `WA_ShowWithoutActivating` / NoFocus, znaki przez XTest.

**Dlaczego:** matchbox/onboard padały przez `WindowStaysOnTopHint` i utratę fokusu. Chromium odrzuca syntetyczne `XSendEvent`.

**Nie zmieniaj** na systemową klawiaturę bez testu logowania Spotify.

## Openbox: margines 0, nie 168

**Decyzja:** sidebar 168 px rysuje VENA; Openbox ma `<left>0</left>`.

**Dlaczego:** `<left>168</left>` wypycha **całe** okno VENA w prawo (czarny pasek). Chromium pozycjonuje aplikacja (`SPOTIFY_X=168`).

## Dwa Chromium zawsze preloadowane

**Decyzja:** Spotify po 1,5 s, YouTube po 3,5 s, oba ukryte.

**Dlaczego:** zimny start web-appa na thin clencie jest wolny. Koszt: RAM/CPU nawet gdy kafelki nieużywane.

**Nie wyłączaj preloadu** bez decyzji produktowej („szybszy boot vs. pierwszy Play”).

## Efekty: LADSPA mbeq, bez podbijania basu

**Decyzja:** `module-ladspa-sink` + 15 pasm; pasma ~50–220 Hz zawsze ≤ 0 dB.

**Dlaczego:** na tym sprzęcie nie ma ALSA Bass/Treble; boost basu clipuje wzmacniacz. Charakter presetów = cięcie innych pasm.

**Nie ładuj** drugiego łańcucha EQ / nie ustawiaj dodatniego basu bez pomiaru na fizycznym głośniku.

## PIN serwisowy w kodzie

**Decyzja:** `DEV_PIN = "1234"`, 7 kliknięć w etykietę wersji w **MENU** (`Vena Pilot V v1.2`). Sidebar „VENA PILOT V” nie jest podpięty.

**Dlaczego:** fizyczny kiosk, brak klawiatury serwisowej przy starcie. To **nie** jest model bezpieczeństwa sieciowego.

**Ryzyko:** fizyczny dostęp = reboot / CLI. Zmiana PINu to zmiana w kodzie; limit prób nie jest zaimplementowany (osobne zadanie).

## Jeden watchdog shell + jeden watchdog w Pythonie

**Decyzja:** `vena-watchdog.sh` trzyma proces Pythona; `ChromiumAppWindowManager._watchdog_tick` trzyma Chromium (max 3 restarty).

**Dlaczego:** crash UI ≠ crash Chromium. Wyjście serwisowe musi umieć zatrzymać pętlę (`data/no_autorestart`).

**Nie usuwaj** flagi `no_autorestart` — bez niej nie da się wyjść do CLI.

## Świadomie odrzucone

- **GNOME / pełny desktop** — za ciężkie, kolizja WM.
- **Ukrycie kursora przez wyłączenie pointera** — psuło dotyk.
- **Szukanie okna po tytule** — niestabilne.
- **Profil Chromium w `/tmp`** — login ginął po reboocie.
- **Kasowanie starych `VenaKioskv1_0.py` / `v1_1` z Gita** — zostają w `archive/legacy/` i w tagu `v1.2-baseline`.
