# Troubleshooting — VENA Kiosk

Objaw → najpewniejsza przyczyna → jak sprawdzić → co zrobić.  
Instalacja od zera: [`naLinux.md`](naLinux.md). Architektura: [`ARCHITECTURE.md`](ARCHITECTURE.md).

Ryzyka **nie naprawione w kodzie** (osobne zadania) są na dole.

---

## Wejście w tryb serwisowy nie działa z sidebara

**Przyczyna:** 7 klików jest podpięte tylko do etykiety wersji w **MENU** (`Vena Pilot V v1.2`). Napis na sidebarze („VENA PILOT V”) nic nie robi.

**Diagnoza:** Home → MENU → wielokrotny klik w szary tekst wersji na środku, potem PIN `1234`.

**Naprawa:** to zamierzone zachowanie kodu, nie usterka sidebara. Dokumentacja historyczna myliła te dwa napisy.

---

## Chromium znika / Exit 1 / cisza w logu

**Przyczyna:** na AMDGPU Chromium padało na Vulkan/GPU; bez `chromium.log` śmierć jest cicha.

**Diagnoza:**

```bash
tail -n 80 /home/kiosk/vena/logs/chromium.log
pgrep -af chromium
```

**Naprawa:** flagi są już w `VenaKioskv1_2.py` (`--ozone-platform=x11 --disable-vulkan --disable-gpu …`). Nie usuwaj ich. Sprawdź, czy nie brakuje miejsca na dysku (`df -h`) i czy profil w `data/*_profile` nie jest uszkodzony. Tryb serwisowy → zabij Chromium (preload wróci).

Watchdog procesu restartuje max 3 razy; `_health_tick` może potem znów preloadować.

---

## Brak dźwięku w Spotify/YouTube, suwak działa

**Przyczyna:** `amixer` rusza ALSA, a Chromium gra przez PulseAudio.

**Diagnoza:**

```bash
pactl info
pulseaudio --check; echo $?
speaker-test -t sine -c 2 -l 1
```

**Naprawa:** `pulseaudio --start` w `~/.xinitrc` (patrz naLinux). User `kiosk` w grupie `audio`.

---

## Okno pod sidebarem / czarny pasek z lewej

**Przyczyna:** Openbox `<left>168</left>` albo VENA nie na `(0,0)`.

**Diagnoza:** `~/.config/openbox/rc.xml` → `<margins>` wszystkie 0. `xwininfo` na oknie VENA.

**Naprawa:** marginesy 0; reguła `class="VenaKioskv1_2.py"` z `force (0,0)`. Aplikacja sama pozycjonuje Chromium od x=168. `openbox --reconfigure`.

---

## Brak okna / złe pozycjonowanie / Wayland

**Przyczyna:** nie-X11 albo zły `WM_CLASS`.

**Diagnoza:** `echo $DISPLAY` (musi być `:0` lub podobny). `wmctrl -lx` / xprop WM_CLASS = `VenaSpotify` / `VenaYouTube`.

**Naprawa:** sesja Openbox + X11, nie GNOME/Wayland. Chromium startuje z `--class=`.

---

## Wi-Fi: pusta lista / „key-mgmt missing”

**Przyczyna:** NM nie działa albo zepsuty profil bez `wifi-sec.key-mgmt`.

**Diagnoza:**

```bash
systemctl status NetworkManager
groups   # netdev
nmcli device wifi list
```

**Naprawa:** v1.2 usuwa stary profil i robi `nmcli connection add` z `wifi-sec.key-mgmt wpa-psk`. Jeśli lista pusta: radio on, `nmcli networking on`, dongle USB. Kilka IP w MENU (eth + wlan) to **norma**, nie bug.

---

## RESET / wyłączenie pyta o hasło albo „nie wystartowało”

**Przyczyna:** brak sudoers NOPASSWD albo fałszywy alarm timera (reboot już trwa, a UI jeszcze żyje ~2,5 s).

**Diagnoza:** `sudo -n reboot` jako `kiosk`. Plik `/etc/sudoers.d/kiosk-reboot`.

**Naprawa:** treść sudoers w naLinux §9. Komunikat „Reboot nie wystartował” w kodzie jest **myłący** — nie oznacza od razu błędu (znane, nie naprawione).

---

## Czarny ekran po boot / nie wstaje VENA

