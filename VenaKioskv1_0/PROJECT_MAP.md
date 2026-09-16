# Mapa projektu — VENA Kiosk

Repozytorium Git: katalog nadrzędny z `VenaKioskv1_0.slnx`. **Kod kiosku** leży w tym katalogu (obok tego pliku).

Entrypoint produkcji: [`VenaKioskv1_2.py`](VenaKioskv1_2.py) — `if __name__ == "__main__"`.

## Pliki aktywne

| Ścieżka | Odpowiedzialność |
|---------|------------------|
| [`VenaKioskv1_2.py`](VenaKioskv1_2.py) | Cała aplikacja: UI, Chromium, X11, audio, Wi-Fi, serwis |
| [`vena-watchdog.sh`](vena-watchdog.sh) | Pętla: restart Pythona po crashu; stop przez `data/no_autorestart` |
| [`requirements.txt`](requirements.txt) | `PyQt6>=6.5`, `python-xlib>=0.33` |
| [`VenaKioskv1_0.pyproj`](VenaKioskv1_0.pyproj) | Projekt Visual Studio — StartupFile = `VenaKioskv1_2.py` |
| [`../VenaKioskv1_0.slnx`](../VenaKioskv1_0.slnx) | Solution VS (jeden projekt) |

## Dokumentacja

| Ścieżka | Odpowiedzialność |
|---------|------------------|
| [`README.md`](README.md) | Start: cel, sprzęt, uruchomienie, linki |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Warstwy, przepływ, timery, integracje |
| [`DECISIONS.md`](DECISIONS.md) | Dlaczego tak; czego nie ruszać |
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | Zasady zmian, debug, testy |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | Diagnoza i naprawa na maszynie |
| [`naLinux.md`](naLinux.md) | Instalacja Debiana + Openbox od zera |
| [`TODO.md`](TODO.md) | Otwarty backlog (nie historia zrobionych rzeczy) |

## Archiwum (nie produkcja)

| Ścieżka | Odpowiedzialność |
|---------|------------------|
| [`archive/legacy/README.md`](archive/legacy/README.md) | Jak odzyskać stare wersje |
| [`archive/legacy/VenaKioskv1_0.py`](archive/legacy/VenaKioskv1_0.py) | Baseline |
| [`archive/legacy/VenaKioskv1_1.py`](archive/legacy/VenaKioskv1_1.py) | v1.1 (łatki niezawodności) |
| [`archive/legacy/_probe_kiosk.sh`](archive/legacy/_probe_kiosk.sh) | Sonda XFixes hide_cursor |
| [`docs/archive/ANALIZA_BLEDOW_v1.1.md`](docs/archive/ANALIZA_BLEDOW_v1.1.md) | Audyt 2026-07-27 dla v1.1 |

Powrót do drzewa **sprzed** docs/archive (stare `.py` z powrotem obok produkcji): `git checkout v1.2-baseline`.  
Na aktualnym `main` stare implementacje są w `archive/legacy/` — nie trzeba zjeżdżać z gałęzi.

Repozytorium: [AdamAdamnomnom/VenaPilotVI](https://github.com/AdamAdamnomnom/VenaPilotVI) (`main`).

## Tworzy aplikacja (nie w Git)

| Ścieżka na kiosku | Znaczenie |
|-------------------|-----------|
| `data/spotify_profile/` | Sesja Chromium Spotify |
| `data/youtube_profile/` | Sesja Chromium YouTube |
| `data/no_autorestart` | Stop `vena-watchdog.sh` |
| `data/restore_networking` | Włącz NM po poprzednim poweroff |
| `logs/vena.log` | Log aplikacji |
| `logs/chromium.log` | Log obu Chromium (wspólny plik) |
| `logs/vena_stdout.log` | stdout/stderr Pythona, gdy startuje `vena-watchdog.sh` |

Na Futro katalog aplikacji to `/home/kiosk/vena/` (kopia `VenaKioskv1_2.py` + `vena-watchdog.sh`).

## Klasy w `VenaKioskv1_2.py`

Przybliżone numery linii — szukaj po nazwie klasy, nie kotwicz logiki do numeru.

| Klasa / symbol | ~linia | Odpowiedzialność | Zależności |
|----------------|--------|------------------|------------|
| stałe (`SCREEN_*`, URL, porty CDP, PIN) | 73 | Geometria kiosku, hosty, ścieżki `data/`/`logs/` | — |
| `_setup_file_logging` | 36 | `logs/vena.log` | logging |
| `HardwareAudioMixer` | 213 | Głośność ALSA | `amixer` |
| `WifiNetwork` | 265 | Rekord SSID / sygnał / security | — |
| `WifiManager` | 310 | Skan, connect, delete profilu key-mgmt | `nmcli` |
| `_WifiWorker` | 736 | `QThread` dla nmcli | `WifiManager` |
| `X11WindowController` | 779 | Geometria, stow, focus, fullscreen, PID | python-xlib |
| `_harden_chromium_profile` | 1076 | Preferences: bez password manager UI | JSON profilu |
| `_install_invisible_cursor` / `_apply_x11_blank_cursor` | 1129 | Ukrycie kursora bez blokady dotyku | Qt + X11 |
| `_restore_networking_if_needed` | 1185 | `nmcli networking on` po poweroff | `nmcli` |
| `ChromiumController` | 1253 | Popen, log file, SIGTERM/KILL grupy | Chromium |
| `ChromiumAppWindowManager` | 1333 | **Jądro kiosku:** preload, show/hide, CDP, watchdog | Controller + X11 |
| `X11KeyInjector` | 2587 | XTest + schowek dla znaków poza US | XTest |
| `SoftKeyboardPanel` / `VirtualKeyboard` | 2700 / 2980 | Widget klawiatury | Qt |
| `OnScreenKeyboard` | 3083 | Pokaz/ukryj, `WM_CLASS=VenaKeyboard` | panel + injector |
| `TouchSlider` | 3121 | Suwak pod palec | Qt |
| `PowerOffConfirmDialog` | 3147 | Slider potwierdzenia wyłączenia | Qt |
| `PinPadDialog` | 3291 | PIN 4 cyfry | `DEV_PIN` |
| `WifiPage` | 3461 | UI listy sieci, hasło, shutdown workera | `WifiManager` |
| `TileButton` | 3926 | Kafelki home | Qt |
| `AudioEffectsPage` | 3987 | Presety EQ, pactl, D-Bus update pasm | PulseAudio, LADSPA |
| `KioskMainWindow` | 4429 | Składanie UI, nawigacja, serwis, health | wszystko powyżej |

Alias: `SpotifyWindowManager = ChromiumAppWindowManager` (zgodność nazw).

## Kolejność startu w `main`

1. `makedirs` `logs/` + `data/`
2. `_setup_file_logging`
3. `_restore_networking_if_needed`
4. `QApplication` + ukrycie kursora
5. `HardwareAudioMixer` + `KioskMainWindow`
6. `aboutToQuit` → `shutdown_web_apps`
7. `show` + `_pin_kiosk_geometry` (i dogrywki 0,4 / 2 / 5 s)

## Czego tu nie ma

- Testów automatycznych
- Systemd unit `vena-kiosk.service` (start jest przez getty + `startx` + Openbox autostart)
- Drugiego entrypointu — VS i watchdog mają celować w `VenaKioskv1_2.py`
