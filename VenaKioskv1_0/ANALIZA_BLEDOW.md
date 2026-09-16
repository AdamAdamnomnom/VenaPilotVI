# Analiza błędów — VENA Kiosk

Przegląd kodu (2026-07-27). **`VenaKioskv1_1.py`** = gałąź z łatami niezawodności;
`VenaKioskv1_0.py` = poprzedni baseline bez tych zmian.

## Krytyczne

- Chromium startuje z `--no-sandbox` — Spotify/YouTube bez izolacji procesu;
  zewnętrzna treść WWW ma łatwiejszą drogę do konta `kiosk` i profili sesji
- PIN serwisowy (`DEV_PIN = "1234"`) jest w kodzie i w dokumentacji; brak limitu
  prób i opóźnienia — fizyczny dostęp do ekranu = tryb serwisowy / reboot / wyjście do CLI

## Wysokie

- hasło Wi-Fi trafia do argumentów `nmcli … password …` — widoczne w `ps` /
  `/proc/.../cmdline` przez czas łączenia
- Spotify/YouTube: ukrywanie/przywracanie i audio wymagają smoke-testu na Casio
  (X11 + Openbox + PulseAudio)

### Naprawione w `VenaKioskv1_1.py` (2026-07-27)
- ~~Chromium bez cleanup przy wyjściu~~ → `shutdown()` + `aboutToQuit` / `closeEvent`
- ~~orphan po `WM_CLASS` / konflikt profilu~~ → `_kill_orphan_chromium()` przed launch;
  `_find_window()` najpierw PID, potem klasa
- ~~`chromium.log` bez limitu~~ → rotacja przy >5 MiB → `chromium.log.1`
- ~~odczyt ALSA bez timeoutu~~ → `amixer sget` z `timeout=2`
- ~~watchdog bez limitu~~ → max 3 restarty + `try/except`; klik kafelka resetuje licznik

## Średnie

- ~~wątek Wi-Fi bez ścieżki shutdown / crash po ODŚWIEŻ~~ — naprawione w v1_1:
  bezpieczny cykl `_WifiWorker` (bez parenta, null po `finished`, `wait` przy wyjściu);
  crash wynikał z `isRunning()` na obiekcie po `deleteLater`
- `_check_reboot_started()` po 2,5 s zawsze pokazuje „Reboot nie wystartował”,
  nawet gdy reboot już startuje (fałszywy alarm dla operatora)
- XTest / fokus: przy wyścigu z Openboxem klawisze (w tym hasło) mogą trafić
  do złego okna; znaki nie-ASCII idą przez schowek systemowy
- status `● ONLINE` jest stały — nie używa `active_ssid()` / realnej łączności
- stała geometria 1024×768 + założenie X11/Openbox (margines 168 px) —
  brak walidacji przy starcie
- Chromium preloadowany zawsze (Spotify ~1,5 s, YouTube ~3,5 s) — RAM/CPU
  nawet bez użycia kafelków
- animacja „shake” PIN (`QPropertyAnimation`) może nie być widoczna w niektórych
  warunkach okna dialogowego
- profile `data/spotify_profile` / `data/youtube_profile` bez jawnych uprawnień
  katalogu — cookies/sesje obok kodu aplikacji
- Efekty: tylko placeholder („Moduł w budowie”)
- zależności w `requirements.txt` bez pinowanych wersji; brak testów automatycznych

## Niskie

- narzędzia (Chromium, `amixer`, `nmcli`) sprawdzane dopiero przy użyciu, nie przy starcie
- Windows-dev: UI częściowo działa, ale ścieżki Linux (reboot, amixer) są mylące
- `TODO.md` / checklista Casio nadal otwarte (weryfikacja Play, PulseAudio, sudoers, Openbox)

---

### Rozwiązane wcześniej (nadal w v1_0 i v1_1)

- ~~równoległe polecenia X11 (`wmctrl`/`xdotool`)~~ → `python-xlib` + `dpy.sync()`
- ~~wyszukiwanie okna po tytule~~ → `WM_CLASS` (`VenaSpotify` / `VenaYouTube`)
- ~~cichy crash Chromium~~ → logi w `logs/chromium.log` + flagi Vulkan/X11
- ~~zimny start Spotify~~ → preload ukryty po starcie VENA
- ~~migotanie przy wielokrotnym kliknięciu~~ → flaga `_launching`
- ~~wiele procesów `amixer` przy suwaku~~ → debounce `VOLUME_DEBOUNCE_MS` (180 ms)
- ~~sesja Spotify w `/tmp` ginie po reboocie~~ → profile w `data/…` (przeżywają restart)
- ~~PIN automatycznie zamyka aplikację~~ → PIN tylko otwiera tryb serwisowy;
  RESET / wyjście wymagają osobnego kliknięcia
- ~~YouTube „nie działa” (brak modułu)~~ → ten sam wzorzec co Spotify (`ChromiumAppWindowManager`)
- ~~README nieaktualny~~ → zgodny ze stackiem i architekturą (2026-07)
