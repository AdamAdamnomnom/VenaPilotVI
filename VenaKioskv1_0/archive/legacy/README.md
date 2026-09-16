# Archiwum — stare implementacje VENA

Te pliki **nie są produkcją**. Zostały przeniesione tutaj, żeby nie mieszać się z aktywną aplikacją.

Produkcja: `VenaKioskv1_2.py` w katalogu głównym projektu.

## Zawartość

| Plik | Co to jest |
|------|------------|
| `VenaKioskv1_0.py` | Baseline kiosku (przed łatami niezawodności z lipca 2026). |
| `VenaKioskv1_1.py` | Wersja z watchdogiem Chromium, cleanupem, rotacją `chromium.log`, poprawkami Wi-Fi. |
| `_probe_kiosk.sh` | Jednorazowy skrypt diagnostyczny API XFixes (`hide_cursor`). Nie jest częścią runtime. |

## Jak wrócić do starej wersji

**Najbezpieczniej — cały stan sprzed docs/archive (Git), tag na pierwszym commicie:**

```bash
git fetch --tags
git checkout v1.2-baseline
```

To przywraca też poprzednie położenie plików (v0/v1 obok produkcji). Remote: `https://github.com/AdamAdamnomnom/VenaPilotVI.git`.

**Na aktualnym `main` — tylko odpalenie starego pliku (bez zmiany gałęzi):**

```bash
python3 archive/legacy/VenaKioskv1_1.py
```

Stare wersje **nie** mają pełnego zestawu v1.2 (EQ LADSPA, ukrywanie kursora, poweroff, CDP kiosk guards w obecnym kształcie). Nie wgrywaj ich na Futro zamiast `VenaKioskv1_2.py` bez świadomej decyzji.

Watchdog produkcyjny (`vena-watchdog.sh`) startuje wyłącznie `VenaKioskv1_2.py`.
