# TODO — otwarty backlog (v1.2)

Zrobione historycznie rzeczy nie są tu trzymane — patrz [`DECISIONS.md`](DECISIONS.md) i tag `v1.2-baseline`.

## Otwarte (produkt)

- [ ] Ekran gaszenia (poweroff): komunikat „możesz wyłączyć zasilanie” dopiero po chwili, nie od razu z „Teraz”
- [ ] Zdrowy start: przy boot poczekać na sieć, potem preload YT/Spotify
- [ ] Większy hit-target POWRÓT / KLAWIATURA w trybie web-app
- [ ] Potwierdzenie RESET w trybie serwisowym
- [ ] Ekran „ładowanie…” przy pierwszym otwarciu Spotify/YT
- [ ] Ikona aktywnego efektu na sidebarze
- [ ] Ulubione / ostatnio: sieć Wi-Fi, efekt, wznów Spotify
- [ ] Blokada dzieci / impreza — PIN na MENU/Wi-Fi
- [ ] Timer wyciszenia Off za 30/60 min
- [ ] Jasność ekranu w MENU (jeśli Futro pozwala)
- [ ] Wyciszenie resztek tekstu przy boot (`[ OK ]`, `kiosk:`) — niski priorytet

## Otwarte (ryzyka z audytu — osobne zadania, nie „przy okazji”)

Opis: [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) (sekcja na dole).

- [ ] CDP / timery poza wątkiem UI (zacięcie sidebara przy długim uptime)
- [ ] Ponowne użycie jednego `X11 Display` w `_pin_kiosk_geometry`
- [ ] Rotacja `vena.log`; rotacja `chromium.log` w trakcie życia procesu
- [ ] `amixer set` bez zombie (`Popen` + wait/poll)
- [ ] PIN serwisowy: nie w kodzie / limit prób
- [ ] Hasło Wi-Fi poza argv `nmcli`
- [ ] Fałszywy alarm „reboot/poweroff nie wystartował”
