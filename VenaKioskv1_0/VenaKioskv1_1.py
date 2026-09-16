import sys
import subprocess
import re
import os
import signal
import logging
import time
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSlider, QLabel, QStackedWidget, QGridLayout, QSizePolicy,
    QDialog, QFrame, QLineEdit, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QCloseEvent

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------
SIDEBAR_WIDTH = 168
SCREEN_W, SCREEN_H = 1024, 768
SPOTIFY_X = SIDEBAR_WIDTH
SPOTIFY_W = SCREEN_W - SIDEBAR_WIDTH
SPOTIFY_H = SCREEN_H
DEV_PIN = "1234"
IS_LINUX = sys.platform.startswith("linux")

TILE_THEMES = {
    "SPOTIFY": {"accent": "#1DB954", "glow": "#1ed760", "subtitle": "Muzyka"},
    "YOUTUBE": {"accent": "#FF0033", "glow": "#ff4d6a", "subtitle": "Wideo"},
    "EFEKTY": {"accent": "#A855F7", "glow": "#c084fc", "subtitle": "Audio FX"},
    "MENU": {"accent": "#38BDF8", "glow": "#7dd3fc", "subtitle": "System"},
}

SPOTIFY_URL = "https://open.spotify.com"
SPOTIFY_WM_CLASS = "VenaSpotify"
YOUTUBE_URL = "https://www.youtube.com"
YOUTUBE_WM_CLASS = "VenaYouTube"
# CDP (DevTools) — tylko localhost; do „START” i blokady reklam poza domeną
SPOTIFY_DEBUG_PORT = 9333
YOUTUBE_DEBUG_PORT = 9334
# Hosty dozwolone w pasku adresu (reklama poza listą → powrót na URL startowy)
YOUTUBE_ALLOWED_HOSTS = (
    "youtube.com",
    "youtu.be",
    "youtubekids.com",
    "youtube-nocookie.com",
    "googlevideo.com",
    "ytimg.com",
    "ggpht.com",
    "google.com",
    "google.pl",
    "gstatic.com",
    "googleapis.com",
    "googleusercontent.com",
    "withyoutube.com",
)
SPOTIFY_ALLOWED_HOSTS = (
    "spotify.com",
    "spotifycdn.com",
    "scdn.co",
    "spotify.net",
    "spotilocal.com",
)
# Chromium źle znosi X11 unmap/map — chowamy okno poza ekranem (proces żyje).
APP_STOW_X = SCREEN_W + 64
APP_STOW_Y = 0
# Alias kompatybilności
SPOTIFY_STOW_X = APP_STOW_X
SPOTIFY_STOW_Y = APP_STOW_Y
CHROMIUM_CANDIDATES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")

# Logi Chromium — bez tego proces ginął po cichu (Exit 1, VK_ERROR_INCOMPATIBLE_DRIVER)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(_BASE_DIR, "logs")
CHROMIUM_LOG_PATH = os.path.join(LOG_DIR, "chromium.log")
CHROMIUM_LOG_MAX_BYTES = 5 * 1024 * 1024  # rotacja: chromium.log → .1
# Profil poza /tmp — login Spotify przeżywa restart systemu
DATA_DIR = os.path.join(_BASE_DIR, "data")
SPOTIFY_PROFILE_DIR = os.path.join(DATA_DIR, "spotify_profile")
YOUTUBE_PROFILE_DIR = os.path.join(DATA_DIR, "youtube_profile")
VOLUME_DEBOUNCE_MS = 180
AMIXER_TIMEOUT_S = 2
# Ile razy szukać okna po starcie Chromium (co 400 ms) — wolny sprzęt Casio
WINDOW_SETTLE_ATTEMPTS = 20
WINDOW_SETTLE_INTERVAL_MS = 400
WINDOW_SETTLE_FIRST_DELAY_MS = 800
# Watchdog: nie młóć Casio przy trwałym crashu Chromium
WATCHDOG_MAX_RESTARTS = 3
ORPHAN_WAIT_S = 2.0

# Wbudowana klawiatura ekranowa (nie matchbox — fokus/AlwaysOnTop go zabijało)
KEYBOARD_H = 280
KEYBOARD_Y = SCREEN_H - KEYBOARD_H

# US QWERTY: znaki wymagające Shift (e-mail / hasło)
_US_SHIFT_PAIRS = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "minus",
    "+": "equal",
    "{": "bracketleft",
    "}": "bracketright",
    "|": "backslash",
    ":": "semicolon",
    '"': "apostrophe",
    "<": "comma",
    ">": "period",
    "?": "slash",
    "~": "grave",
}
_US_PLAIN_KEYSYMS = {
    "-": "minus",
    "=": "equal",
    "[": "bracketleft",
    "]": "bracketright",
    "\\": "backslash",
    ";": "semicolon",
    "'": "apostrophe",
    ",": "comma",
    ".": "period",
    "/": "slash",
    "`": "grave",
}

