# Architektura — VENA Kiosk

Aplikacja produkcyjna to **jeden plik** [`VenaKioskv1_2.py`](VenaKioskv1_2.py) (~5900 linii). Świadomie nie jest podzielona na pakiet — podział Chromium/X11 to główne źródło regresji. Zobacz [`DECISIONS.md`](DECISIONS.md).

## Cel systemu

Dostarczyć użytkownikowi imprezowemu (dotyk, 1024×768) Spotify i YouTube jak „aplikacje”, bez chrome przeglądarki, z głośnością, Wi-Fi i EQ — na thin clencie bez pełnego pulpitu.

## Warstwy od zasilania do UI

```
zasilanie
  → getty autologin kiosk (tty1)
    → ~/.bash_profile → startx
      → ~/.xinitrc → pulseaudio + openbox-session
        → openbox/autostart → vena-watchdog.sh
          → python3 VenaKioskv1_2.py
            → KioskMainWindow (AlwaysOnTop)
            → Chromium ×2 (VenaSpotify, VenaYouTube)
```

Watchdog: [`vena-watchdog.sh`](vena-watchdog.sh). Celowe wyjście serwisowe tworzy `data/no_autorestart` — pętla się kończy. Po reboocie flaga jest kasowana.

## Moduły w jednym pliku

```
KioskMainWindow (PyQt, AlwaysOnTop)
├── Sidebar 168 px (głośność, POWRÓT, klawiatura, zegar, ONLINE)
└── QStackedWidget: Home / MENU / placeholder / Wi-Fi / Efekty

ChromiumAppWindowManager × 2
├── ChromiumController     — Popen, PID, logi, killpg
└── X11WindowController    — move / stow / focus / fullscreen (python-xlib)

OnScreenKeyboard → X11KeyInjector (XTest) → fokus do aktywnego Chromium
HardwareAudioMixer → amixer
WifiManager + _WifiWorker → nmcli (wątek, UI nie zamarza)
AudioEffectsPage → pactl + module-ladspa-sink (mbeq)
```

Wejście: `if __name__ == "__main__"` na końcu `VenaKioskv1_2.py`.

## Przepływ: Spotify / YouTube

1. Po starcie UI: preload Spotify (~1,5 s), YouTube (~3,5 s) — okna **poza ekranem** (`APP_STOW_X = 1088`).
2. Klik kafelka: druga aplikacja jest chowana **bez pauzy**; okno VENA zwęża się do 168 px (`_enter_sidebar_only_mode`).
3. Chromium jest `map` + `configure` na `x=168, y=-8` (crop paska chrome).
4. Pauza drugiego playera dopiero gdy aktywny **faktycznie gra** (`_watch_active_media` + CDP `is_media_playing`).
5. **POWRÓT** = `hide()` (stow), nie `shutdown()`. Muzyka idzie dalej.
6. `shutdown()` tylko przy wyjściu z VENA / poweroff / `aboutToQuit`.

Identyfikacja okien: `--class=VenaSpotify` / `VenaYouTube`, potem `_NET_WM_PID`, fallback `WM_CLASS`. Nie szukać po tytule.

## Stow vs unmap

Chromium źle znosi X11 unmap/map. Ukrywanie = przesunięcie okna poza ekran, proces żyje. Watchdog procesu (10 s) działa też gdy okno jest schowane.

## CDP (Chrome DevTools Protocol)

Porty tylko na localhost: Spotify **9333**, YouTube **9334**.

Służy do:

- blokady wyjścia poza dozwolone hosty (reklamy → powrót na URL startowy)
- pauzy / play / detekcji odtwarzania
- wyjścia z HTML5 fullscreen (sidebar musi zostać)
- pętli nawigacji: 5 resetów w 30 s → twardy restart procesu

Implementacja WebSocket jest ręczna (stdlib), wołana z **wątku UI**. To ryzyko zacięcia sidebara — opisane w [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md), nie ruszane w tej fazie.

## Timery (KioskMainWindow + manager)

| Timer | Interwał | Rola |
|-------|----------|------|
| zegar | 1 s | `%H:%M` |
| ONLINE | 30 s | HTTP connectivitycheck / TCP 8.8.8.8 |
| health | 60 s | dysk, stan Chromium, ponowny preload po limicie restartów |
| kursor X11 | 400 ms | Chromium przywraca kursor — ponowne ukrycie |
| media watch | 1,5 s | pauza drugiego playera gdy aktywny gra |
| Chromium watchdog | 10 s | restart procesu (max 3, potem health znów preloaduje) |
| policy CDP | 2 s | enforce URL + popupy (także po preloadzie, w tle) |
| layout | 600 ms | geometria / fullscreen, tylko gdy okno widoczne |
| debounce głośności | 35 ms | nie młóć `amixer` |

## Integracje

**X11 / Openbox.** VENA zakłada geometrię 1024×768 i `DISPLAY`. Openbox: marginesy **0** (nie 168 — to wypycha całe VENA w prawo). Reguły `class="VenaKioskv1_2.py"`, `VenaSpotify`, `VenaYouTube` — bez dekoracji. Szczegóły w [`naLinux.md`](naLinux.md).

**PyQt6.** Overlay AlwaysOnTop, Frameless. W trybie web-app okno ma szerokość 168 px, stack stron jest ukryty.

**ALSA.** `HardwareAudioMixer` → `amixer sset Master N%`. Odczyt z timeoutem 2 s. Set jest fire-and-forget `Popen`.

**PulseAudio.** Chromium bez PA często milczy mimo działającego suwaka. Efekty: `pactl load-module module-ladspa-sink` (`mbeq_1197`). Pasma basu nigdy > 0 dB (headroom wzmacniacza).

**Touch.** Brak osobnego stosu dotyku — Qt + sterownik X. Niewidoczny kursor (Qt override + X11 pixmap + próba XFixes). Ukrycie kursora **nie może** wyłączać zdarzeń pointer (wcześniejsza próba psuła dotyk).

**Sieć.** `nmcli` przez `WifiManager`. Hasło Wi-Fi trafia do argv (ryzyko `/proc/cmdline`). Łączenie w `QThread`.

## Runtime na dysku

Tworzone przy starcie, nie commitować:

- `data/spotify_profile/`, `data/youtube_profile/` — cookies/sesje
- `data/no_autorestart` — stop watchdoga po wyjściu serwisowym
- `data/restore_networking` — po poweroff włącz sieć przy następnym starcie
- `logs/vena.log` — aplikacja (bez rotacji)
- `logs/chromium.log` — stdout/stderr Chromium (rotacja ~5 MiB przy starcie procesu)
- `logs/vena_stdout.log` — stdout/stderr procesu Pythona, gdy startuje watchdog (nie przy ręcznym `python3`)

## Zależności

**Python:** PyQt6, python-xlib.

**System:** chromium, amixer, pactl, nmcli, xorg, openbox, sudo reboot/poweroff.
