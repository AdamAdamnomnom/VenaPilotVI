# VENA Kiosk (Pilot V)

Kiosk audio/wideo na thin clencie: sidebar + kafelki, pełny ekran **1024×768**, **X11 + Openbox**.

To nie jest natywny client Spotify ani aplikacja webowa. VENA to overlay PyQt, który trzyma dwa procesy Chromium (`--app`) obok paska bocznego i steruje głośnością, Wi-Fi oraz efektami dźwięku.

**Produkcja:** tylko [`VenaKioskv1_2.py`](VenaKioskv1_2.py). Starsze pliki są w [`archive/legacy/`](archive/legacy/README.md).

---

## Sprzęt produkcyjny

| | |
|--|--|
| **Terminal** | Fujitsu Futro S930 (AMD GX / Radeon) |
| **Ekran** | 1024×768 (DisplayPort; wymuszane w sesji X) |
| **OS** | Debian 13 (Trixie), bez pełnego pulpitu — X11 + Openbox |
| **Użytkownik** | `kiosk` — autologin tty1 → `startx` → Openbox |
| **Aplikacja** | `/home/kiosk/vena/VenaKioskv1_2.py` |
| **Sieć** | Ethernet + Wi-Fi USB TP-Link TL-WN725N (`rtl8xxxu`) |
| **Audio** | PulseAudio + ALSA (`amixer`); efekty przez LADSPA `mbeq` |
| **BIOS** | Power Failure Recovery → Power On |

Pełna instalacja od czystego Debiana: **[`naLinux.md`](naLinux.md)**.

---

## Funkcje

- **Spotify / YouTube** — Chromium `--app`, okno X11 obok sidebara 168 px
- **POWRÓT** — chowa Chromium poza ekran; proces żyje, muzyka/wideo nie ginie
- **MENU** — Wi-Fi (`nmcli`), wyłączenie głośnika (poweroff)
- **Efekty** — presety Party / Disco / Bass / Chill / Normal / Off (PulseAudio + LADSPA)
- **Głośność** — suwak → `amixer` (debounce)
- **Klawiatura ekranowa** — PyQt + XTest (logowanie w Chromium)
- **Tryb serwisowy** — MENU → **7×** klik w etykietę wersji **`Vena Pilot V v1.2`** → PIN `1234` → RESET / wyjście do CLI / logi. Napis na sidebarze („VENA PILOT V”) **nie** otwiera serwisu.

Sesje przeglądarki: `data/spotify_profile`, `data/youtube_profile`.  
Logi: `logs/vena.log` (aplikacja), `logs/chromium.log` (oba Chromium), `logs/vena_stdout.log` (stdout/stderr z [`vena-watchdog.sh`](vena-watchdog.sh); tylko gdy start jest przez watchdog).

---

## Wymagania

**Python:** 3.11+, pakiety w [`requirements.txt`](requirements.txt) (`PyQt6`, `python-xlib`). Na Debianie produkcyjnym lepiej `apt install python3-pyqt6 python3-xlib`.

**System (kiosk):** X11, Openbox, Chromium, ALSA, PulseAudio, NetworkManager, `sudo` NOPASSWD na `reboot`/`poweroff`. Wayland / GNOME / KDE — nieobsługiwane.

---

## Uruchamianie

Na kiosku (po `startx` / Openbox):

```bash
cd /home/kiosk/vena
python3 VenaKioskv1_2.py
```

Produkcja startuje przez `~/.config/openbox/autostart` → [`vena-watchdog.sh`](vena-watchdog.sh).

Dev (Windows: UI częściowo działa; `amixer` / Chromium `--app` / reboot — nie):

```bash
python VenaKioskv1_2.py
```

---

## Dokumentacja

| Dokument | Po co |
|----------|--------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Jak system jest złożony, przepływ danych, timery |
| [`DECISIONS.md`](DECISIONS.md) | Dlaczego tak — i czego nie zmieniać bez przyczyny |
| [`PROJECT_MAP.md`](PROJECT_MAP.md) | Mapa plików i klas w `VenaKioskv1_2.py` |
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | Zasady pracy, debug, smoke-test |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | Objaw → przyczyna → diagnoza → naprawa |
| [`naLinux.md`](naLinux.md) | Instalacja i odtworzenie maszyny od zera |
| [`TODO.md`](TODO.md) | Otwarty backlog |

Zacznij od tego README, potem `ARCHITECTURE.md` i `DECISIONS.md`.

Smoke na urządzeniu (Futro) jest w [`DEVELOPMENT.md`](DEVELOPMENT.md) — Windows/Linux-dev **nie** zastępuje tego testu.

---

## Git

Remote: [github.com/AdamAdamnomnom/VenaPilotVI](https://github.com/AdamAdamnomnom/VenaPilotVI), gałąź `main`.

- **`v1.2-baseline`** — tag na pierwszym commicie: sam runtime (`VenaKioskv1_2.py`, watchdog, stare pliki jeszcze obok siebie). Służy do odzyskania aplikacji sprzed porządku dokumentacji.
- Commity **po** tym tagu dodają docs/archive; **nie zmieniają** `VenaKioskv1_2.py` ani `vena-watchdog.sh`, dopóki osobny etap tego nie zrobi.
- Clone zawsze z `main`. `git checkout v1.2-baseline` cofa też dokumentację i wrzuca stare `.py` z powrotem do katalogu aplikacji.
