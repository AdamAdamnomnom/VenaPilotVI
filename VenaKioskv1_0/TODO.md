# TODO — Vena V v1.2 (`VenaKioskv1_2.py`)

## Wdrożone w kodzie

- [x] w menu usunac napisz "w kolejnych akutalnicj...'  ipt 
- [x] sprawdz czy przysik online dziala  
- [x] dodac ikonki pod napisami spotiy yt itp   
- [x] usunac napis muska wideo audio systme 

- [x] ujednolic klawiature z wpiswania hasla z kalwaitula ta co sie opla z panelu bocznego  
- [x] sprawdz bokowania wychodznia na inne storny z yt i sporfity zrobic tak aby sie nie dalo wyjsc ale jednocznie aby sie dalo kkozystac w szyksich fukcji danej apliakcji   
- [x] wlasnie widze ze jest kilka ip w paneiu menu sa 3 z konowkai od 124 do 126 nwm czy to blacz czy co   
  → **nie bug**: Ethernet `.126` + Wi‑Fi USB `.124` — w MENU pokazuje etykiety interfejsów
- [x] sprawdzicz czy napewno jest zabspieczenia przed ewtualnmi bledami systemu, lagami scikami systemu lub chroium, itp w razie czego no reboot czy cos, mozna dodac gdzies w trybie serwosywm jakies logi w razie czego 
- [x] efekty imprezowe: Party / Disco / Bass / Chill / Normal / Off (LADSPA mbeq EQ)   

- [x] gdy jest wlaczony tryb serwoswy aby na pasku z boku daj jakas informacji nawet ikonek ze jest serwis 
- [x] usun wszyskie zmianki o logo bo jezli nie uzywam to usuń i ogolnie to usun rzeczy nie potzrbne i z kodu i systemu 
- [x] przycisk wyalczania w menu — „WYŁĄCZ GŁOŚNIK”, popup + slider, vol 0 → sieć off → czarny ekran ~5 s → poweroff; sieć wraca przy następnym starcie
- [x] przenuscie trosze do gory chorium aby ukryc paek u goruy chroium.spotify itp ogolnie chdzoi o to aby jak naberdzije zblokac choirum aby uzywkownik nie mogl wyjc i robic cos innego aby to ywlgalo jak aplikacja bo dalj sie d a ywjsc np przez zbadj elemt albo pokazja sie kominkaty typowe dla choirum jak czy zapmaietac chaslo itp a to jest niepozadane 
- [x] usuac kursor aby nie byl widoczny nie wykrzaczajc przy tym calego projetku (była proba ale to blokwalo wtedy dotyk i nie dzialal poprawie )
- [x] pauza muzyki dopiero gdy nowy player faktycznie gra — nie przy samym wejściu w YT gdy gra Spotify
- [x] Wi‑Fi key-mgmt missing — delete profil + connect przez `nmcli connection add` z `wifi-sec.key-mgmt wpa-psk`
- [ ] `tam gdzie jest ekran gasnie to to daj za chwile mozna wlaczyc itp a  nie ze Teraz` 



## Pomysły na później



### Szybkie wygrane

- [ ] Ulubione / „ostatnio” — skróty: ostatnia sieć Wi‑Fi, ostatni efekt, „wznów Spotify”
- [ ] Blokada dzieci / impreza — PIN blokujący MENU/Wi‑Fi na czas imprezy
- [ ] Timer wyciszenia — Off za 30/60 min (koniec imprezy bez gaszenia sprzętu)
- [ ] Jasność ekranu — suwak w MENU (jeśli Futro ogarnia)



### Audio / impreza

- [ ] Ikona aktywnego efektu na sidebarze (Party/Bass… bez wchodzenia w EFEKTY)



### Stabilność kiosku

- [x] Watchdog UI — `vena-watchdog.sh` w Openbox autostart; po padnięciu Pythona restart za 2 s; wyjście serwisowe → CLI przez `data/no_autorestart`
- [ ] Zdrowy start — przy boot: czekaj na sieć → potem preload YT/Spotify
- [ ] Lepsze logi serwisowe — ostatni crash + uptime (+ temperatura jeśli jest sensor)



### UX pod palec

- [ ] Większy hit-target POWRÓT / KLAWIATURA w trybie web-app
- [ ] Potwierdzenie RESET w trybie serwisowym
- [ ] Ekran „ładowanie…” przy pierwszym otwarciu Spotify/YT
- [ ] USUNIECIE KUROSA CALOKWICE 



## Na kiosku

- [ ] *(później — nie robić teraz)* wyciszyć resztki tekstu przy bootcie (`[ OK ]`, `kiosk:` itd.); logo splash też odłożone — liczy się szybki start, nie idealna cisza
- [ ] 