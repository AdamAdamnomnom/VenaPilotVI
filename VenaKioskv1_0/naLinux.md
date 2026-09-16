# VENA Kiosk — pełna instalacja od czystego Debiana

Instrukcja odtworzenia maszyny kioskowej **od zera**: instalator Debiana → pakiety → pliki konfiguracyjne → autostart → weryfikacja.


| Założenie   | Wartość                                                  |
| ----------- | -------------------------------------------------------- |
| OS          | Debian 12 (Bookworm) lub nowszy — **nie Ubuntu Desktop** |
| Wyświetlacz | **1024×768** (tak jest zakodowane w aplikacji)           |
| Sesja       | **X11** + **Openbox** (Wayland = nie działa)             |
| Użytkownik  | `kiosk` (bez uprawnień root na co dzień)                 |
| Aplikacja   | `VenaKioskv1_2.py` (+ `vena-watchdog.sh`)                 |
| Python      | 3.11+                                                    |


---

## Spis treści

1. [Instalator Debiana (krok po kroku)](#1-instalator-debiana-krok-po-kroku)
2. [Pierwsze logowanie i aktualizacja](#2-pierwsze-logowanie-i-aktualizacja)
3. [Pakiety systemowe](#3-pakiety-systemowe)
4. [Użytkownik](#4-użytkownik-kiosk-i-grupy) `kiosk` [i grupy](#4-użytkownik-kiosk-i-grupy)
5. [X11 + Openbox — pliki do utworzenia](#5-x11--openbox--pliki-do-utworzenia)
6. [Autologowanie i start X przy bootowaniu](#6-autologowanie-i-start-x-przy-bootowaniu)
7. [Audio (PulseAudio + ALSA)](#7-audio-pulseaudio--alsa)
8. [Wi-Fi (NetworkManager)](#8-wi-fi-networkmanager)
9. [Sudoers — RESET bez hasła](#9-sudoers--reset-bez-hasła)
10. [Skopiowanie aplikacji VENA](#10-skopiowanie-aplikacji-vena)
11. [Autostart VENA w Openbox](#11-autostart-vena-w-openbox)
12. [Uruchomienie ręczne (test)](#12-uruchomienie-ręczne-test)
13. [Checklista weryfikacji](#13-checklista-weryfikacji)
14. [Tryb serwisowy](#14-tryb-serwisowy)
15. [Diagnostyka](#15-diagnostyka)
16. [Mapa plików (co gdzie leży)](#16-mapa-plików-co-gdzie-leży)

---



## 1. Instalator Debiana (krok po kroku)

Przygotuj: pendrive z **debian-*-netinst.iso** (amd64), docelowy komputer/Casio.

### 1.1 Boot

1. Włóż pendrive, wejdź w BIOS/UEFI → boot z USB.
2. W menu instalatora wybierz **Install** (tekstowy) albo **Graphical install** — oba są OK; poniżej opis pod wersję tekstową / graficzną (ekrany te same).



### 1.2 Język i lokalizacja


| Ekran    | Wybór                                                           |
| -------- | --------------------------------------------------------------- |
| Language | **Polish** (lub English — dowolnie; komendy i tak po angielsku) |
| Location | **Poland**                                                      |
| Locale   | `pl_PL.UTF-8` (lub `en_US.UTF-8`)                               |
| Keyboard | **Polish** / **Polish (programmer's)** — jak wygodniej          |




### 1.3 Sieć


| Ekran              | Wybór                                                                                                            |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Hostname           | np. `vena-kiosk`                                                                                                 |
| Domain name        | puste (Enter)                                                                                                    |
| Konfiguracja sieci | Jeśli jest Ethernet — zwykle DHCP. Wi‑Fi w instalatorze opcjonalne; i tak skonfigurujesz NetworkManager później. |




### 1.4 Konta


| Ekran                  | Wybór                                                |
| ---------------------- | ---------------------------------------------------- |
| Root password          | Ustaw silne hasło root (zapisz je)                   |
| Full name for new user | np. `Kiosk`                                          |
| Username               | `kiosk` (ważne — reszta instrukcji zakłada tę nazwę) |
| Password for kiosk     | Ustaw hasło (do serwisu / SSH)                       |


> Jeśli instalator utworzył innego użytkownika — potem i tak zrobisz `kiosk` ręcznie (sekcja 4).



### 1.5 Partycjonowanie

Najprościej na czystym dysku:

1. **Guided - use entire disk**
2. Wybierz dysk
3. **All files in one partition** (dla kiosku wystarczy)
4. Potwierdź **Finish partitioning and write changes to disk** → **Yes**



### 1.6 Mirror i popularność


| Ekran                         | Wybór                           |
| ----------------------------- | ------------------------------- |
| Debian archive mirror country | Poland (lub najbliższy)         |
| Mirror                        | domyślny (np. `deb.debian.org`) |
| HTTP proxy                    | puste, chyba że masz            |
| Package usage survey          | **No**                          |




### 1.7 Wybór oprogramowania (WAŻNE)

Odznacz środowiska graficzne — Openbox doinstalujesz później ręcznie.

Zostaw zaznaczone tylko:

- [ ] Debian desktop environment ← **ODZNACZ**
- [ ] GNOME / KDE / … ← **wszystko odznaczone**
- [x] **SSH server** — opcjonalnie, wygodne do wgrywania plików
- [x] **standard system utilities**

Dalej → instalacja pakietów bazowych.

### 1.8 GRUB


| Ekran        | Wybór                                              |
| ------------ | -------------------------------------------------- |
| Install GRUB | **Yes**                                            |
| Boot device  | dysk systemowy (np. `/dev/sda` lub `/dev/nvme0n1`) |




### 1.9 Koniec instalatora

**Continue** → restart → wyjmij pendrive.

Masz czysty Debian **bez** GUI. Logujesz się na konsoli jako `kiosk` lub `root`.

---



## 2. Pierwsze logowanie i aktualizacja

Zaloguj się jako `root` (lub `kiosk` + `sudo`):

```bash
apt update
apt upgrade -y
```

Ustaw strefę czasową (jeśli trzeba):

```bash
timedatectl set-timezone Europe/Warsaw
```

---



## 3. Pakiety systemowe

Jako root (albo `sudo`):

```bash
apt update

apt install -y \
  xorg xinit openbox \
  python3 python3-pyqt6 python3-xlib \
  chromium \
  alsa-utils pulseaudio \
  network-manager \
  sudo \
  x11-utils x11-xserver-utils \
  fonts-dejavu-core
```

Co to daje:


| Pakiet                           | Po co                                                      |
| -------------------------------- | ---------------------------------------------------------- |
| `xorg` + `xinit`                 | Serwer X11, `startx`                                       |
| `openbox`                        | Lekki menedżer okien (margines 168 px, reguły WM_CLASS)    |
| `python3-pyqt6` / `python3-xlib` | UI VENA + pozycjonowanie okien / XTest                     |
| `chromium`                       | Spotify / YouTube w `--app`                                |
| `alsa-utils`                     | `amixer` — suwak głośności                                 |
| `pulseaudio`                     | Audio w Chromium (bez PA często cisza mimo że ALSA działa) |
| `network-manager`                | `nmcli` — lista Wi‑Fi w MENU                               |
| `sudo`                           | RESET z trybu serwisowego                                  |




### Alternatywa: zależności z pip

Jeśli wolisz pip zamiast pakietów `python3-pyqt6` / `python3-xlib`:

```bash
apt install -y python3-pip python3-venv
cd /home/kiosk/vena
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` w repo:

```
PyQt6>=6.5
python-xlib>=0.33
```

Na produkcji prostsze są **pakiety apt** (mniej problemów z Qt/platform plugins).

### Czego NIE instalować

- GNOME / KDE / Wayland — kolidują z modelem X11 + Openbox.
- `matchbox-keyboard` / `onboard` — **nie są potrzebne**; VENA ma własną klawiaturę (PyQt + XTest).

---



## 4. Użytkownik `kiosk` i grupy

Jeśli użytkownik już istnieje (z instalatora):

```bash
usermod -aG audio,video,netdev,sudo kiosk
```

Jeśli nie istnieje:

```bash
adduser kiosk
usermod -aG audio,video,netdev,sudo kiosk
```


| Grupa    | Po co                                              |
| -------- | -------------------------------------------------- |
| `audio`  | ALSA / Pulse                                       |
| `video`  | GPU / DRM                                          |
| `netdev` | NetworkManager / `nmcli`                           |
| `sudo`   | administracja (osobno: NOPASSWD tylko na `reboot`) |


Po zmianie grup: **wyloguj i zaloguj ponownie** użytkownika `kiosk` (albo reboot).

Sprawdzenie:

```bash
groups kiosk
# powinno zawierać: audio video netdev …
```

---



## 5. X11 + Openbox — pliki do utworzenia

Wszystkie ścieżki poniżej zakładają użytkownika `kiosk`. Twórz pliki jako `kiosk` (nie root), chyba że napisane inaczej.

```bash
su - kiosk
mkdir -p ~/.config/openbox
```



### 5.1 Domyślny `rc.xml` Openbox

Skopiuj szablon systemowy, potem go edytuj:

```bash
cp /etc/xdg/openbox/rc.xml ~/.config/openbox/rc.xml
```



### 5.2 Plik: `~/.config/openbox/rc.xml` — co zmienić

Otwórz edytorem:

```bash
nano ~/.config/openbox/rc.xml
```



#### A) Marginesy = 0 (ważne)

Znajdź sekcję `<margins>` i ustaw **wszystkie na 0**:

```xml
<margins>
  <top>0</top>
  <bottom>0</bottom>
  <left>0</left>
  <right>0</right>
</margins>
```

**Nie** ustawiaj `<left>168</left>` — Openbox wtedy wypycha całe VENA w prawo (czarny pasek po lewej).
Chromium pozycjonuje aplikacja (X11, `SPOTIFY_X=168`).

#### B) Reguły okien VENA / Spotify / YouTube

Znajdź sekcję `<applications>` (na końcu pliku, przed `</openbox_config>`) i **wewnątrz** niej dodaj
(tylko `class` — Chromium ma `name=open.spotify.com` / `www.youtube.com`, więc `name="Vena…"` **nie trafia**):

```xml
<application class="VenaKioskv1_2.py">
  <decor>no</decor>
  <position force="yes">
    <x>0</x>
    <y>0</y>
  </position>
  <layer>above</layer>
</application>
<application class="VenaSpotify">
  <decor>no</decor>
  <focus>no</focus>
  <layer>above</layer>
</application>
<application class="VenaYouTube">
  <decor>no</decor>
  <focus>no</focus>
  <layer>above</layer>
</application>
```

`WM_CLASS` (drugi człon) musi być `VenaSpotify` / `VenaYouTube` — tak startuje Chromium (`--class=…`).

Po edycji (gdy Openbox już działa):

```bash
openbox --reconfigure
```



### 5.3 Plik: `~/.xinitrc` (cała treść)

Uruchamia PulseAudio, Openbox i VENA przy `startx`:

```bash
nano ~/.xinitrc
```

Wklej **całość**:

```bash
#!/bin/sh
# VENA Kiosk — sesja X11

# Audio dla Chromium
pulseaudio --start 2>/dev/null || true

# Opcjonalnie: wycisz dźwięki systemowe / ustaw domyślny sink
# pactl set-sink-mute @DEFAULT_SINK@ 0

# Start Openbox (autostart Openbox odpali VENA — patrz sekcja 11)
exec openbox-session
```

Uprawnienia:

```bash
chmod +x ~/.xinitrc
```



### 5.4 Plik: `~/.config/openbox/autostart`

```bash
nano ~/.config/openbox/autostart
```

Na razie zostaw pusty lub z komentarzem — **pełną treść** dopiszesz w [sekcji 11](#11-autostart-vena-w-openbox) po skopiowaniu aplikacji.

```bash
#!/bin/sh
# (uzupełnione w sekcji 11)
```

```bash
chmod +x ~/.config/openbox/autostart
```



### 5.5 Rozdzielczość 1024×768 (jeśli monitor raportuje inną)

VENA ma na sztywno `SCREEN_W, SCREEN_H = 1024, 768`. Ustaw tryb X:

```bash
# lista trybów:
xrandr
# wymuszenie (przykład — nazwa wyjścia z xrandr, np. HDMI-1 / eDP-1):
xrandr --output HDMI-1 --mode 1024x768
```

Żeby ustawiało się przy starcie, dopisz tę linię **przed** `exec openbox-session` w `~/.xinitrc`.

---



## 6. Autologowanie i start X przy bootowaniu

Cel: po włączeniu zasilania → od razu Openbox + VENA, bez hasła na konsoli.

### 6.1 Autologin na tty1 (systemd)

Jako **root**:

```bash
mkdir -p /etc/systemd/system/getty@tty1.service.d
nano /etc/systemd/system/getty@tty1.service.d/autologin.conf
```

Treść pliku `/etc/systemd/system/getty@tty1.service.d/autologin.conf`:

```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin kiosk --noclear %I $TERM
```

```bash
systemctl daemon-reload
```



### 6.2 Automatyczny `startx` po zalogowaniu na tty1

Jako **kiosk**:

```bash
nano ~/.bash_profile
```

Treść pliku `~/.bash_profile`:

```bash
# Start X tylko na pierwszej konsoli (nie przy SSH)
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  startx
fi
```

Jeśli używasz tylko `.profile` (nie bash login):

```bash
nano ~/.profile
```

Dodaj na końcu te same 3 linie `if … startx`.

### 6.3 Test bez rebootu

Jako `kiosk` na lokalnej konsoli:

```bash
startx
```

Powinien wejść Openbox (puste tło / menu prawym przyciskiem). Wyjście: prawy przycisk → Exit (albo Ctrl+Alt+Backspace jeśli włączone).

---



## 7. Audio (PulseAudio + ALSA)

Bez PulseAudio odtwarzanie w Spotify/YouTube (Chromium) często **nie gra**, mimo że `amixer` reaguje na suwak.

```bash
# pakiety już w sekcji 3; upewnij się:
sudo apt install -y pulseaudio alsa-utils

# jako kiosk — w sesji użytkownika:
systemctl --user enable pulseaudio
systemctl --user start pulseaudio
```

Jeśli `systemctl --user` nie działa (brak lingering), wystarczy `pulseaudio --start` w `~/.xinitrc` (już jest).

### Test

```bash
aplay -L
speaker-test -t sine -c 2 -l 1
amixer sget Master
# albo PCM / Speaker — zależnie od karty:
amixer scontrols
```

VENA woła: `amixer -q sset Master <N>%`. Jeśli na Twojej karcie kanał to nie `Master`, trzeba zmienić `channel` w kodzie (`HardwareAudioMixer`) albo ustawić alias ALSA — na większości laptopów/Casio `Master` działa.

---



## 8. Wi-Fi (NetworkManager)

```bash
sudo systemctl enable --now NetworkManager
sudo systemctl disable --now networking 2>/dev/null || true
# (opcjonalnie wyłącz ifupdown, jeśli koliduje)
```

Użytkownik `kiosk` musi być w grupie `netdev` (sekcja 4).

### Test z konsoli

```bash
nmcli general
nmcli device wifi rescan
nmcli device wifi list
# połączenie (przykład):
nmcli device wifi connect "SSID" password "HASLO"
```

W aplikacji: kafelek **MENU** → Wi‑Fi (ten sam `nmcli`).

---



## 9. Sudoers — RESET bez hasła

Tryb serwisowy woła `sudo -n reboot` (bez pytania o hasło). Bez tego przycisk RESET nie zadziała.

Jako **root**:

```bash
nano /etc/sudoers.d/kiosk-reboot
```

**Cała treść** pliku `/etc/sudoers.d/kiosk-reboot`:

```
kiosk ALL=(root) NOPASSWD: /sbin/reboot, /usr/sbin/reboot, /sbin/poweroff, /usr/sbin/poweroff, /sbin/shutdown, /usr/sbin/shutdown
```

```bash
chmod 440 /etc/sudoers.d/kiosk-reboot
visudo -c -f /etc/sudoers.d/kiosk-reboot
```

Test jako `kiosk`:

```bash
sudo -n reboot
# maszyna powinna się zrestartować; jeśli pyta o hasło — sudoers jest źle
```

---



## 10. Skopiowanie aplikacji VENA



### 10.1 Katalog docelowy

```bash
sudo mkdir -p /home/kiosk/vena
sudo chown -R kiosk:kiosk /home/kiosk/vena
```



### 10.2 Wgraj pliki z repo

Potrzebujesz co najmniej:


| Plik                                        | Wymagany       |
| ------------------------------------------- | -------------- |
| `VenaKioskv1_1.py` (lub `VenaKioskv1_0.py`) | tak            |
| `requirements.txt`                          | tylko przy pip |


Katalogi `data/` i `logs/` aplikacja **tworzy sama** przy pierwszym starcie — nie kasuj ich na produkcji.

Przykłady wgrania:

```bash
# z pendrive
cp /media/kiosk/*/VenaKioskv1_1.py /home/kiosk/vena/

# albo scp z innego PC
scp VenaKioskv1_1.py kiosk@vena-kiosk:/home/kiosk/vena/
```

Struktura po pierwszym uruchomieniu:

```
/home/kiosk/vena/
├── VenaKioskv1_1.py
├── data/
│   ├── spotify_profile/    # sesja Spotify (login przeżywa reboot)
│   └── youtube_profile/    # sesja YouTube
└── logs/
    └── chromium.log        # diagnostyka crashy Chromium
```

**Nie kasuj** `data/spotify_profile` i `data/youtube_profile` — użytkownik musiałby logować się od nowa.

---



## 11. Autostart VENA w Openbox



### 11.1 Plik: `~/.config/openbox/autostart` (pełna treść)

Jako `kiosk`:

```bash
nano ~/.config/openbox/autostart
```

```bash
#!/bin/sh
# VENA Kiosk — autostart Openbox

# Daj X czas na wstanie
sleep 1

# Watchdog UI: restartuje VENA po crashu; wyjście serwisowe → CLI
# (plik data/no_autorestart) wyłącza pętlę do kolejnego bootu.
chmod +x /home/kiosk/vena/vena-watchdog.sh 2>/dev/null || true
/home/kiosk/vena/vena-watchdog.sh &
```

Skrypt `vena-watchdog.sh` leży obok `VenaKioskv1_2.py` w `/home/kiosk/vena/`
(w repo: `vena-watchdog.sh`).

```bash
chmod +x ~/.config/openbox/autostart
chmod +x /home/kiosk/vena/vena-watchdog.sh
```



### 11.2 Po zmianach

```bash
# w działającej sesji:
openbox --reconfigure
# albo wyloguj / reboot
sudo reboot
```

---



## 12. Uruchomienie ręczne (test)

Na działającym X + Openbox (albo po `startx`):

```bash
cd /home/kiosk/vena
python3 VenaKioskv1_1.py
```

Oczekiwane:

1. Pełny ekran 1024×768, sidebar ~168 px z lewej.
2. Po ~1,5 s preload Spotify (ukryty), potem YouTube.
3. Kafelki: SPOTIFY / YOUTUBE / EFEKTY / MENU.
4. Suwak głośności → `amixer`.
5. **POWRÓT** chowa Chromium poza ekran (muzyka/wideo **nie** giną).

---



## 13. Checklista weryfikacji

Po reboocie maszyny odznacz po kolei:

- [ ] Autologin `kiosk` na tty1
- [ ] Samochodem startuje X + Openbox
- [ ] Startuje VENA (sidebar widoczny)
- [ ] `speaker-test` / Play w Spotify ma dźwięk
- [ ] Suwak głośności zmienia poziom systemowy
- [ ] MENU → Wi‑Fi: widać sieci, da się połączyć
- [ ] Spotify: okno obok sidebara (nie pod nim), bez dekoracji Openbox
- [ ] YouTube: to samo
- [ ] POWRÓT: wraca home, muzyka dalej gra
- [ ] Tryb serwisowy → RESET restartuje bez hasła
- [ ] Po rebootcie Spotify nadal zalogowane (`data/spotify_profile`)

---



## 14. Tryb serwisowy

W MENU (lub z sidebara): **7×** klik w napis **VENA PILOT V** → PIN `1234`:


| Akcja                           | Skutek                                |
| ------------------------------- | ------------------------------------- |
| **RESET**                       | `sudo -n reboot`                      |
| **Wyłącz aplikację → CLI**      | zamyka VENA, zostaje Openbox/terminal |
| **Wyjście z trybu serwisowego** | powrót do normalnego UI               |


PIN jest na sztywno w kodzie (`DEV_PIN = "1234"`) — zmień przed produkcją jeśli potrzebujesz.

---



## 15. Diagnostyka


| Objaw                                   | Gdzie patrzeć                                                                          |
| --------------------------------------- | -------------------------------------------------------------------------------------- |
| Chromium znika / Exit 1                 | `/home/kiosk/vena/logs/chromium.log`                                                   |
| Brak dźwięku w YT/Spotify, suwak działa | PulseAudio (`pulseaudio --start`, `pactl info`)                                        |
| Okno pod sidebarem / czarny pasek       | margines `left=0` w `rc.xml` (nie 168!); pozycja Chromium z aplikacji                  |
| Brak okna / złe pozycjonowanie          | Openbox + reguły `VenaSpotify` / `VenaYouTube`; czy jest X11 (`echo $DISPLAY`)         |
| Wi‑Fi puste                             | `systemctl status NetworkManager`, grupa `netdev`, `nmcli device wifi list`            |
| RESET pyta o hasło                      | `/etc/sudoers.d/kiosk-reboot`, `sudo -n reboot`                                        |
| Czarny ekran po boot                    | autologin tty1, `~/.bash_profile` + `startx`, logi X: `~/.local/share/xorg/Xorg.0.log` |


Flagi Chromium (już w kodzie, nie trzeba ustawiać ręcznie):  
`--ozone-platform=x11 --disable-vulkan --disable-gpu …` — omijają typowe crashe AMDGPU/Vulkan.

---



## 16. Mapa plików (co gdzie leży)



### Tworzysz / edytujesz Ty


| Ścieżka                                                   | Akcja                                             |
| --------------------------------------------------------- | ------------------------------------------------- |
| `/etc/systemd/system/getty@tty1.service.d/autologin.conf` | **utwórz** — autologin                            |
| `/home/kiosk/.bash_profile` (lub `.profile`)              | **utwórz/dopisz** — `startx` na tty1              |
| `/home/kiosk/.xinitrc`                                    | **utwórz** — Pulse + Openbox                      |
| `/home/kiosk/.config/openbox/rc.xml`                      | **skopiuj + edytuj** — margines 168, reguły okien |
| `/home/kiosk/.config/openbox/autostart`                   | **utwórz** — start `vena-watchdog.sh`             |
| `/etc/sudoers.d/kiosk-reboot`                             | **utwórz** — NOPASSWD reboot                      |
| `/home/kiosk/vena/vena-watchdog.sh`                       | **skopiuj** — pętla restartu UI                   |
| `/home/kiosk/vena/VenaKioskv1_2.py`                       | **skopiuj** z repo                                |




### Tworzy aplikacja sama


| Ścieżka                                  | Znaczenie                            |
| ---------------------------------------- | ------------------------------------ |
| `/home/kiosk/vena/data/spotify_profile/` | Sesja Spotify                        |
| `/home/kiosk/vena/data/youtube_profile/` | Sesja YouTube                        |
| `/home/kiosk/vena/logs/chromium.log`     | Log Chromium (rotacja ~5 MiB w v1.1) |




### Komendy „na skróty” (kolejność od zera po zainstalowanym Debianie)

```bash
# 1) pakiety (root)
apt update && apt install -y \
  xorg xinit openbox \
  python3 python3-pyqt6 python3-xlib \
  chromium alsa-utils pulseaudio \
  network-manager sudo \
  x11-utils x11-xserver-utils fonts-dejavu-core

# 2) grupy
usermod -aG audio,video,netdev,sudo kiosk

# 3) NetworkManager
systemctl enable --now NetworkManager

# 4) sudoers reboot
echo 'kiosk ALL=(root) NOPASSWD: /sbin/reboot, /usr/sbin/reboot, /sbin/poweroff, /usr/sbin/poweroff, /sbin/shutdown, /usr/sbin/shutdown' \
  > /etc/sudoers.d/kiosk-reboot
chmod 440 /etc/sudoers.d/kiosk-reboot

# 5) autologin tty1
mkdir -p /etc/systemd/system/getty@tty1.service.d
printf '%s\n' '[Service]' 'ExecStart=' \
  'ExecStart=-/sbin/agetty --autologin kiosk --noclear %I $TERM' \
  > /etc/systemd/system/getty@tty1.service.d/autologin.conf
systemctl daemon-reload

# 6) dalej jako kiosk: .xinitrc, .bash_profile, openbox rc.xml + autostart, skopiuj .py
# 7) reboot
```

---



## Szybki skrót architektury (po co ten stack)

```
zasilanie
  → getty autologin kiosk
    → ~/.bash_profile → startx
      → ~/.xinitrc → pulseaudio + openbox-session
        → openbox/autostart → vena-watchdog.sh → python3 VenaKioskv1_2.py
          → sidebar 168 px + Chromium (VenaSpotify / VenaYouTube)
```

**Wayland, GNOME, pełny desktop — nie używaj.** Całość opiera się o X11, `python-xlib` i reguły Openbox.