# ---------------------------------------------------------------------------
# Kontroler dźwięku ALSA
# ---------------------------------------------------------------------------
class HardwareAudioMixer:
    """Bezpośrednia kontrola głośności przez ALSA (amixer)."""

    def __init__(self, channel="Master"):
        self.channel = channel
        self.available = True

    def set_volume(self, value: int):
        if not self.available:
            return
        safe_vol = max(0, min(int(value), 100))
        try:
            subprocess.Popen(
                ["amixer", "-q", "sset", self.channel, f"{safe_vol}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self.available = False
            logger.warning("ALSA/amixer niedostępne — suwak działa tylko lokalnie w UI.")
        except OSError as e:
            logger.error("Błąd ALSA (set): %s", e)

    def get_volume(self) -> int:
        if not self.available:
            return 30
        try:
            output = subprocess.check_output(
                ["amixer", "sget", self.channel],
                stderr=subprocess.DEVNULL,
                timeout=AMIXER_TIMEOUT_S,
            ).decode("utf-8")
            match = re.search(r"\[(\d+)%\]", output)
            if match:
                return int(match.group(1))
        except FileNotFoundError:
            self.available = False
            logger.warning("ALSA/amixer niedostępne — używam głośności domyślnej 30%.")
        except subprocess.TimeoutExpired:
            logger.warning(
                "ALSA/amixer nie odpowiedział w %ss — używam głośności domyślnej 30%%.",
                AMIXER_TIMEOUT_S,
            )
        except Exception as e:
            logger.error("Błąd ALSA (get): %s", e)
        return 30


# ---------------------------------------------------------------------------
# Wi-Fi (NetworkManager / nmcli) — jak klasyczna lista w Androidzie
# ---------------------------------------------------------------------------
@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    in_use: bool

    @property
    def is_secured(self) -> bool:
        sec = (self.security or "").strip().upper()
        return bool(sec) and sec not in ("--", "NONE", "OPEN")

    @property
    def signal_bars(self) -> str:
        # 0–4 paski jak w Androidzie
        if self.signal >= 75:
            return "▂▄▆█"
        if self.signal >= 50:
            return "▂▄▆░"
        if self.signal >= 25:
            return "▂▄░░"
        return "▂░░░"


def _nmcli_split(line: str) -> List[str]:
    """Parsuje linię nmcli -t z escape'ami \\:."""
    parts: List[str] = []
    buf: List[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            buf.append(line[i + 1])
            i += 2
            continue
        if ch == ":":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


class WifiManager:
    """Skanowanie i łączenie przez NetworkManager (nmcli)."""

    def __init__(self):
        self.available = self._probe()

    @staticmethod
    def _probe() -> bool:
        if not IS_LINUX:
            return False
        try:
            r = subprocess.run(
                ["nmcli", "-t", "-f", "STATE", "general"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def rescan(self) -> None:
        if not self.available:
            return
        try:
            subprocess.run(
                ["nmcli", "device", "wifi", "rescan"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Wi-Fi rescan: %s", exc)

    def list_networks(self) -> List[WifiNetwork]:
        if not self.available:
            return []
        try:
            r = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "IN-USE,SSID,SIGNAL,SECURITY",
                    "device",
                    "wifi",
                    "list",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("Wi-Fi list: %s", exc)
            return []
        if r.returncode != 0:
            logger.error("Wi-Fi list failed: %s", (r.stderr or "").strip())
            return []

        by_ssid: dict[str, WifiNetwork] = {}
        for raw in (r.stdout or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            parts = _nmcli_split(line)
            if len(parts) < 4:
                continue
            in_use = parts[0].strip() == "*"
            ssid = parts[1].strip()
            if not ssid:
                continue
            try:
                signal = int(parts[2].strip() or "0")
            except ValueError:
                signal = 0
            security = parts[3].strip()
            net = WifiNetwork(ssid=ssid, signal=signal, security=security, in_use=in_use)
            prev = by_ssid.get(ssid)
            if prev is None or net.signal > prev.signal or (net.in_use and not prev.in_use):
                if prev and prev.in_use:
                    net.in_use = True
                by_ssid[ssid] = net

        networks = list(by_ssid.values())
        networks.sort(key=lambda n: (not n.in_use, -n.signal, n.ssid.lower()))
        return networks

    def active_ssid(self) -> Optional[str]:
        if not self.available:
            return None
        try:
            r = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "IN-USE,SSID",
                    "device",
                    "wifi",
                    "list",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if r.returncode != 0:
            return None
        for raw in (r.stdout or "").splitlines():
            parts = _nmcli_split(raw.strip())
            if len(parts) >= 2 and parts[0].strip() == "*" and parts[1].strip():
                return parts[1].strip()
        return None

    def connect(self, ssid: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Łączy z siecią. Zwraca (ok, komunikat)."""
        if not self.available:
            return False, "NetworkManager (nmcli) niedostępny"
        if not ssid:
            return False, "Brak nazwy sieci"
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return False, "Przekroczono czas łączenia — spróbuj ponownie"
        except OSError as exc:
            return False, f"Błąd systemu: {exc} — spróbuj ponownie"

        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode == 0:
            return True, f"Połączono z „{ssid}”"
        # Typowe błędy nmcli — przyjazny komunikat
        low = out.lower()
        if "secrets were required" in low or "password" in low:
            return False, "Nieprawidłowe hasło — spróbuj ponownie"
        if "no network with ssid" in low:
            return False, "Nie znaleziono sieci — odśwież listę"
        if out:
            # Skróć długi stderr
            msg = out.splitlines()[-1].strip()
            return False, f"{msg} — spróbuj ponownie"
        return False, "Nie udało się połączyć — spróbuj ponownie"


class _WifiWorker(QThread):
    """Wątek dla skanu / łączenia — UI nie zamarza."""

    ok = pyqtSignal(object)
    err = pyqtSignal(str)

    def __init__(self, fn: Callable):
        # Bez parenta: unikamy "QThread: Destroyed while thread is still running"
        # gdy WifiPage znika wcześniej niż nmcli.
        super().__init__(None)
        self._fn = fn

    def run(self):
        try:
            self.ok.emit(self._fn())
        except Exception as exc:
            logger.exception("Wi-Fi worker")
            self.err.emit(str(exc))


# ---------------------------------------------------------------------------
# X11 / python-xlib
# ---------------------------------------------------------------------------
try:
    from Xlib import X, display, Xatom, XK  # type: ignore[import-not-found, import-untyped]
    from Xlib.ext import xtest  # type: ignore[import-not-found, import-untyped]
    from Xlib.protocol import event as xevent  # type: ignore[import-not-found, import-untyped]

    XLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - środowisko bez Xlib
    X = None  # type: ignore[assignment]
    display = None  # type: ignore[assignment]
    Xatom = None  # type: ignore[assignment]
    XK = None  # type: ignore[assignment]
    xtest = None  # type: ignore[assignment]
    xevent = None  # type: ignore[assignment]
    XLIB_AVAILABLE = False
    logger.warning(
        "python3-xlib nie jest zainstalowany. "
        "Zainstaluj: apt install python3-xlib"
    )


class X11WindowController:
    """Bezpośrednia kontrola okien X11 przez python-xlib (EWMH-compatible)."""

    def __init__(self) -> None:
        self._dpy = None
        self._root = None
        self._xatom = None

    def _connect(self) -> None:
        if self._dpy is not None:
            return
        if not IS_LINUX or not XLIB_AVAILABLE:
            raise RuntimeError("X11 niedostępne (tylko Linux + python3-xlib)")
        self._dpy = display.Display()
        self._root = self._dpy.screen().root
        self._xatom = Xatom

    def _win(self, wid: int):
        self._connect()
        return self._dpy.create_resource_object("window", wid)

    def _iter_window_ids(self, parent=None, depth: int = 0):
        """DFS po drzewie X11 (WM często reparentuje okna)."""
        self._connect()
        if depth > 8:
            return
        try:
            node = self._root if parent is None else self._win(parent)
            children = node.query_tree().children
        except Exception:
            return
        for child in children:
            try:
                wid = child.id if hasattr(child, "id") else int(child)
            except Exception:
                continue
            yield wid
            yield from self._iter_window_ids(wid, depth + 1)

    def _client_window_ids(self):
        """Top-level okna klientów (EWMH), z fallbackiem do DFS."""
        self._connect()
        try:
            prop = self._root.get_full_property(
                self._dpy.intern_atom("_NET_CLIENT_LIST"),
                self._xatom.WINDOW,
            )
            if prop and prop.value:
                for wid in prop.value:
                    yield int(wid)
                return
        except Exception:
            pass
        yield from self._iter_window_ids()

    def get_window_pid(self, wid: int) -> Optional[int]:
        if not IS_LINUX or not XLIB_AVAILABLE:
            return None
        self._connect()
        try:
            prop = self._win(wid).get_full_property(
                self._dpy.intern_atom("_NET_WM_PID"),
                self._xatom.CARDINAL,
            )
            if prop and prop.value:
                return int(prop.value[0])
        except Exception as exc:
            logger.debug("Odczyt _NET_WM_PID dla %s: %s", wid, exc)
        return None

    def find_windows_by_pid(self, pid: int) -> List[int]:
        """Wszystkie top-level okna danego PID (app + popupy reklam)."""
        found: List[int] = []
        if not IS_LINUX or not XLIB_AVAILABLE or not pid:
            return found
        self._connect()
        try:
            for wid in self._client_window_ids():
                try:
                    if self.get_window_pid(wid) == pid:
                        found.append(wid)
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("Szukanie okien po PID: %s", exc)
        return found

    def close_window(self, wid: int) -> None:
        """Poproś okno o zamknięcie (WM_DELETE_WINDOW) — bez kill całego Chromium."""
        if not IS_LINUX or not XLIB_AVAILABLE:
            return
        self._connect()
        try:
            win = self._win(wid)
            wm_protocols = self._dpy.intern_atom("WM_PROTOCOLS")
            wm_delete = self._dpy.intern_atom("WM_DELETE_WINDOW")
            ev = xevent.ClientMessage(
                window=win,
                client_type=wm_protocols,
                data=(32, [wm_delete, X.CurrentTime, 0, 0, 0]),
            )
            self._dpy.send_event(win, False, X.NoEventMask, ev)
            self._dpy.sync()
        except Exception as exc:
            logger.debug("close_window %s: %s", wid, exc)

    def find_window_by_pid(self, pid: int) -> Optional[int]:
        wins = self.find_windows_by_pid(pid)
        return wins[0] if wins else None

    def find_window_by_class(self, class_name: str) -> Optional[int]:
        if not IS_LINUX or not XLIB_AVAILABLE:
            return None
        self._connect()
        try:
            for wid in self._client_window_ids():
                try:
                    wm_class = self._win(wid).get_wm_class()
                    if wm_class and class_name in wm_class:
                        return wid
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("Szukanie okna po klasie nie powiodło się: %s", exc)
        return None

    def move_and_resize(self, wid: int, x: int, y: int, w: int, h: int) -> None:
        self._connect()
        try:
            win = self._win(wid)
            win.configure(x=x, y=y, width=w, height=h)
            self._dpy.sync()
        except Exception as exc:
            logger.error("Błąd ustawiania geometrii okna %s: %s", wid, exc)

    def raise_window(self, wid: int) -> None:
        self._connect()
        try:
            win = self._win(wid)
            win.configure(stack_mode=X.Above)
            self._dpy.sync()
        except Exception as exc:
            logger.error("Błąd podniesienia okna %s: %s", wid, exc)

    def lower_window(self, wid: int) -> None:
        self._connect()
        try:
            win = self._win(wid)
            win.configure(stack_mode=X.Below)
            self._dpy.sync()
        except Exception as exc:
            logger.debug("Obniżanie okna %s: %s", wid, exc)

    def is_valid(self, wid: int) -> bool:
        self._connect()
        try:
            self._win(wid).get_attributes()
            return True
        except Exception:
            return False

    def stow_window(self, wid: int) -> None:
        """Schowaj okno poza ekranem (bez unmap — Chromium tego nie lubi)."""
        self._connect()
        try:
            win = self._win(wid)
            # Na wypadek wcześniejszego unmap — przywróć, potem wynieś poza ekran.
            win.map()
            win.configure(
                x=APP_STOW_X,
                y=APP_STOW_Y,
                width=SPOTIFY_W,
                height=SPOTIFY_H,
                stack_mode=X.Below,
            )
            self._dpy.sync()
        except Exception as exc:
            logger.debug("Chowanie okna %s poza ekran: %s", wid, exc)

    def deploy_window(self, wid: int, x: int, y: int, w: int, h: int) -> None:
        """Pokaż okno we właściwej geometrii i podnieś je."""
        self._connect()
        try:
            win = self._win(wid)
            win.map()
            win.configure(x=x, y=y, width=w, height=h, stack_mode=X.Above)
            self._dpy.sync()
        except Exception as exc:
            logger.error("Pokazywanie okna %s: %s", wid, exc)

    def focus_window(self, wid: int) -> None:
        """Ustaw fokus klawiatury na oknie (wymagane przed XTest)."""
        self._connect()
        try:
            win = self._win(wid)
            win.map()
            win.configure(stack_mode=X.Above)
            win.set_input_focus(X.RevertToParent, X.CurrentTime)
            if xevent is not None:
                atom = self._dpy.intern_atom("_NET_ACTIVE_WINDOW")
                evt = xevent.ClientMessage(
                    window=win,
                    client_type=atom,
                    data=(32, [1, X.CurrentTime, 0, 0, 0]),
                )
                mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
                self._root.send_event(evt, event_mask=mask)
            self._dpy.sync()
        except Exception as exc:
            logger.debug("Fokus okna %s: %s", wid, exc)

    # Alias kompatybilności — stare unmap/map psuło ponowne otwarcie Spotify.
    def hide_window(self, wid: int) -> None:
        self.stow_window(wid)

    def show_window(self, wid: int) -> None:
        self.deploy_window(wid, SPOTIFY_X, 0, SPOTIFY_W, SPOTIFY_H)


# ---------------------------------------------------------------------------
# Kontroler procesu Chromium
# ---------------------------------------------------------------------------
def _prepare_chromium_log_file():
    """Otwórz logs/chromium.log z prostą rotacją (max 5 MiB → .1)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        if (
            os.path.exists(CHROMIUM_LOG_PATH)
            and os.path.getsize(CHROMIUM_LOG_PATH) > CHROMIUM_LOG_MAX_BYTES
        ):
            bak = CHROMIUM_LOG_PATH + ".1"
            try:
                os.replace(CHROMIUM_LOG_PATH, bak)
            except OSError:
                # Nie da się przenieść — obetnij, żeby dysk nie puchł
                with open(CHROMIUM_LOG_PATH, "w", encoding="utf-8"):
                    pass
    except OSError as exc:
        logger.debug("Rotacja logu Chromium: %s", exc)
    return open(CHROMIUM_LOG_PATH, "a", encoding="utf-8", errors="ignore")


class ChromiumController:
    """Cykl życia procesu Chromium."""

    def __init__(self) -> None:
        self.process = None
        self.pid = None
        self._log_file = None

    def launch(self, cmd: list) -> bool:
        if self.process and self.process.poll() is None:
            return True

        # Bez logowania do pliku Chromium potrafi umrzeć bez śladu
        # (np. VK_ERROR_INCOMPATIBLE_DRIVER na AMDGPU) — patrz logs/chromium.log
        try:
            if self._log_file and not self._log_file.closed:
                try:
                    self._log_file.close()
                except OSError:
                    pass
            self._log_file = _prepare_chromium_log_file()
            self._log_file.write(f"\n----- start {datetime.now().isoformat()} -----\n")
            self._log_file.flush()
            log_target = self._log_file
        except OSError as exc:
            logger.warning("Nie udało się otworzyć logu Chromium: %s", exc)
            log_target = subprocess.DEVNULL

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=log_target,
                stderr=subprocess.STDOUT if log_target != subprocess.DEVNULL else subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
            self.pid = self.process.pid
            logger.info("Chromium uruchomiony (PID %s), logi: %s", self.pid, CHROMIUM_LOG_PATH)
            return True
        except OSError as exc:
            logger.error("Nie udało się uruchomić Chromium: %s", exc)
            self.process = None
            self.pid = None
            return False

    def is_alive(self) -> bool:
        if not self.process:
            return False
        return self.process.poll() is None

    def get_pid(self) -> Optional[int]:
        if self.process and self.is_alive():
            return self.process.pid
        return None

    def terminate(self) -> None:
        if self.process:
            try:
                pgid = os.getpgid(self.process.pid)
                os.killpg(pgid, signal.SIGTERM)
                self.process.wait(timeout=5)
            except Exception:
                try:
                    pgid = os.getpgid(self.process.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    pass
            self.process = None
            self.pid = None
        if self._log_file and not self._log_file.closed:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None


# ---------------------------------------------------------------------------
# Główny menedżer aplikacji Chromium (Spotify / YouTube)
# ---------------------------------------------------------------------------
class ChromiumAppWindowManager:
    """
    Zarządzanie oknem Chromium --app przez python-xlib.
    - Preload ukryty przy starcie VENA
    - Watchdog procesu (co 10 s) — działa też gdy okno schowane
    - Ukrywanie przez wyniesienie poza ekran (bez unmap — proces żyje)
    - shutdown() tylko przy wyjściu z aplikacji (nie przy POWRÓT)
    - CDP: blokada reklam poza domeną + reset START
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        name: str,
        url: str,
        wm_class: str,
        profile_dir: str,
        debug_port: int,
        allowed_hosts: Tuple[str, ...],
    ) -> None:
        self.parent = parent
        self.name = name
        self.url = url
        self.wm_class = wm_class
        self.profile_dir = profile_dir
        self.debug_port = debug_port
        self.allowed_hosts = allowed_hosts
        self.x11 = X11WindowController()
        self.chromium = ChromiumController()
        self.wid = None
        self.visible = False
        self._launching = False
        self._keyboard_open = False
        # Jeśli użytkownik kliknie w trakcie preloadu — pokaż po settle
        self._pending_show = False
        self._restart_count = 0
        self.on_ready = None
        self.on_failed = None

        self._watchdog_timer = QTimer(parent)
        self._watchdog_timer.setInterval(10_000)
        self._watchdog_timer.timeout.connect(self._watchdog_tick)
        self._policy_timer = QTimer(parent)
        self._policy_timer.setInterval(2000)
        self._policy_timer.timeout.connect(self._enforce_kiosk_navigation)

    # ------------------------------------------------------------------
    # Publiczne API
    # ------------------------------------------------------------------
    def preload(self) -> None:
        """Uruchom Chromium w tle (ukryte)."""
        if not IS_LINUX:
            return
        self._ensure_running(silent=True)

    def show(self) -> None:
        if not IS_LINUX:
            self._fail(f"{self.name} (Chromium --app) działa tylko na kiosku Linux (X11).")
            return
        # Ręczne kliknięcie kafelka — pozwól znów na serię restartów watchdoga
        self._restart_count = 0
        self._pending_show = True
        if self._launching:
            # Preload/start w toku — pokaż w _post_launch_settle
            return
        self._ensure_running(silent=False)
        QTimer.singleShot(600, self._enforce_kiosk_navigation)

    def hide(self) -> None:
        # Watchdog zostaje włączony: proces ma żyć w tle i być restartowany
        self._pending_show = False
        self.visible = False
        if not IS_LINUX:
            self.wid = None
            return
        try:
            wid = self._resolve_wid()
            if wid:
                self.wid = wid
                self.x11.stow_window(wid)
        except Exception as exc:
            logger.debug("hide(%s) bez X11: %s", self.name, exc)
            self.wid = None

    def reset_to_home(self) -> None:
        """Wróć do URL startowego (reklama / wyjście poza aplikację)."""
        if not IS_LINUX:
            return
        if not self.chromium.is_alive():
            self.show()
            return
        try:
            if self._cdp_reset_home():
                logger.info("%s: reset do %s (CDP)", self.name, self.url)
                self.raise_to_front()
                return
        except Exception as exc:
            logger.warning("%s: CDP reset nieudany: %s", self.name, exc)
        logger.info("%s: reset przez restart Chromium", self.name)
        was_visible = self.visible or self._pending_show
        try:
            self._policy_timer.stop()
        except Exception:
            pass
        self.chromium.terminate()
        self.wid = None
        self._launching = False
        self._restart_count = 0
        self._ensure_running(silent=not was_visible)

    def shutdown(self) -> None:
        """Zatrzymaj watchdog i zabij Chromium (wyjście z VENA / aboutToQuit)."""
        try:
            self._watchdog_timer.stop()
        except Exception:
            pass
        try:
            self._policy_timer.stop()
        except Exception:
            pass
        self._pending_show = False
        self.visible = False
        self._launching = False
        self.wid = None
        self.chromium.terminate()

    def is_running(self) -> bool:
        return self.chromium.is_alive()

    def raise_to_front(self) -> None:
        """Ponownie ustaw geometrię i z-order po wejściu w tryb sidebara."""
        if not IS_LINUX:
            return
        if not self.visible and not self._pending_show:
            return
        try:
            wid = self._resolve_wid()
            if not wid:
                return
            self.wid = wid
            self.x11.deploy_window(wid, SPOTIFY_X, 0, SPOTIFY_W, self._content_height())
            self.visible = True
        except Exception as exc:
            logger.debug("raise_to_front(%s): %s", self.name, exc)

    def focus(self) -> None:
        """Oddaj fokus klawiatury do okna aplikacji (przed wpisywaniem)."""
        if not IS_LINUX:
            return
        try:
            wid = self._resolve_wid()
            if not wid:
                return
            self.wid = wid
            self.x11.focus_window(wid)
        except Exception as exc:
            logger.debug("focus(%s): %s", self.name, exc)

    def set_keyboard_open(self, open_: bool) -> None:
        """Zwęż treść, gdy wbudowana klawiatura zajmuje dół ekranu."""
        self._keyboard_open = bool(open_)
        if self.visible:
            self.raise_to_front()

    def _content_height(self) -> int:
        if self._keyboard_open:
            return max(200, SPOTIFY_H - KEYBOARD_H)
        return SPOTIFY_H

    # ------------------------------------------------------------------
    # CDP — karty / URL (tylko 127.0.0.1)
    # ------------------------------------------------------------------
    def _cdp_base(self) -> str:
        return f"http://127.0.0.1:{self.debug_port}"

    def _cdp_request(self, path: str, method: str = "GET", timeout: float = 1.5):
        req = Request(self._cdp_base() + path, method=method, data=b"" if method == "PUT" else None)
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def _cdp_tabs(self) -> list:
        try:
            data = self._cdp_request("/json/list")
        except (URLError, HTTPError, TimeoutError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _cdp_close(self, target_id: str) -> None:
        try:
            self._cdp_request(f"/json/close/{target_id}")
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            logger.debug("CDP close %s: %s", target_id, exc)

    def _cdp_new(self, url: str) -> bool:
        path = f"/json/new?{url}"
        try:
            self._cdp_request(path, method="PUT", timeout=2.0)
            return True
        except (URLError, HTTPError, TimeoutError, OSError):
            pass
        try:
            self._cdp_request(path, timeout=2.0)
            return True
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            logger.debug("CDP new tab: %s", exc)
            return False

    def _cdp_ready(self) -> bool:
        try:
            self._cdp_request("/json/version")
            return True
        except (URLError, HTTPError, TimeoutError, OSError):
            return False

    def _url_allowed(self, url: str) -> bool:
        if not url:
            return True
        low = url.lower()
        if low.startswith(
            ("about:", "chrome://", "chrome-extension://", "devtools://", "data:", "blob:")
        ):
            return True
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        if not host:
            return True
        for suf in self.allowed_hosts:
            if host == suf or host.endswith("." + suf):
                return True
        return False

    def _cdp_ws_call(self, ws_url: str, method: str, params: Optional[dict] = None, timeout: float = 2.5) -> bool:
        """Minimalny CDP po WebSocket (stdlib) — Page.navigate w oknie --app."""
        try:
            parsed = urlparse(ws_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 80
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query

            import base64
            import socket as _socket

            key = base64.b64encode(os.urandom(16)).decode("ascii")
            sock = _socket.create_connection((host, port), timeout=timeout)
            try:
                sock.settimeout(timeout)
                upgrade = (
                    f"GET {path} HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {key}\r\n"
                    "Sec-WebSocket-Version: 13\r\n"
                    "\r\n"
                ).encode("ascii")
                sock.sendall(upgrade)
                # Odczytaj nagłówki upgrade
                buf = b""
                while b"\r\n\r\n" not in buf:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return False
                    buf += chunk
                    if len(buf) > 65536:
                        return False
                if b"101" not in buf.split(b"\r\n", 1)[0]:
                    return False

                payload = json.dumps(
                    {"id": 1, "method": method, "params": params or {}}
                ).encode("utf-8")
                # Maskowany frame (klient → serwer)
                mask = os.urandom(4)
                header = bytearray([0x81])  # FIN + text
                n = len(payload)
                if n < 126:
                    header.append(0x80 | n)
                elif n < 65536:
                    header.append(0x80 | 126)
                    header.extend(n.to_bytes(2, "big"))
                else:
                    header.append(0x80 | 127)
                    header.extend(n.to_bytes(8, "big"))
                masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                sock.sendall(bytes(header) + mask + masked)

                # Krótki odczyt odpowiedzi (nie blokuj UI długo)
                try:
                    sock.recv(4096)
                except OSError:
                    pass
                return True
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
        except Exception as exc:
            logger.debug("CDP WS %s: %s", method, exc)
            return False

    def _cdp_navigate_main(self, url: str) -> bool:
        """Przejdź w istniejącym oknie --app (bez nowej karty)."""
        tabs = self._cdp_tabs()
        target = None
        for t in tabs:
            if t.get("type") in ("page", "app") and t.get("webSocketDebuggerUrl"):
                target = t
                if self._url_allowed(t.get("url") or ""):
                    break
        if not target:
            return self._cdp_new(url)
        ws = target.get("webSocketDebuggerUrl")
        if not ws:
            return self._cdp_new(url)
        ok = self._cdp_ws_call(ws, "Page.navigate", {"url": url})
        if ok:
            # Domknij obce karty / popupy
            for t in tabs:
                if t.get("type") not in ("page", "app"):
                    continue
                tid = t.get("id")
                if tid and tid != target.get("id") and not self._url_allowed(t.get("url") or ""):
                    self._cdp_close(tid)
        return ok

    def _cdp_reset_home(self) -> bool:
        """Wróć na URL startowy w tym samym oknie --app."""
        if not self._cdp_ready():
            return False
        if self._cdp_navigate_main(self.url):
            return True
        # Fallback: nowa karta + sprzątanie
        if not self._cdp_new(self.url):
            return False
        tabs = self._cdp_tabs()
        keep_id = None
        home_marker = urlparse(self.url).hostname or ""
        for t in tabs:
            if t.get("type") not in ("page", "app"):
                continue
            u = (t.get("url") or "").lower()
            if home_marker and home_marker in u and self._url_allowed(t.get("url") or ""):
                keep_id = t.get("id")
                break
        if keep_id is None:
            for t in tabs:
                if t.get("type") in ("page", "app") and self._url_allowed(t.get("url") or ""):
                    keep_id = t.get("id")
                    break
        for t in tabs:
            if t.get("type") not in ("page", "app"):
                continue
            tid = t.get("id")
            if not tid or tid == keep_id:
                continue
            if keep_id is None and self._url_allowed(t.get("url") or ""):
                keep_id = tid
                continue
            self._cdp_close(tid)
        return True

    def _enforce_kiosk_navigation(self) -> None:
        """Zamknij popupy X11 + wróć z obcych URL (reklamy = lag)."""
        if not self.chromium.is_alive():
            return
        try:
            self._close_extra_x11_windows()
        except Exception as exc:
            logger.debug("%s popup X11: %s", self.name, exc)
        try:
            tabs = self._cdp_tabs()
            if not tabs:
                return
            bad = []
            good = []
            for t in tabs:
                if t.get("type") not in ("page", "app"):
                    continue
                url = t.get("url") or ""
                if self._url_allowed(url):
                    good.append(t)
                else:
                    bad.append(t)
            if not bad:
                return
            # Najpierw spróbuj wrócić w głównym oknie (bez mnożenia kart)
            if not good:
                logger.info("%s: reklama/obcy URL — nawigacja na %s", self.name, self.url)
                self._cdp_navigate_main(self.url)
                if self.visible:
                    self.raise_to_front()
                return
            for t in bad:
                tid = t.get("id")
                if tid:
                    logger.info(
                        "%s: wyjście poza app — zamykam %s",
                        self.name,
                        (t.get("url") or "")[:80],
                    )
                    self._cdp_close(tid)
        except Exception as exc:
            logger.debug("%s enforce CDP: %s", self.name, exc)

    def _close_extra_x11_windows(self) -> None:
        """Reklamy często otwierają drugie okno Chromium — zamykamy je."""
        pid = self.chromium.get_pid()
        if not pid:
            return
        wins = self.x11.find_windows_by_pid(pid)
        if len(wins) <= 1:
            return
        main = self.wid if self.wid in wins else None
        if main is None:
            for wid in wins:
                try:
                    wm_class = self.x11._win(wid).get_wm_class()
                    if wm_class and self.wm_class in wm_class:
                        main = wid
                        break
                except Exception:
                    continue
        if main is None:
            main = wins[0]
        self.wid = main
        for wid in wins:
            if wid == main:
                continue
            logger.info("%s: zamykam popup X11 WID %s", self.name, wid)
            self.x11.close_window(wid)

    # ------------------------------------------------------------------
    # Wewnętrzne
    # ------------------------------------------------------------------
    def _resolve_wid(self) -> Optional[int]:
        if self.wid and self.x11.is_valid(self.wid):
            return self.wid
        return self._find_window()

    def _stow(self, wid: int) -> None:
        self.x11.stow_window(wid)
        self.visible = False

    def _reveal(self, wid: int) -> None:
        self.wid = wid
        self.x11.deploy_window(wid, SPOTIFY_X, 0, SPOTIFY_W, self._content_height())
        self.visible = True
        self._pending_show = False
        self._restart_count = 0
        if not self._policy_timer.isActive():
            self._policy_timer.start()
        if self.on_ready:
            self.on_ready()
        # Chromium czasem resetuje geometrię zaraz po map/configure — dogrywamy.
        QTimer.singleShot(120, self.raise_to_front)
        QTimer.singleShot(400, self.raise_to_front)
        QTimer.singleShot(1000, self.raise_to_front)
        QTimer.singleShot(2000, self.raise_to_front)

    def _kill_orphan_chromium(self) -> None:
        """Zabij Chromium z poprzedniej sesji VENA (ten sam WM_CLASS / profil)."""
        if not IS_LINUX:
            return
        try:
            wid = self.x11.find_window_by_class(self.wm_class)
            if not wid:
                return
            orphan_pid = self.x11.get_window_pid(wid)
            our_pid = self.chromium.get_pid()
            if not orphan_pid or orphan_pid == our_pid:
                return
            logger.warning(
                "Orphan %s (PID %s, WID %s) — zabijam przed nowym startem",
                self.name,
                orphan_pid,
                wid,
            )
            try:
                os.kill(orphan_pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + ORPHAN_WAIT_S
            while time.monotonic() < deadline:
                try:
                    os.kill(orphan_pid, 0)
                except ProcessLookupError:
                    return
                time.sleep(0.1)
            try:
                os.kill(orphan_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except Exception as exc:
            logger.debug("orphan cleanup %s: %s", self.name, exc)

    def _ensure_running(self, silent: bool = False) -> bool:
        if self.chromium.is_alive():
            wid = self._resolve_wid()
            if wid:
                self.wid = wid
                if silent and not self._pending_show:
                    self._stow(wid)
                else:
                    self._reveal(wid)
                if not self._watchdog_timer.isActive():
                    self._watchdog_timer.start()
                if not self._policy_timer.isActive():
                    self._policy_timer.start()
                return True
            # Proces żyje, ale okna jeszcze nie ma — daj settle kolejną szansę
            if not self._launching:
                self._launching = True
                if not silent:
                    self._pending_show = True
                QTimer.singleShot(
                    WINDOW_SETTLE_INTERVAL_MS,
                    lambda: self._post_launch_settle(silent, attempt=1),
                )
            elif not silent:
                self._pending_show = True
            return False

        if self._launching:
            if not silent:
                self._pending_show = True
            return False

        self._launching = True
        if not silent:
            self._pending_show = True

        binary = self._resolve_chromium()
        if not binary:
            self._launching = False
            self._pending_show = False
            self._fail(
                f"Nie znaleziono Chromium — spróbuj ponownie.\n"
                "Zainstaluj: sudo apt install chromium"
            )
            return False

        try:
            os.makedirs(self.profile_dir, exist_ok=True)
        except OSError as exc:
            self._launching = False
            self._pending_show = False
            self._fail(
                f"Nie można utworzyć profilu {self.name} — spróbuj ponownie.\n{exc}"
            )
            return False

        # Stary Chromium z crashu VENA blokuje profil / myli WM_CLASS
        self._kill_orphan_chromium()

        cmd = [
            binary,
            f"--app={self.url}",
            f"--window-size={SPOTIFY_W},{SPOTIFY_H}",
            f"--window-position={APP_STOW_X},{APP_STOW_Y}",
            f"--class={self.wm_class}",
            f"--user-data-dir={self.profile_dir}",
            f"--remote-debugging-port={self.debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--test-type",
            "--noerrdialogs",
            "--disable-infobars",
            "--no-first-run",
            # Naprawa cichego crashu (Exit 1, VK_ERROR_INCOMPATIBLE_DRIVER na AMDGPU)
            "--ozone-platform=x11",
            "--disable-vulkan",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--no-sandbox",
            "--disable-features=TranslateUI",
            "--disable-session-crashed-bubble",
        ]

        if not self.chromium.launch(cmd):
            self._launching = False
            self._pending_show = False
            self._fail("Nie udało się uruchomić Chromium — spróbuj ponownie.")
            return False

        QTimer.singleShot(
            WINDOW_SETTLE_FIRST_DELAY_MS,
            lambda: self._post_launch_settle(silent, attempt=1),
        )
        return True

    def _post_launch_settle(self, silent: bool = False, attempt: int = 1) -> None:
        want_show = self._pending_show or not silent
        try:
            wid = self._find_window()
            if wid:
                self.wid = wid
                if want_show:
                    self._reveal(wid)
                    logger.info("Okno %s gotowe (WID %s)", self.name, wid)
                else:
                    self._stow(wid)
                    self._restart_count = 0
                    if not self._policy_timer.isActive():
                        self._policy_timer.start()
                    logger.info("%s preloaded w tle (WID %s, ukryte)", self.name, wid)
                if not self._watchdog_timer.isActive():
                    self._watchdog_timer.start()
                self._launching = False
                return

            # Okno czasem pojawia się później niż proces — więcej prób na wolnym sprzęcie.
            if attempt < WINDOW_SETTLE_ATTEMPTS and self.chromium.is_alive():
                QTimer.singleShot(
                    WINDOW_SETTLE_INTERVAL_MS,
                    lambda: self._post_launch_settle(silent, attempt=attempt + 1),
                )
                return

            logger.warning(
                "Nie znaleziono okna %s po starcie — sprawdź %s",
                self.name,
                CHROMIUM_LOG_PATH,
            )
            self._pending_show = False
            self._launching = False
            if want_show:
                self._fail(
                    f"{self.name} nie odpowiada — spróbuj ponownie.\n"
                    f"Sprawdź logi: {CHROMIUM_LOG_PATH}"
                )
        except Exception as exc:
            logger.error("Settle %s nie powiódł się: %s", self.name, exc)
            self._launching = False
            self._pending_show = False
            if want_show:
                self._fail(f"{self.name} nie odpowiada — spróbuj ponownie.")

    def _find_window(self) -> Optional[int]:
        # Najpierw PID naszej instancji — unikamy orphanowanego okna po WM_CLASS
        pid = self.chromium.get_pid()
        if pid:
            wid = self.x11.find_window_by_pid(pid)
            if wid:
                return wid
        # Fallback: na Casio _NET_WM_PID bywa później niż samo okno
        return self.x11.find_window_by_class(self.wm_class)

    def _watchdog_tick(self) -> None:
        try:
            if not self.chromium.is_alive():
                logger.warning(
                    "%s (Chromium) zakończył działanie — restart w tle. Zobacz %s",
                    self.name,
                    CHROMIUM_LOG_PATH,
                )
                self._watchdog_timer.stop()
                try:
                    self._policy_timer.stop()
                except Exception:
                    pass
                was_visible = self.visible
                self.wid = None
                self._launching = False
                if self._restart_count >= WATCHDOG_MAX_RESTARTS:
                    logger.error(
                        "%s: limit restartów watchdoga (%s) — stop",
                        self.name,
                        WATCHDOG_MAX_RESTARTS,
                    )
                    self._fail(
                        f"{self.name} padł wielokrotnie — sprawdź {CHROMIUM_LOG_PATH}"
                    )
                    return
                self._restart_count += 1
                # Jeśli było widoczne — pokaż po restarcie; inaczej cichy preload
                self._ensure_running(silent=not was_visible)
                return

            if self.wid and not self.x11.is_valid(self.wid):
                logger.warning(
                    "WID %s (%s) nieprawidłowy — szukam ponownie.", self.wid, self.name
                )
                self.wid = None
                wid = self._find_window()
                if not wid:
                    return
                self.wid = wid
                if self.visible:
                    self.x11.deploy_window(
                        wid, SPOTIFY_X, 0, SPOTIFY_W, self._content_height()
                    )
                else:
                    self.x11.stow_window(wid)
                logger.info(
                    "Okno %s odzyskane (WID %s, visible=%s)",
                    self.name,
                    wid,
                    self.visible,
                )
        except Exception as exc:
            logger.error("watchdog %s: %s", self.name, exc)

    def _resolve_chromium(self) -> Optional[str]:
        for name in CHROMIUM_CANDIDATES:
            try:
                subprocess.run(
                    ["which", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                return name
            except (FileNotFoundError, subprocess.CalledProcessError, OSError):
                continue
        return None

    def _fail(self, message: str) -> None:
        self.visible = False
        self._launching = False
        self._pending_show = False
        if self.on_failed:
            self.on_failed(message)


# Alias dla czytelności w starszych odniesieniach
SpotifyWindowManager = ChromiumAppWindowManager


# ---------------------------------------------------------------------------
# Klawiatura ekranowa — wbudowana (PyQt + XTest → Spotify)
# ---------------------------------------------------------------------------
# Chromium nie otwiera systemowej klawiatury dotykowej. matchbox/onboard padały
# przez WindowStaysOnTopHint i utratę fokusu. Własna klawiatura:
#  - nie przejmuje fokusu (WA_ShowWithoutActivating / NoFocus),
#  - przed każdym znakiem oddaje fokus do Spotify,
#  - wysyła klawisze przez XTest (Chromium odrzuca syntetyczne XSendEvent).
# Auto-otwarcie przy kliknięciu „Szukaj” w Spotify Web nie jest wiarygodne
# (osobny proces, brak API fokusu pól) — zostaje przycisk ⌨ KLAWIATURA.
# ---------------------------------------------------------------------------
class X11KeyInjector:
    """Wstrzykiwanie klawiszy do wskazanego okna przez XTest (+ schowek dla PL)."""

    def __init__(self) -> None:
        self._dpy = None

    def _connect(self):
        if not XLIB_AVAILABLE or xtest is None or XK is None:
            raise RuntimeError("XTest / Xlib niedostępne")
        if self._dpy is None:
            self._dpy = display.Display()
        return self._dpy

    def _keycode_for_keysym_name(self, name: str) -> int:
        dpy = self._connect()
        keysym = XK.string_to_keysym(name)
        if not keysym:
            return 0
        return dpy.keysym_to_keycode(keysym) or 0

    def send_char(self, ch: str, focus_cb=None) -> None:
        if ch == "\n":
            self.tap_special("Return", focus_cb=focus_cb)
            return
        if ch == "\b":
            self.tap_special("BackSpace", focus_cb=focus_cb)
            return
        if ch == " ":
            self.tap_special("space", focus_cb=focus_cb)
            return

        # Poza ASCII (ąęół…) — schowek.
        if ord(ch) > 127:
            self._paste_text(ch, focus_cb=focus_cb)
            return

        if focus_cb:
            focus_cb()

        dpy = self._connect()
        need_shift = False
        keycode = 0

        if ch.isalpha():
            need_shift = ch.isupper()
            keycode = self._keycode_for_keysym_name(ch.lower())
        elif ch.isdigit():
            keycode = self._keycode_for_keysym_name(ch)
        elif ch in _US_SHIFT_PAIRS:
            need_shift = True
            keycode = self._keycode_for_keysym_name(_US_SHIFT_PAIRS[ch])
        elif ch in _US_PLAIN_KEYSYMS:
            keycode = self._keycode_for_keysym_name(_US_PLAIN_KEYSYMS[ch])
        else:
            keysym = XK.string_to_keysym(ch)
            keycode = dpy.keysym_to_keycode(keysym) if keysym else 0

        if not keycode:
            self._paste_text(ch, focus_cb=None)
            return

        shift_code = self._keycode_for_keysym_name("Shift_L")
        try:
            if need_shift and shift_code:
                xtest.fake_input(dpy, X.KeyPress, shift_code)
            xtest.fake_input(dpy, X.KeyPress, keycode)
            xtest.fake_input(dpy, X.KeyRelease, keycode)
            if need_shift and shift_code:
                xtest.fake_input(dpy, X.KeyRelease, shift_code)
            dpy.sync()
        except Exception as exc:
            logger.error("XTest send_char(%r): %s", ch, exc)
            self._paste_text(ch, focus_cb=None)

    def tap_special(self, name: str, focus_cb=None) -> None:
        if focus_cb:
            focus_cb()
        dpy = self._connect()
        keycode = self._keycode_for_keysym_name(name)
        if not keycode:
            logger.debug("Brak keycode dla keysym %s", name)
            return
        try:
            xtest.fake_input(dpy, X.KeyPress, keycode)
            xtest.fake_input(dpy, X.KeyRelease, keycode)
            dpy.sync()
        except Exception as exc:
            logger.error("XTest tap(%s): %s", name, exc)

    def _paste_text(self, text: str, focus_cb=None) -> None:
        app = QApplication.instance()
        if app is None:
            return
        cb = app.clipboard()
        previous = cb.text()
        cb.setText(text)
        if focus_cb:
            focus_cb()
        dpy = self._connect()
        ctrl = self._keycode_for_keysym_name("Control_L")
        v_key = self._keycode_for_keysym_name("v")
        try:
            xtest.fake_input(dpy, X.KeyPress, ctrl)
            xtest.fake_input(dpy, X.KeyPress, v_key)
            xtest.fake_input(dpy, X.KeyRelease, v_key)
            xtest.fake_input(dpy, X.KeyRelease, ctrl)
            dpy.sync()
        except Exception as exc:
            logger.error("XTest paste(%r): %s", text, exc)
        finally:
            QTimer.singleShot(200, lambda: cb.setText(previous))


class VirtualKeyboard(QWidget):
    """Klawiatura w stylu Androida: ABC / ?123 / =\\< — e-mail, hasło, wyszukiwanie."""

    # mode: letters | numbers | symbols
    def __init__(self, focus_cb, on_visibility=None, parent=None):
        super().__init__(parent)
        self._focus_cb = focus_cb
        self._on_visibility = on_visibility
        self._injector = X11KeyInjector()
        self._shift = False
        self._mode = "letters"  # letters | numbers | symbols
        self._visible = False
        self._keys_box: Optional[QWidget] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(SPOTIFY_W, KEYBOARD_H)
        self.setObjectName("virtualKeyboard")
        self.setStyleSheet(
            """
            #virtualKeyboard {
                background-color: #1a1d24;
                border-top: 1px solid #2a2f3a;
            }
            QPushButton {
                background-color: #2b303b;
                color: #f8fafc;
                border: none;
                border-radius: 6px;
                font-size: 20px;
                font-weight: 500;
                padding: 0px;
            }
            QPushButton:pressed { background-color: #4b5563; }
            QPushButton#keyAction {
                background-color: #3a4050;
                font-size: 15px;
                font-weight: 700;
            }
            QPushButton#keyAction:pressed { background-color: #0ea5e9; }
            QPushButton#keyEnter {
                background-color: #0ea5e9;
                color: #ffffff;
                font-size: 15px;
                font-weight: 700;
            }
            QPushButton#keyEnter:pressed { background-color: #0284c7; }
            QPushButton#keySpace {
                background-color: #2b303b;
                font-size: 14px;
                letter-spacing: 1px;
            }
            """
        )

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(6, 8, 6, 6)
        self._root.setSpacing(0)
        self._build_keys()

    @property
    def is_open(self) -> bool:
        return self._visible

    def toggle(self) -> bool:
        if self._visible:
            self.hide_keyboard()
            return False
        self.show_keyboard()
        return True

    def show_keyboard(self) -> None:
        self._mode = "letters"
        self._shift = False
        self._build_keys()
        self.move(SPOTIFY_X, KEYBOARD_Y)
        self.show()
        self.raise_()
        self._visible = True
        if self._on_visibility:
            self._on_visibility(True)
        if self._focus_cb:
            QTimer.singleShot(40, self._focus_cb)

    def hide_keyboard(self) -> None:
        was_open = self._visible
        self.hide()
        self._visible = False
        self._shift = False
        self._mode = "letters"
        self._build_keys()
        if was_open and self._on_visibility:
            self._on_visibility(False)

    @staticmethod
    def _qt_label(text: str) -> str:
        # QPushButton traktuje '&' jako mnemonic — żeby widać było '&', trzeba '&&'.
        return text.replace("&", "&&")

    def _make_key(
        self,
        label: str,
        slot,
        stretch: int = 1,
        role: str = "char",
    ) -> QPushButton:
        btn = QPushButton(self._qt_label(label))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setMinimumHeight(52)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if role == "action":
            btn.setObjectName("keyAction")
        elif role == "enter":
            btn.setObjectName("keyEnter")
        elif role == "space":
            btn.setObjectName("keySpace")
        btn.clicked.connect(slot)
        btn._kb_stretch = stretch  # type: ignore[attr-defined]
        return btn

    def _add_row(self, layout: QVBoxLayout, keys: list) -> None:
        row = QHBoxLayout()
        row.setSpacing(5)
        row.setContentsMargins(2, 0, 2, 0)
        for item in keys:
            row.addWidget(item, stretch=getattr(item, "_kb_stretch", 1))
        layout.addLayout(row, stretch=1)

    def _build_keys(self) -> None:
        if self._keys_box is not None:
            self._root.removeWidget(self._keys_box)
            self._keys_box.deleteLater()
            self._keys_box = None

        box = QWidget()
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if self._mode == "letters":
            self._build_letters(layout)
        elif self._mode == "numbers":
            self._build_numbers(layout)
        else:
            self._build_symbols(layout)

        self._keys_box = box
        self._root.addWidget(box)

    def _char_key(self, ch: str, display: Optional[str] = None) -> QPushButton:
        label = display if display is not None else ch
        # Wszystkie znaki (w tym @ . , &) — ten sam rozmiar (stretch=1)
        return self._make_key(label, lambda _=False, c=ch: self._on_char(c), stretch=1)

    def _bottom_row(self, mode_label: str, mode_slot, side_char: str = "@") -> list:
        # Jednolite klawisze znakowe; szersze tylko spacja / Enter / tryb
        return [
            self._make_key(mode_label, mode_slot, stretch=2, role="action"),
            self._char_key(side_char),
            self._make_key("spacja", lambda: self._on_char(" "), stretch=5, role="space"),
            self._char_key("."),
            self._make_key("Enter", lambda: self._special("Return"), stretch=2, role="enter"),
            self._make_key("▼", self.hide_keyboard, stretch=2, role="action"),
        ]

    def _build_letters(self, layout: QVBoxLayout) -> None:
        def row_chars(s: str):
            return [self._char_key(c, c.upper() if self._shift else c) for c in s]

        self._add_row(layout, row_chars("qwertyuiop"))
        self._add_row(layout, row_chars("asdfghjkl"))
        # Shift / ⌫ lekko szersze; litery równe sobie
        self._add_row(
            layout,
            [
                self._make_key(
                    "⇧" if not self._shift else "⇪",
                    self._toggle_shift,
                    stretch=2,
                    role="action",
                ),
                *row_chars("zxcvbnm"),
                self._make_key(
                    "⌫", lambda: self._special("BackSpace"), stretch=2, role="action"
                ),
            ],
        )
        self._add_row(layout, self._bottom_row("?123", self._to_numbers))

    def _build_numbers(self, layout: QVBoxLayout) -> None:
        # Równe klawisze w każdym rzędzie (żadnych stretch=14 obok stretch=1)
        self._add_row(layout, [self._char_key(c) for c in "1234567890"])
        self._add_row(layout, [self._char_key(c) for c in "@#$%&-_+()"])
        self._add_row(
            layout,
            [
                self._make_key("=\\<", self._to_symbols, stretch=2, role="action"),
                *[self._char_key(c) for c in "*/\"':;!?"],
                self._make_key(
                    "⌫", lambda: self._special("BackSpace"), stretch=2, role="action"
                ),
            ],
        )
        self._add_row(layout, self._bottom_row("ABC", self._to_letters, side_char=","))

    def _build_symbols(self, layout: QVBoxLayout) -> None:
        self._add_row(layout, [self._char_key(c) for c in "~`|^•°={}\\"])
        self._add_row(layout, [self._char_key(c) for c in "[]<>€£¥¿¡"])
        self._add_row(
            layout,
            [
                self._make_key("?123", self._to_numbers, stretch=2, role="action"),
                *[self._char_key(c) for c in "™©®✓_+/"],
                self._make_key(
                    "⌫", lambda: self._special("BackSpace"), stretch=2, role="action"
                ),
            ],
        )
        self._add_row(layout, self._bottom_row("ABC", self._to_letters, side_char=","))

    def _to_letters(self) -> None:
        self._mode = "letters"
        self._shift = False
        self._build_keys()
        if self._focus_cb:
            self._focus_cb()

    def _to_numbers(self) -> None:
        self._mode = "numbers"
        self._shift = False
        self._build_keys()
        if self._focus_cb:
            self._focus_cb()

    def _to_symbols(self) -> None:
        self._mode = "symbols"
        self._shift = False
        self._build_keys()
        if self._focus_cb:
            self._focus_cb()

    def _toggle_shift(self) -> None:
        self._shift = not self._shift
        self._build_keys()
        if self._focus_cb:
            self._focus_cb()

    def _on_char(self, ch: str) -> None:
        out = ch.upper() if self._shift and "a" <= ch <= "z" else ch
        try:
            self._injector.send_char(out, focus_cb=self._focus_cb)
        except Exception as exc:
            logger.error("Klawiatura: nie wysłano %r: %s", out, exc)
        if self._shift and "a" <= ch <= "z":
            self._shift = False
            self._build_keys()

    def _special(self, name: str) -> None:
        try:
            self._injector.tap_special(name, focus_cb=self._focus_cb)
        except Exception as exc:
            logger.error("Klawiatura: special %s: %s", name, exc)


class OnScreenKeyboard:
    """Fasada: wbudowana VirtualKeyboard sterowana z sidebara."""

    def __init__(self, focus_cb, on_visibility=None) -> None:
        self._focus_cb = focus_cb
        self._on_visibility = on_visibility
        self._panel: Optional[VirtualKeyboard] = None

    def _ensure(self) -> VirtualKeyboard:
        if self._panel is None:
            self._panel = VirtualKeyboard(
                self._focus_cb,
                on_visibility=self._on_visibility,
            )
        return self._panel

    @property
    def is_open(self) -> bool:
        return bool(self._panel and self._panel.is_open)

    def toggle(self) -> None:
        if not IS_LINUX or not XLIB_AVAILABLE:
            logger.warning("Klawiatura ekranowa wymaga Linuksa + python3-xlib (XTest).")
            return
        self._ensure().toggle()

    def hide(self) -> None:
        if self._panel and self._panel.is_open:
            self._panel.hide_keyboard()


# ---------------------------------------------------------------------------
# Slider dotykowy
# ---------------------------------------------------------------------------
class TouchSlider(QSlider):
    """Pionowy suwak z mapowaniem dotyku na pełną wysokość."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._pixel_to_val(event.position().y()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self._pixel_to_val(event.position().y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _pixel_to_val(self, y_pos: float) -> int:
        height = self.height()
        if height <= 0:
            return self.minimum()
        ratio = max(0.0, min(1.0, 1.0 - (y_pos / height)))
        span = self.maximum() - self.minimum()
        return int(round(self.minimum() + ratio * span))


# ---------------------------------------------------------------------------
# PIN dialog
# ---------------------------------------------------------------------------
class PinPadDialog(QDialog):
    """Ekranowa klawiatura PIN (wejście do trybu serwisowego)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setModal(True)
        self.setFixedSize(SCREEN_W, SCREEN_H)
        self._pin = ""
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background-color: rgba(8, 10, 16, 245);")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("pinCard")
        card.setFixedWidth(420)
        card.setStyleSheet(
            """
            #pinCard {
                background-color: #161b22;
                border: 2px solid #2a3340;
                border-radius: 20px;
            }
            """
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 36, 32, 28)
        card_layout.setSpacing(14)

        title = QLabel("TRYB SERWISOWY")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #38BDF8; letter-spacing: 3px;"
        )
        card_layout.addWidget(title)

        hint = QLabel("Wpisz kod PIN")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 22px; font-weight: bold; color: #ffffff;")
        card_layout.addWidget(hint)

        self.dots = QLabel("○  ○  ○  ○")
        self.dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dots.setStyleSheet(
            "font-size: 28px; color: #38BDF8; letter-spacing: 6px; padding: 12px 0;"
        )
        card_layout.addWidget(self.dots)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setFixedHeight(22)
        self.error_label.setStyleSheet("font-size: 13px; color: #f87171;")
        card_layout.addWidget(self.error_label)

        grid = QGridLayout()
        grid.setSpacing(12)
        keys = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("C", 3, 0), ("0", 3, 1), ("OK", 3, 2),
        ]
        for text, row, col in keys:
            btn = QPushButton(text)
            btn.setMinimumSize(100, 64)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if text == "OK":
                btn.setStyleSheet(self._key_style("#0ea5e9", "#0284c7"))
                btn.clicked.connect(self._submit)
            elif text == "C":
                btn.setStyleSheet(self._key_style("#374151", "#4b5563"))
                btn.clicked.connect(self._clear)
            else:
                btn.setStyleSheet(self._key_style("#1f2937", "#374151"))
                btn.clicked.connect(lambda _=False, d=text: self._digit(d))
            grid.addWidget(btn, row, col)
        card_layout.addLayout(grid)

        cancel = QPushButton("ANULUJ")
        cancel.setMinimumHeight(48)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #9ca3af;
                font-size: 14px;
                font-weight: bold;
                border: 1px solid #374151;
                border-radius: 10px;
                margin-top: 6px;
            }
            QPushButton:pressed { background: #1f2937; color: #fff; }
            """
        )
        cancel.clicked.connect(self.reject)
        card_layout.addWidget(cancel)

        wrap = QHBoxLayout()
        wrap.addStretch()
        wrap.addWidget(card)
        wrap.addStretch()
        root.addStretch()
        root.addLayout(wrap)
        root.addStretch()

    @staticmethod
    def _key_style(bg: str, pressed: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: #ffffff;
                font-size: 22px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
            }}
            QPushButton:pressed {{ background-color: {pressed}; }}
        """

    def _digit(self, d: str):
        if len(self._pin) >= 4:
            return
        self._pin += d
        self.error_label.setText("")
        self._refresh_dots()
        if len(self._pin) == 4:
            QTimer.singleShot(120, self._submit)

    def _clear(self):
        self._pin = ""
        self.error_label.setText("")
        self._refresh_dots()

    def _refresh_dots(self):
        filled = "●" * len(self._pin)
        empty = "○" * (4 - len(self._pin))
        self.dots.setText("  ".join(filled + empty))

    def _submit(self):
        if self._pin == DEV_PIN:
            self.accept()
            return
        self.error_label.setText("Nieprawidłowy kod PIN — spróbuj ponownie")
        self._pin = ""
        self._refresh_dots()
        self._shake()

    def _shake(self):
        anim = QPropertyAnimation(self, b"pos", self)
        origin = self.pos()
        anim.setDuration(280)
        anim.setKeyValueAt(0.0, origin)
        anim.setKeyValueAt(0.2, origin + QPoint(-12, 0))
        anim.setKeyValueAt(0.4, origin + QPoint(12, 0))
        anim.setKeyValueAt(0.6, origin + QPoint(-8, 0))
        anim.setKeyValueAt(0.8, origin + QPoint(8, 0))
        anim.setKeyValueAt(1.0, origin)
        anim.start()


# ---------------------------------------------------------------------------
# Wi-Fi — strona listy sieci (styl Androida), w obszarze treści obok sidebara
# ---------------------------------------------------------------------------
class WifiPage(QWidget):
    """Lista dostępnych sieci Wi-Fi + łączenie z hasłem (klawiatura ekranowa)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wifi = WifiManager()
        self._worker: Optional[_WifiWorker] = None
        self._pending: Optional[WifiNetwork] = None
        self._busy = False
        self._build_ui()

    def on_show(self):
        """Wywołaj przy wejściu na stronę — skan sieci."""
        self._show_list()
        QTimer.singleShot(80, self._refresh)

    def handle_back(self) -> bool:
        """True = cofnięto wewnątrz Wi-Fi (hasło→lista); False = wyjście ze strony."""
        if self.pages.currentIndex() == 1:
            self._show_list()
            return True
        return False

    def _build_ui(self):
        self.setObjectName("wifiPage")
        self.setStyleSheet(
            """
            #wifiPage { background-color: #0b0e14; }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        badge = QLabel("SIEĆ")
        badge.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #38BDF8; letter-spacing: 3px;"
        )
        titles.addWidget(badge)
        title = QLabel("Wi-Fi")
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #f8fafc;")
        titles.addWidget(title)
        header.addLayout(titles)
        header.addStretch()

        self.btn_refresh = QPushButton("ODŚWIEŻ")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setMinimumSize(140, 48)
        self.btn_refresh.setStyleSheet(self._btn_style("#1f2937", "#374151"))
        self.btn_refresh.clicked.connect(self._refresh)
        header.addWidget(self.btn_refresh)
        root.addLayout(header)

        self.status_label = QLabel("Szukanie sieci…")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "font-size: 14px; color: #9ca3af; padding: 4px 2px;"
        )
        root.addWidget(self.status_label)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_list_page())
        self.pages.addWidget(self._build_password_page())
        root.addWidget(self.pages, stretch=1)

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            """
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: #12161e; width: 14px; margin: 0; border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: #374151; min-height: 40px; border-radius: 7px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """
        )
        self.list_host = QWidget()
        self.list_host.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()
        scroll.setWidget(self.list_host)
        layout.addWidget(scroll)
        return page

    def _build_password_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        self.pass_ssid_label = QLabel("")
        self.pass_ssid_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pass_ssid_label.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #f8fafc;"
        )
        layout.addWidget(self.pass_ssid_label)

        hint = QLabel("Wpisz hasło sieci")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 14px; color: #9ca3af;")
        layout.addWidget(hint)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setMinimumHeight(52)
        self.password_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.password_edit.setStyleSheet(
            """
            QLineEdit {
                background-color: #161b22;
                color: #f8fafc;
                border: 2px solid #2a3340;
                border-radius: 12px;
                font-size: 20px;
                padding: 8px 16px;
            }
            QLineEdit:focus { border-color: #0ea5e9; }
            """
        )
        layout.addWidget(self.password_edit)

        self.pass_error = QLabel("")
        self.pass_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pass_error.setFixedHeight(22)
        self.pass_error.setStyleSheet("font-size: 13px; color: #f87171;")
        layout.addWidget(self.pass_error)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        btn_back = QPushButton("WSTECZ")
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setMinimumHeight(52)
        btn_back.setStyleSheet(self._btn_style("#374151", "#4b5563"))
        btn_back.clicked.connect(self._show_list)
        actions.addWidget(btn_back)

        self.btn_show_pass = QPushButton("POKAŻ")
        self.btn_show_pass.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_show_pass.setMinimumHeight(52)
        self.btn_show_pass.setCheckable(True)
        self.btn_show_pass.setStyleSheet(self._btn_style("#1f2937", "#374151"))
        self.btn_show_pass.toggled.connect(self._toggle_password_visible)
        actions.addWidget(self.btn_show_pass)

        self.btn_connect = QPushButton("POŁĄCZ")
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setMinimumHeight(52)
        self.btn_connect.setStyleSheet(self._btn_style("#0ea5e9", "#0284c7"))
        self.btn_connect.clicked.connect(self._submit_password)
        actions.addWidget(self.btn_connect, stretch=1)
        layout.addLayout(actions)

        layout.addWidget(self._build_soft_keyboard(), stretch=1)
        return page

    def _build_soft_keyboard(self) -> QWidget:
        """Prosta klawiatura dotykowa wpisująca do pola hasła."""
        box = QWidget()
        box.setObjectName("wifiKb")
        box.setStyleSheet(
            """
            #wifiKb { background-color: #1a1d24; border-radius: 12px; }
            QPushButton {
                background-color: #2b303b;
                color: #f8fafc;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: 600;
                min-height: 44px;
            }
            QPushButton:pressed { background-color: #4b5563; }
            QPushButton#kbAction { background-color: #3a4050; font-size: 14px; }
            QPushButton#kbEnter { background-color: #0ea5e9; font-size: 14px; }
            """
        )
        root = QVBoxLayout(box)
        root.setContentsMargins(8, 10, 8, 10)
        root.setSpacing(6)
        self._kb_shift = False
        self._kb_mode = "letters"  # letters | numbers
        self._kb_root = root
        self._kb_rows_host: Optional[QWidget] = None
        self._rebuild_soft_keyboard()
        return box

    def _rebuild_soft_keyboard(self):
        if self._kb_rows_host is not None:
            self._kb_root.removeWidget(self._kb_rows_host)
            self._kb_rows_host.deleteLater()
            self._kb_rows_host = None

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        def add_row(keys: list):
            row = QHBoxLayout()
            row.setSpacing(5)
            for item in keys:
                row.addWidget(item, stretch=getattr(item, "_st", 1))
            lay.addLayout(row, stretch=1)

        def char_btn(ch: str, label: Optional[str] = None) -> QPushButton:
            b = QPushButton((label or ch).replace("&", "&&"))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=ch: self._kb_char(c))
            b._st = 1
            return b

        def action_btn(label: str, slot, stretch=2, obj="kbAction") -> QPushButton:
            b = QPushButton(label)
            b.setObjectName(obj)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            b._st = stretch
            return b

        if self._kb_mode == "letters":
            def row_chars(s: str):
                return [
                    char_btn(c, c.upper() if self._kb_shift else c) for c in s
                ]

            add_row(row_chars("qwertyuiop"))
            add_row(row_chars("asdfghjkl"))
            add_row(
                [
                    action_btn("⇧" if not self._kb_shift else "⇪", self._kb_toggle_shift),
                    *row_chars("zxcvbnm"),
                    action_btn("⌫", self._kb_backspace),
                ]
            )
            add_row(
                [
                    action_btn("?123", self._kb_to_numbers),
                    char_btn("@"),
                    action_btn("spacja", lambda: self._kb_char(" "), stretch=5),
                    char_btn("."),
                    action_btn("OK", self._submit_password, stretch=2, obj="kbEnter"),
                ]
            )
        else:
            add_row([char_btn(c) for c in "1234567890"])
            add_row([char_btn(c) for c in "@#$%&-_+()"])
            add_row(
                [
                    action_btn("ABC", self._kb_to_letters),
                    *[char_btn(c) for c in "*/\"':;!?"],
                    action_btn("⌫", self._kb_backspace),
                ]
            )
            add_row(
                [
                    action_btn(",.", lambda: self._kb_char(",")),
                    char_btn("="),
                    action_btn("spacja", lambda: self._kb_char(" "), stretch=5),
                    char_btn("."),
                    action_btn("OK", self._submit_password, stretch=2, obj="kbEnter"),
                ]
            )

        self._kb_rows_host = host
        self._kb_root.addWidget(host)

    def _kb_char(self, ch: str):
        out = ch.upper() if self._kb_shift and "a" <= ch <= "z" else ch
        self.password_edit.insert(out)
        if self._kb_shift and "a" <= ch <= "z":
            self._kb_shift = False
            self._rebuild_soft_keyboard()

    def _kb_backspace(self):
        self.password_edit.backspace()

    def _kb_toggle_shift(self):
        self._kb_shift = not self._kb_shift
        self._rebuild_soft_keyboard()

    def _kb_to_numbers(self):
        self._kb_mode = "numbers"
        self._kb_shift = False
        self._rebuild_soft_keyboard()

    def _kb_to_letters(self):
        self._kb_mode = "letters"
        self._kb_shift = False
        self._rebuild_soft_keyboard()

    @staticmethod
    def _btn_style(bg: str, pressed: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
                padding: 0 16px;
            }}
            QPushButton:pressed {{ background-color: {pressed}; }}
            QPushButton:disabled {{ background-color: #1f2937; color: #6b7280; }}
        """

    def _set_busy(self, busy: bool, message: str = ""):
        self._busy = busy
        self.btn_refresh.setEnabled(not busy)
        self.btn_connect.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def _clear_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _worker_is_running(self) -> bool:
        """Bezpiecznie: po finished+deleteLater stary QThread jest martwy."""
        w = self._worker
        if w is None:
            return False
        try:
            return w.isRunning()
        except RuntimeError:
            self._worker = None
            return False

    def shutdown(self) -> None:
        """Poczekaj na nmcli przed zniszczeniem UI (aboutToQuit / closeEvent)."""
        w = self._worker
        self._worker = None
        if w is None:
            return
        try:
            if w.isRunning():
                # nmcli nie da się sensownie przerwać — czekamy z limitem
                if not w.wait(15_000):
                    logger.warning("Wi-Fi worker nie zakończył się w 15 s")
            w.deleteLater()
        except RuntimeError:
            pass

    def _refresh(self):
        if self._busy or self._worker_is_running():
            return
        if not self._wifi.available:
            self.status_label.setText(
                "Wi-Fi niedostępne — wymagany Linux z NetworkManager (nmcli)."
            )
            self._clear_list()
            self.list_layout.addStretch()
            return
        self._set_busy(True, "Szukanie sieci…")
        # Listę czyścimy dopiero po wyniku — przy błędzie zostaje poprzednia

        def job():
            self._wifi.rescan()
            return self._wifi.list_networks()

        if not self._start_worker(job, self._on_scan_ok, self._on_scan_err):
            self._set_busy(False, "Skan już trwa — spróbuj za chwilę")

    def _start_worker(self, fn, on_ok, on_err) -> bool:
        if self._worker_is_running():
            return False
        # Wyrzuć odniesienie do zakończonego wątku (unikaj isRunning na deleteLater)
        if self._worker is not None:
            try:
                self._worker.deleteLater()
            except RuntimeError:
                pass
            self._worker = None

        worker = _WifiWorker(fn)
        self._worker = worker

        def _cleanup():
            if self._worker is worker:
                self._worker = None
            try:
                worker.deleteLater()
            except RuntimeError:
                pass

        worker.ok.connect(on_ok)
        worker.err.connect(on_err)
        worker.finished.connect(_cleanup)
        worker.start()
        return True

    def _on_scan_ok(self, networks):
        if not isinstance(networks, list):
            networks = []
        self._set_busy(False)
        active = next((n.ssid for n in networks if getattr(n, "in_use", False)), None)
        if active:
            self.status_label.setText(f"Połączono z „{active}” · {len(networks)} sieci")
        elif networks:
            self.status_label.setText(f"Znaleziono {len(networks)} sieci — wybierz, aby połączyć")
        else:
            self.status_label.setText("Brak sieci — sprawdź Wi-Fi lub odśwież listę")

        self._clear_list()
        for net in networks:
            self.list_layout.addWidget(self._make_row(net))
        self.list_layout.addStretch()
        self.pages.setCurrentIndex(0)

    def _on_scan_err(self, message: str):
        self._set_busy(False, f"Błąd skanowania: {message} — spróbuj ponownie")

    def _make_row(self, net: WifiNetwork) -> QPushButton:
        lock = "[*] " if net.is_secured else ""
        connected = "  OK" if net.in_use else ""
        label = f"{net.signal_bars}   {lock}{net.ssid}{connected}"
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(64)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {"#0c4a6e" if net.in_use else "#151a24"};
                color: #f8fafc;
                font-size: 18px;
                font-weight: 600;
                text-align: left;
                padding: 12px 20px;
                border: 1px solid {"#0ea5e9" if net.in_use else "#243044"};
                border-radius: 14px;
            }}
            QPushButton:pressed {{ background-color: #1e293b; }}
            """
        )
        btn.clicked.connect(lambda _=False, n=net: self._on_network_tap(n))
        return btn

    def _on_network_tap(self, net: WifiNetwork):
        if self._busy:
            return
        if net.in_use:
            self.status_label.setText(f"Już połączono z „{net.ssid}”")
            return
        if net.is_secured:
            self._pending = net
            self.pass_ssid_label.setText(net.ssid)
            self.password_edit.clear()
            self.pass_error.setText("")
            self.btn_show_pass.setChecked(False)
            self._kb_mode = "letters"
            self._kb_shift = False
            self._rebuild_soft_keyboard()
            self.pages.setCurrentIndex(1)
            self.password_edit.setFocus()
            self.status_label.setText(f"Sieć chroniona · {net.ssid}")
            return
        self._connect_to(net.ssid, None)

    def _show_list(self):
        self._pending = None
        self.pages.setCurrentIndex(0)
        self.status_label.setText("Wybierz sieć z listy")

    def _toggle_password_visible(self, checked: bool):
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        self.btn_show_pass.setText("UKRYJ" if checked else "POKAŻ")

    def _submit_password(self):
        if self._busy or self._pending is None:
            return
        password = self.password_edit.text()
        if not password:
            self.pass_error.setText("Wpisz hasło")
            return
        self.pass_error.setText("")
        self._connect_to(self._pending.ssid, password)

    def _connect_to(self, ssid: str, password: Optional[str]):
        self._set_busy(True, f"Łączenie z „{ssid}”…")

        def job():
            return self._wifi.connect(ssid, password)

        self._start_worker(job, self._on_connect_ok, self._on_connect_err)

    def _on_connect_ok(self, result):
        ok, message = result
        self._set_busy(False, message)
        if ok:
            self._pending = None
            self.pages.setCurrentIndex(0)
            QTimer.singleShot(400, self._refresh)
        else:
            self.pass_error.setText(message)
            if self.pages.currentIndex() == 0:
                # sieć otwarta — komunikat w statusie wystarczy
                pass

    def _on_connect_err(self, message: str):
        self._set_busy(False, f"{message} — spróbuj ponownie")
        self.pass_error.setText(message)


# ---------------------------------------------------------------------------
# Kafelek
# ---------------------------------------------------------------------------
class TileButton(QPushButton):
    """Kafelek galerii z kolorowym akcentem i podtytułem."""

    def __init__(self, title: str, subtitle: str, accent: str, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 24)
        layout.setSpacing(8)

        accent_bar = QFrame()
        accent_bar.setFixedHeight(4)
        accent_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        accent_bar.setStyleSheet(
            f"background-color: {accent}; border-radius: 2px; border: none;"
        )
        layout.addWidget(accent_bar)

        name = QLabel(title)
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        name.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #ffffff; letter-spacing: 1.5px;"
            "background: transparent; border: none;"
        )
        layout.addWidget(name)

        sub = QLabel(subtitle)
        sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        sub.setStyleSheet(
            "font-size: 14px; color: #9ca3af; background: transparent; border: none;"
        )
        layout.addWidget(sub)
        layout.addStretch()

        self.setStyleSheet(
            f"""
            TileButton {{
                background-color: #1a1f2a;
                border: 2px solid #2a3344;
                border-radius: 18px;
                text-align: left;
            }}
            TileButton:hover {{
                background-color: #212836;
                border: 2px solid {accent};
            }}
            TileButton:pressed {{
                background-color: #151a24;
                border: 2px solid {accent};
            }}
            """
        )


# Indeksy stron w QStackedWidget (obok stałego sidebara)
PAGE_HOME = 0
PAGE_MENU = 1
PAGE_PLACEHOLDER = 2
PAGE_WIFI = 3


# ---------------------------------------------------------------------------
# Główne okno kiosku
# ---------------------------------------------------------------------------
class KioskMainWindow(QWidget):
    def __init__(self, mixer):
        super().__init__()
        self.mixer = mixer
        self.click_count = 0
        self._web_app_mode = False
        self._active_app = None  # "spotify" | "youtube" | None
        self._service_mode = False
        self._web_apps_shut_down = False

        self.dev_timer = QTimer(self)
        self.dev_timer.setInterval(3000)
        self.dev_timer.setSingleShot(True)
        self.dev_timer.timeout.connect(self.reset_dev_clicks)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)
        self.clock_timer.start(1000)

        self.spotify = ChromiumAppWindowManager(
            self,
            name="Spotify",
            url=SPOTIFY_URL,
            wm_class=SPOTIFY_WM_CLASS,
            profile_dir=SPOTIFY_PROFILE_DIR,
            debug_port=SPOTIFY_DEBUG_PORT,
            allowed_hosts=SPOTIFY_ALLOWED_HOSTS,
        )
        self.spotify.on_ready = lambda: self._on_web_app_ready("spotify")
        self.spotify.on_failed = lambda msg: self._on_web_app_failed("spotify", msg)

        self.youtube = ChromiumAppWindowManager(
            self,
            name="YouTube",
            url=YOUTUBE_URL,
            wm_class=YOUTUBE_WM_CLASS,
            profile_dir=YOUTUBE_PROFILE_DIR,
            debug_port=YOUTUBE_DEBUG_PORT,
            allowed_hosts=YOUTUBE_ALLOWED_HOSTS,
        )
        self.youtube.on_ready = lambda: self._on_web_app_ready("youtube")
        self.youtube.on_failed = lambda msg: self._on_web_app_failed("youtube", msg)

        self.keyboard = OnScreenKeyboard(
            focus_cb=self._focus_active_app,
            on_visibility=self._on_keyboard_visibility,
        )

        self._pending_volume = None
        self._vol_debounce = QTimer(self)
        self._vol_debounce.setSingleShot(True)
        self._vol_debounce.setInterval(VOLUME_DEBOUNCE_MS)
        self._vol_debounce.timeout.connect(self._apply_pending_volume)

        # Preload: Spotify najpierw, YouTube chwilę później (mniej szczytu CPU/RAM)
        QTimer.singleShot(1500, self.spotify.preload)
        QTimer.singleShot(3500, self.youtube.preload)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(SCREEN_W, SCREEN_H)
        self.setObjectName("kioskRoot")
        self.setStyleSheet(
            """
            #kioskRoot {
                background-color: #0b0e14;
                color: #ffffff;
                font-family: 'Segoe UI', 'DejaVu Sans', sans-serif;
            }
            """
        )

        # Sidebar jest pierwszym widgetem w QHBoxLayout — zawsze widoczny
        # (także na Wi-Fi / MENU). W trybie web-app okno zwęża się do sidebara.
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_sidebar())
        main_layout.addWidget(self._build_stack(), stretch=1)

        self.stack.currentChanged.connect(self._on_page_changed)
        self._on_page_changed(0)
        self._tick_clock()

    # ------------------------------------------------------------------ UI
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet(
            """
            #sidebar {
                background-color: #11161f;
                border-right: 1px solid #1e2633;
            }
            """
        )

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(14)

        self.dev_label = QLabel("VENA\nPILOT V")
        self.dev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dev_label.setMinimumHeight(64)
        self.dev_label.setStyleSheet(
            """
            QLabel {
                font-weight: 800;
                font-size: 15px;
                padding: 10px 6px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0ea5e9, stop:1 #6366f1);
                color: #ffffff;
                border-radius: 12px;
                letter-spacing: 1px;
            }
            """
        )
        layout.addWidget(self.dev_label)

        self.btn_back = QPushButton("←  POWRÓT")
        self.btn_back.setMinimumHeight(58)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setStyleSheet(
            """
            QPushButton {
                background-color: #0ea5e9;
                color: white;
                font-size: 15px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
            }
            QPushButton:pressed { background-color: #0284c7; }
            QPushButton:disabled {
                background-color: #1a2030;
                color: #4b5563;
            }
            """
        )
        self.btn_back.clicked.connect(self.go_back)
        layout.addWidget(self.btn_back)

        self.btn_app_home = QPushButton("⌂  START")
        self.btn_app_home.setMinimumHeight(48)
        self.btn_app_home.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_app_home.setToolTip("Wróć na stronę główną YouTube / Spotify (po reklamie)")
        self.btn_app_home.setStyleSheet(
            """
            QPushButton {
                background-color: #b45309;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
            }
            QPushButton:pressed { background-color: #92400e; }
            """
        )
        self.btn_app_home.clicked.connect(self.reset_active_web_app)
        self.btn_app_home.hide()
        layout.addWidget(self.btn_app_home)

        self.btn_keyboard = QPushButton("⌨  KLAWIATURA")
        self.btn_keyboard.setMinimumHeight(48)
        self.btn_keyboard.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_keyboard.setStyleSheet(
            """
            QPushButton {
                background-color: #1f2937;
                color: #d1d5db;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #374151;
                border-radius: 10px;
            }
            QPushButton:pressed { background-color: #111827; }
            """
        )
        self.btn_keyboard.clicked.connect(self.toggle_keyboard)
        layout.addWidget(self.btn_keyboard)

        vol_box = QFrame()
        vol_box.setObjectName("volBox")
        vol_box.setStyleSheet(
            """
            #volBox {
                background-color: #161c28;
                border: 1px solid #243044;
                border-radius: 14px;
            }
            """
        )
        vol_layout = QVBoxLayout(vol_box)
        vol_layout.setContentsMargins(8, 14, 8, 14)
        vol_layout.setSpacing(8)

        vol_label = QLabel("GŁOŚNOŚĆ")
        vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_label.setStyleSheet(
            "font-size: 11px; color: #8b95a8; font-weight: bold; letter-spacing: 1.5px;"
            "background: transparent; border: none;"
        )
        vol_layout.addWidget(vol_label)

        self.vol_val_label = QLabel("0%")
        self.vol_val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vol_val_label.setStyleSheet(
            "font-size: 20px; color: #38BDF8; font-weight: 800;"
            "background: transparent; border: none;"
        )
        vol_layout.addWidget(self.vol_val_label)

        self.slider = TouchSlider(Qt.Orientation.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setMinimumWidth(52)
        self.slider.setMinimumHeight(240)
        self.slider.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        initial_vol = self.mixer.get_volume()
        self.slider.blockSignals(True)
        self.slider.setValue(initial_vol)
        self.slider.blockSignals(False)
        self.vol_val_label.setText(f"{initial_vol}%")
        self.slider.valueChanged.connect(self.update_volume_and_label)
        self.slider.setStyleSheet(
            """
            QSlider::groove:vertical {
                background: #243044;
                width: 22px;
                border-radius: 11px;
            }
            QSlider::sub-page:vertical {
                background: #243044;
                border-radius: 11px;
            }
            QSlider::add-page:vertical {
                background: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                    stop:0 #0ea5e9, stop:1 #6366f1);
                border-radius: 11px;
            }
            QSlider::handle:vertical {
                background: #ffffff;
                height: 34px;
                width: 40px;
                margin: 0 -9px;
                border-radius: 10px;
                border: 3px solid #0ea5e9;
            }
            """
        )
        vol_layout.addWidget(
            self.slider, stretch=1, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        layout.addWidget(vol_box, stretch=1)

        self.clock_label = QLabel("--:--")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e5e7eb; padding-top: 4px;"
        )
        layout.addWidget(self.clock_label)

        status = QLabel("● ONLINE")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #34d399; letter-spacing: 1px;"
        )
        layout.addWidget(status)

        return sidebar

    def _build_stack(self) -> QStackedWidget:
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #0b0e14;")
        self.stack.addWidget(self._build_home_page())       # PAGE_HOME
        self.stack.addWidget(self._build_menu_page())       # PAGE_MENU
        self.stack.addWidget(self._build_placeholder_page())  # PAGE_PLACEHOLDER
        self.wifi_page = WifiPage()
        self.stack.addWidget(self.wifi_page)                # PAGE_WIFI
        return self.stack

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("homePage")
        page.setStyleSheet(
            """
            #homePage {
                background-color: #0b0e14;
            }
            """
        )
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)

        title = QLabel("Centrum multimedialne")
        title.setStyleSheet(
            "font-size: 30px; font-weight: 800; color: #f8fafc; letter-spacing: 0.3px;"
        )
        titles.addWidget(title)

        subtitle = QLabel("Wybierz moduł — panel dotykowy VENA")
        subtitle.setStyleSheet("font-size: 14px; color: #6b7280;")
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        layout.addLayout(header)
        layout.addSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(20)
        grid.setContentsMargins(0, 8, 0, 0)

        order = [
            ("SPOTIFY", 0, 0),
            ("YOUTUBE", 0, 1),
            ("EFEKTY", 1, 0),
            ("MENU", 1, 1),
        ]
        for key, row, col in order:
            theme = TILE_THEMES[key]
            btn = TileButton(key, theme["subtitle"], theme["accent"])
            if key == "SPOTIFY":
                btn.clicked.connect(self.open_spotify)
            elif key == "YOUTUBE":
                btn.clicked.connect(self.open_youtube)
            elif key == "MENU":
                btn.clicked.connect(lambda _=False: self.switch_to_page("MENU"))
            else:
                btn.clicked.connect(
                    lambda _=False, name=key: self.on_tile_click(name)
                )
            grid.addWidget(btn, row, col)
            grid.setRowStretch(row, 1)
            grid.setColumnStretch(col, 1)

        layout.addLayout(grid, stretch=1)
        return page

    def _build_menu_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 48, 56, 48)
        layout.setSpacing(18)

        badge = QLabel("SYSTEM")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #38BDF8; letter-spacing: 3px;"
        )
        layout.addWidget(badge)

        title = QLabel("Panel MENU")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 32px; font-weight: 800; color: #f8fafc;")
        layout.addWidget(title)

        subtitle = QLabel("Ustawienia urządzenia")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #6b7280;")
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        wifi_btn = QPushButton("Wi-Fi")
        wifi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        wifi_btn.setMinimumHeight(88)
        wifi_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #151a24;
                color: #f8fafc;
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 1px;
                border: 1px solid #243044;
                border-radius: 16px;
                text-align: left;
                padding-left: 28px;
            }
            QPushButton:pressed {
                background-color: #1e293b;
                border-color: #0ea5e9;
            }
            """
        )
        wifi_btn.clicked.connect(self.open_wifi)
        layout.addWidget(wifi_btn)

        # --- widok normalny ---
        self.menu_normal = QFrame()
        self.menu_normal.setStyleSheet(
            """
            QFrame {
                background-color: #151a24;
                border: 1px solid #243044;
                border-radius: 16px;
            }
            """
        )
        normal_layout = QVBoxLayout(self.menu_normal)
        normal_layout.setContentsMargins(28, 24, 28, 24)
        normal_layout.setSpacing(12)

        self.menu_info_label = QLabel(
            "W kolejnych aktualizacjach: adres IP oraz diagnostyka urządzenia."
        )
        self.menu_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.menu_info_label.setWordWrap(True)
        self.menu_info_label.setStyleSheet(
            "font-size: 15px; color: #9ca3af; background: transparent; border: none;"
        )
        normal_layout.addWidget(self.menu_info_label)

        self.version_label = QLabel("Vena Pilot V v1.1")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_label.setStyleSheet(
            "font-size: 13px; color: #6b7280; background: transparent; border: none;"
            "padding-top: 8px;"
        )
        self.version_label.mousePressEvent = self.on_dev_click
        normal_layout.addWidget(self.version_label)
        layout.addWidget(self.menu_normal)

        # --- widok trybu serwisowego (po PIN) ---
        self.menu_service = QFrame()
        self.menu_service.setStyleSheet(
            """
            QFrame {
                background-color: #1a1214;
                border: 1px solid #7f1d1d;
                border-radius: 16px;
            }
            """
        )
        service_layout = QVBoxLayout(self.menu_service)
        service_layout.setContentsMargins(20, 20, 20, 20)
        service_layout.setSpacing(12)

        svc_title = QLabel("TRYB SERWISOWY")
        svc_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        svc_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #f87171; letter-spacing: 2px;"
            "background: transparent; border: none;"
        )
        service_layout.addWidget(svc_title)

        btn_style = """
            QPushButton {
                background-color: #151a24;
                color: #f8fafc;
                font-size: 18px;
                font-weight: 800;
                border: 1px solid #243044;
                border-radius: 14px;
                min-height: 64px;
            }
            QPushButton:pressed { background-color: #1e293b; }
        """
        btn_danger = """
            QPushButton {
                background-color: #7f1d1d;
                color: #fef2f2;
                font-size: 18px;
                font-weight: 800;
                border: 1px solid #991b1b;
                border-radius: 14px;
                min-height: 64px;
            }
            QPushButton:pressed { background-color: #991b1b; }
        """

        self.btn_svc_reboot = QPushButton("RESET (sudo reboot)")
        self.btn_svc_reboot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_svc_reboot.setStyleSheet(btn_danger)
        self.btn_svc_reboot.clicked.connect(self._service_reboot)
        service_layout.addWidget(self.btn_svc_reboot)

        self.btn_svc_quit = QPushButton("Wyłącz aplikację → CLI")
        self.btn_svc_quit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_svc_quit.setStyleSheet(btn_style)
        self.btn_svc_quit.clicked.connect(self._service_quit_app)
        service_layout.addWidget(self.btn_svc_quit)

        self.btn_svc_exit = QPushButton("Wyjście z trybu serwisowego")
        self.btn_svc_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_svc_exit.setStyleSheet(btn_style)
        self.btn_svc_exit.clicked.connect(self._exit_service_mode)
        service_layout.addWidget(self.btn_svc_exit)

        self.service_status = QLabel("")
        self.service_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.service_status.setWordWrap(True)
        self.service_status.setStyleSheet(
            "font-size: 13px; color: #fbbf24; background: transparent; border: none;"
        )
        service_layout.addWidget(self.service_status)

        self.menu_service.hide()
        layout.addWidget(self.menu_service)
        layout.addStretch()
        return page

    def open_wifi(self):
        """Wi-Fi w obszarze treści — sidebar i POWRÓT zostają widoczne."""
        self._hide_web_apps()
        self.stack.setCurrentIndex(PAGE_WIFI)
        self.wifi_page.on_show()

    def _build_placeholder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 56, 56, 56)

        layout.addStretch()
        badge = QLabel("WKRÓTCE")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #fbbf24; letter-spacing: 3px;"
        )
        layout.addWidget(badge)

        self.placeholder_label = QLabel("Moduł w budowie")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setWordWrap(True)
        self.placeholder_label.setStyleSheet(
            "font-size: 28px; font-weight: 800; color: #f8fafc;"
        )
        layout.addWidget(self.placeholder_label)

        hint = QLabel("Dotknij POWRÓT, aby wrócić do galerii.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 14px; color: #6b7280; padding-top: 8px;")
        layout.addWidget(hint)
        layout.addStretch()
        return page

    # -------------------------------------------------------------- actions
    def update_volume_and_label(self, val: int):
        self.vol_val_label.setText(f"{val}%")
        self._pending_volume = val
        self._vol_debounce.start()

    def _apply_pending_volume(self):
        if self._pending_volume is None:
            return
        self.mixer.set_volume(self._pending_volume)
        self._pending_volume = None

    def _active_manager(self):
        if self._active_app == "youtube":
            return self.youtube
        if self._active_app == "spotify":
            return self.spotify
        return None

    def _focus_active_app(self):
        mgr = self._active_manager()
        if mgr:
            mgr.focus()

    def toggle_keyboard(self):
        self.keyboard.toggle()

    def _on_keyboard_visibility(self, open_: bool):
        for mgr in (self.spotify, self.youtube):
            mgr.set_keyboard_open(open_ and mgr is self._active_manager())
        self.btn_keyboard.setText("⌨  UKRYJ" if open_ else "⌨  KLAWIATURA")
        if open_:
            QTimer.singleShot(60, self._focus_active_app)

    # ------------------------------------------------------------------
    # Spotify / YouTube / sidebar mode
    # ------------------------------------------------------------------
    def _hide_web_apps(self):
        self.keyboard.hide()
        self.spotify.hide()
        self.youtube.hide()
        if self._web_app_mode:
            self._exit_sidebar_only_mode()
        self._active_app = None

    def open_spotify(self):
        self._open_web_app("spotify", self.spotify, "Uruchamianie Spotify…")

    def open_youtube(self):
        self._open_web_app("youtube", self.youtube, "Uruchamianie YouTube…")

    def _open_web_app(self, key: str, mgr: ChromiumAppWindowManager, loading_msg: str):
        # Już w tej app — START (wyciąga z reklamy bez wychodzenia do galerii)
        if self._active_app == key and (mgr.visible or self._web_app_mode):
            mgr.reset_to_home()
            return
        # Ukryj drugą aplikację; zwęż VENA od razu (WindowStaysOnTopHint
        # nie może przykrywać Chromium — to powodowało „trzeba kliknąć POWRÓT”).
        other = self.youtube if key == "spotify" else self.spotify
        other.hide()
        self.keyboard.hide()
        self._active_app = key
        self.placeholder_label.setText(loading_msg)
        self.stack.setCurrentIndex(PAGE_PLACEHOLDER)
        self.btn_back.setEnabled(True)
        self._enter_sidebar_only_mode()
        mgr.show()
        # Jeśli okno już było gotowe — dograj geometrię po skurczeniu sidebara
        QTimer.singleShot(80, mgr.raise_to_front)
        QTimer.singleShot(300, mgr.raise_to_front)

    def reset_active_web_app(self):
        """Przycisk START — powrót na youtube.com / open.spotify.com."""
        mgr = self._active_manager()
        if mgr is None:
            return
        self.placeholder_label.setText("Wracam na stronę startową…")
        mgr.reset_to_home()

    def _on_web_app_ready(self, key: str):
        if self._active_app != key:
            return
        self._enter_sidebar_only_mode()
        mgr = self.spotify if key == "spotify" else self.youtube
        mgr.raise_to_front()

    def _on_web_app_failed(self, key: str, message: str):
        if self._active_app not in (None, key):
            return
        self.keyboard.hide()
        self._exit_sidebar_only_mode()
        self._active_app = None
        self.placeholder_label.setText(message)
        self.stack.setCurrentIndex(PAGE_PLACEHOLDER)
        self.btn_back.setEnabled(True)

    def _enter_sidebar_only_mode(self):
        self._web_app_mode = True
        self.stack.hide()
        self.setFixedSize(SIDEBAR_WIDTH, SCREEN_H)
        self.move(0, 0)
        self.raise_()
        self.activateWindow()
        self.btn_back.setEnabled(True)
        self.btn_app_home.show()

    def _exit_sidebar_only_mode(self):
        self.keyboard.hide()
        self._web_app_mode = False
        self.setFixedSize(SCREEN_W, SCREEN_H)
        self.move(0, 0)
        self.stack.show()
        self.raise_()
        self.activateWindow()
        self.btn_app_home.hide()

    def go_back(self):
        """POWRÓT z sidebara — hierarchia: web-app → home; hasło Wi-Fi → lista → MENU → home."""
        if self._web_app_mode or self.spotify.visible or self.youtube.visible:
            self._hide_web_apps()
            self.stack.setCurrentIndex(PAGE_HOME)
            return

        idx = self.stack.currentIndex()
        if idx == PAGE_WIFI:
            if self.wifi_page.handle_back():
                return
            self.stack.setCurrentIndex(PAGE_MENU)
            return
        if idx in (PAGE_MENU, PAGE_PLACEHOLDER):
            if self._service_mode:
                self._exit_service_mode()
            self.stack.setCurrentIndex(PAGE_HOME)
            return
        self.stack.setCurrentIndex(PAGE_HOME)

    def switch_to_home_view(self):
        self._hide_web_apps()
        self.stack.setCurrentIndex(PAGE_HOME)

    def switch_to_page(self, name: str):
        self._hide_web_apps()
        if name == "MENU":
            self.stack.setCurrentIndex(PAGE_MENU)
        else:
            self.placeholder_label.setText(
                f"Moduł {name} jest w przygotowaniu"
            )
            self.stack.setCurrentIndex(PAGE_PLACEHOLDER)

    def on_tile_click(self, name: str):
        self.switch_to_page(name)

    def _on_page_changed(self, index: int):
        self.btn_back.setEnabled(index != PAGE_HOME or self._web_app_mode)

    def _tick_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M"))

    def on_dev_click(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._service_mode:
            event.accept()
            return
        self.click_count += 1
        if self.click_count == 1:
            self.dev_timer.start()
        if self.click_count >= 7:
            self.dev_timer.stop()
            self.click_count = 0
            self._show_pin_pad()
        event.accept()

    def _show_pin_pad(self):
        dialog = PinPadDialog(self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self._enter_service_mode()

    def _enter_service_mode(self):
        self._service_mode = True
        self.menu_normal.hide()
        self.menu_service.show()
        self.service_status.setText("")
        self.stack.setCurrentIndex(PAGE_MENU)

    def _exit_service_mode(self):
        self._service_mode = False
        self.menu_service.hide()
        self.menu_normal.show()
        self.service_status.setText("")
        self.click_count = 0

    def _service_reboot(self):
        """Pełny reset urządzenia (sudo reboot). Wymaga NOPASSWD w sudoers."""
        self.service_status.setText("Restartowanie systemu…")
        try:
            # -n: nie pytaj o hasło (kiosk: kiosk ALL=NOPASSWD: /sbin/reboot)
            subprocess.Popen(
                ["sudo", "-n", "reboot"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self.service_status.setText(
                f"Nie udało się uruchomić reboot — spróbuj ponownie.\n{exc}"
            )
            return
        # Jeśli sudo wymaga hasła / brak uprawnień, proces kończy się szybko
        QTimer.singleShot(2500, self._check_reboot_started)

    def _check_reboot_started(self):
        if not self._service_mode:
            return
        self.service_status.setText(
            "Reboot nie wystartował — dodaj w sudoers:\n"
            "kiosk ALL=(root) NOPASSWD: /sbin/reboot,/usr/sbin/reboot"
        )

    def _service_quit_app(self):
        """Wyłącz VENA → powrót do linii komend sesji X11."""
        self.shutdown_web_apps()
        QApplication.instance().quit()

    def shutdown_web_apps(self) -> None:
        """Zabij Spotify/YouTube Chromium + dokończ Wi-Fi (idempotentne)."""
        if self._web_apps_shut_down:
            return
        self._web_apps_shut_down = True
        try:
            self.wifi_page.shutdown()
        except Exception as exc:
            logger.debug("shutdown wifi: %s", exc)
        try:
            self.spotify.shutdown()
        except Exception as exc:
            logger.debug("shutdown spotify: %s", exc)
        try:
            self.youtube.shutdown()
        except Exception as exc:
            logger.debug("shutdown youtube: %s", exc)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown_web_apps()
        super().closeEvent(event)

    def reset_dev_clicks(self):
        self.click_count = 0


# ---------------------------------------------------------------------------
# Punkt startowy
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))

    mixer = HardwareAudioMixer()
    window = KioskMainWindow(mixer)
    app.aboutToQuit.connect(window.shutdown_web_apps)
    window.show()
    sys.exit(app.exec())
