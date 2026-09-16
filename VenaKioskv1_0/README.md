# VENA Kiosk (Pilot V)

Aplikacja kioskowa do sterowania urządzeniem audio/wideo:
sidebar + kafelki, pełny ekran 1024×768, X11 + Openbox.

Aktualna wersja produkcyjna: **`VenaKioskv1_2.py`** (wcześniej `VenaKioskv1_0.py` / `v1_1`).

---

## Terminal produkcyjny (obecny sprzęt)

Od lipca 2026 produkcja nie jest już na Casio — działa na thin clencie:

| | |
|--|--|
| **Sprzęt** | **Fujitsu Futro S930** (thin client, AMD GX / Radeon) |
| **Wyświetlacz** | 1024×768 (DisplayPort; wymuszane w sesji X) |
| **OS** | Debian 13 (Trixie), bez pełnego desktopu — X11 + Openbox |
| **Użytkownik** | `kiosk` — autologin / sesja X (`vena-kiosk.service`) |
| **Aplikacja** | `/home/kiosk/vena/VenaKioskv1_2.py` |
| **Sieć** | Ethernet (wbudowany) + **Wi‑Fi USB TP-Link TL-WN725N** (RTL8188EUS, `rtl8xxxu`) |
| **Audio** | PulseAudio + ALSA (`amixer`) |
| **BIOS** | *Power Failure Recovery → Power On* (auto-start po podaniu prądu) |

Instalacja / odtworzenie od zera: **`naLinux.md`**.  
SSH: użytkownik `kiosk` (IP z DHCP — Ethernet i Wi‑Fi mogą mieć osobne adresy; w trybie serwisowym w MENU widać host + IP).

---

## Co robi

| Moduł | Jak działa |
|-------|------------|
| **Spotify** | Chromium `--app=https://open.spotify.com`, okno X11 obok sidebara |
| **YouTube** | Ten sam wzorzec (`--app=https://www.youtube.com`) |
| **MENU** | Panel systemowy + Wi-Fi (`nmcli` / NetworkManager) |
| **Efekty** | Placeholder |
| **Głośność** | Suwak → ALSA (`amixer`), z debounce |
| **Klawiatura** | Wbudowana (PyQt + XTest) — do logowania w Chromium |
| **Tryb serwisowy** | 7× klik w logo VENA → PIN `1234` → RESET / wyjście do CLI |

**POWRÓT** tylko chowa okno Chromium (proces żyje w tle — muzyka/wideo nie ginie).
Sesje przeglądarki: `data/spotify_profile`, `data/youtube_profile`.
Logi Chromium: `logs/chromium.log`.

---

## Stack

- **Python 3.11+**
- **PyQt6** — UI kiosku
- **python-xlib** — pozycjonowanie okien Chromium + wstrzykiwanie klawiszy (XTest)
- **Chromium** — Spotify / YouTube w trybie `--app`
- **ALSA** (`amixer`) + zwykle **PulseAudio** (audio w Chromium)
- **NetworkManager** (`nmcli`) — lista Wi-Fi w MENU
- **Openbox** + **X11** (Wayland nieobsługiwany)

Zależności Pythona: `requirements.txt` (`PyQt6`, `python-xlib`).

---

## Architektura (w skrócie)

```
KioskMainWindow (PyQt, AlwaysOnTop)
├── Sidebar 168 px (głośność, POWRÓT, klawiatura, zegar)
└── Stack: Home / MENU / Wi-Fi / placeholder

ChromiumAppWindowManager × 2 (Spotify, YouTube)
├── ChromiumController          — proces + profil + logi
└── X11WindowController         — move / stow / focus po WM_CLASS

VirtualKeyboard → X11KeyInjector (XTest) → fokus do aktywnego Chromium
HardwareAudioMixer → amixer
WifiManager → nmcli
```

Przy starcie: preload Spotify (~1,5 s), potem YouTube (~3,5 s) — ukryte w tle.
W trybie web-app okno VENA zwęża się do sidebara (168 px), żeby nie przykrywać Chromium.

---

## Pliki w repo

| Plik | Rola |
|------|------|
| `VenaKioskv1_2.py` | Aplikacja (produkcja na Futro) |
| `vena-watchdog.sh` | Pętla restartu UI (Openbox autostart) |
| `VenaKioskv1_1.py` / `VenaKioskv1_0.py` | Starsze wersje |
| `requirements.txt` | Zależności Python |
| `TODO.md` | Rzeczy do zrobienia |
| `naLinux.md` | Instalacja i konfiguracja na Debian (kiosk) |
| `ANALIZA_BLEDOW.md` | Znane problemy / ryzyka |

---

## Szybki start (dev)

```bash
python3 VenaKioskv1_2.py
```

Na Futro / Debianie — pełna checklista w **`naLinux.md`**.