**Przyczyna:** brak autologin / `startx` / watchdog.

**Diagnoza:** loguj się na tty2 (Ctrl+Alt+F2). Sprawdź `getty@tty1` drop-in, `~/.bash_profile`, `~/.xinitrc`, `~/.config/openbox/autostart`, `logs/vena_stdout.log`. X: `~/.local/share/xorg/Xorg.0.log`.

**Naprawa:** naLinux §6 i §11. Watchdog musi być wykonywalny i wskazywać `VenaKioskv1_2.py`.

---

## VENA pada i nie wraca / albo nie da się wyjść do CLI

**Przyczyna:** watchdog w pętli; albo brak flagi przy wyjściu serwisowym.

**Diagnoza:** `ps aux | grep -E 'vena-watchdog|VenaKioskv1_2'`. Czy istnieje `data/no_autorestart` w złym momencie.

**Naprawa:** wyjście serwisowe zapisuje flagę i `quit()`. Watchdog na starcie **kasuje** starą flagę (żeby po rebootcie znów wstawać). Nie uruchamiaj dwóch watchdogów (`/tmp/vena-watchdog.lock`).

---

## Klawiatura nic nie wpisuje w Spotify

**Przyczyna:** fokus w złym oknie (wyścig z Openbox); XTest nie trafia w Chromium.

**Diagnoza:** czy panel klawiatury jest nad Chromium (`VenaKeyboard`). Czy sesja to X11.

**Naprawa:** nie używać matchbox. Znaki ASCII idą XTest; poza US — schowek. Otwórz klawiaturę z sidebara, nie licz na auto-focus pola „Szukaj”.

---

## Kursor widać / dotyk nie działa

**Przyczyna:** Chromium rysuje własny kursor. Stara próba „wyłączenia pointera” psuła dotyk.

**Diagnoza:** czy `_cursor_timer` (400 ms) działa — to zamierzone. Dotyk musi działać mimo pustego kursora.

**Naprawa:** nie chować kursora przez `xinput disable`. Zostaw Qt override + blank pixmap.

---

## Efekty nie zmieniają brzmienia / cisza po Off

**Przyczyna:** brak `mbeq_1197`, zły sink, Off ustawia głośność 0.

**Diagnoza:** `pactl list short sinks`; `pactl list short modules | grep ladspa`.

**Naprawa:** pakiet LADSPA swh/mbeq na Debianie. Preset Off jest wyciszeniem — wróć Normal. Nie podbijaj basu > 0 dB.

---

## Logi / dysk

`vena.log` **nie rotuje** (rośnie przez dni). `chromium.log` rotuje przy starcie procesu (~5 MiB → `.1`). Mało miejsca: health loguje warning poniżej 200 MiB.

```bash
ls -lh /home/kiosk/vena/logs
df -h /home/kiosk
```

---

## Znane ryzyka (kodu nie ruszamy tutaj)

Osobne zadania — nie zgaduj łatki „przy okazji”:

| Ryzyko | Skutek |
|--------|--------|
| CDP WebSocket na wątku UI (co 2 s × 2 Chromium, także schowane) | zacięcie sidebara przy wolnym CDP |
| `_watch_active_media` co 1,5 s + CDP | to samo przy otwartym playerze |
| `_apply_x11_blank_cursor` co 400 ms, iteracja wszystkich okien | obciążenie X11 |
| `_pin_kiosk_geometry` tworzy nowy `X11WindowController`/`Display()` | wyciek połączeń X przy długim uptime |
| `amixer set` przez `Popen` bez wait | zombie |
| `vena.log` bez rotacji | zapełnienie dysku |
| Dwa Chromium zawsze w RAM | presja na Futro |
| `--no-sandbox` | treść WWW bliżej konta `kiosk` |
| PIN `1234` bez limitu prób | fizyczny dostęp = serwis |
| Hasło Wi-Fi w argv nmcli | widać w `/proc/.../cmdline` |
| Fałszywy alarm reboot/poweroff | operator myśli, że sudoers padł |
| Poweroff: tekst „Teraz możesz wyłączyć” od razu | otwarty punkt w TODO (opóźnić komunikat) |

Audyt v1.1 (historyczny, częściowo nieaktualny): [`docs/archive/ANALIZA_BLEDOW_v1.1.md`](docs/archive/ANALIZA_BLEDOW_v1.1.md).
