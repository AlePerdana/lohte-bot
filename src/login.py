"""Auto-login ke ETHOL via CAS (login.pens.ac.id).

Alur:
  1. GET  login.pens.ac.id/cas/login       -> ambil JSESSIONID + lt (hidden field)
  2. POST login.pens.ac.id/cas/login       -> username+password+lt -> 302 + ticket
  3. GET  ethol/api/auth/cas-callback?ticket=... -> token + refresh_token (7 hari)
"""

import re
import os
import logging
import requests

log = logging.getLogger("login")

ETHOL = "https://ethol.pens.ac.id"
CAS = "https://login.pens.ac.id"
CAS_LOGIN_URL = CAS + "/cas/login"
CAS_SERVICE = ETHOL + "/api/auth/cas-callback"


class EtholLogin:
    def __init__(self, username, password, timeout=20):
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0",
        })

    @staticmethod
    def _extract_lt(html):
        m = re.search(r'name="lt"\s+value="([^"]+)"', html)
        return m.group(1) if m else None

    def login(self):
        """Full CAS login flow. Return dict {token, refresh_token} atau None."""
        if not self.username or not self.password:
            log.error("ETHOL_LOGIN_USERNAME / ETHOL_LOGIN_PASSWORD belum diisi di .env")
            return None

        try:
            log.info("step 1/4: GET CAS login form...")
            r1 = self.session.get(CAS_LOGIN_URL, params={"service": CAS_SERVICE}, timeout=self.timeout)
            r1.raise_for_status()
            lt = self._extract_lt(r1.text)
            if not lt:
                log.error("field lt tidak ditemukan di form CAS")
                return None
            log.info("lt=...%s", lt[-12:])

            log.info("step 2/4: POST credentials...")
            pw = self.password
            r2 = self.session.post(
                CAS_LOGIN_URL,
                params={"service": CAS_SERVICE},
                data={
                    "username": self.username,
                    "password": pw,
                    "lt": lt,
                    "_eventId": "submit",
                    "submit": "LOGIN",
                },
                allow_redirects=False,
                timeout=self.timeout,
            )

            loc = r2.headers.get("Location", "")
            if r2.status_code in (301, 302, 303, 307, 308) and "ticket=" in loc:
                ticket = loc.split("ticket=")[1].split("&")[0]
            else:
                err = re.search(r'class="[^"]*error[^"]*"[^>]*>([^<]+)<', r2.text, re.I)
                msg = err.group(1).strip() if err else ("login page (kredensial salah?)" if r2.status_code == 200 else "no ticket in redirect")
                log.error("login gagal: %s (status=%s loc=%s)", msg, r2.status_code, loc[:200])
                return None
            log.info("ticket=...%s", ticket[-12:])

            log.info("step 3/4: exchange ticket di ETHOL...")
            r3 = self.session.get(
                ETHOL + "/api/auth/cas-callback",
                params={"ticket": ticket},
                allow_redirects=False,
                timeout=self.timeout,
            )
            jar = dict(r3.cookies)
            token = jar.get("token", "")
            refresh = jar.get("refresh_token", "")
            if not token:
                try:
                    data = r3.json()
                    token = data.get("token") or data.get("accessToken") or ""
                    refresh = data.get("refresh_token") or ""
                except Exception:
                    pass
            if not token:
                log.error("token tidak didapat. status=%s body=%s", r3.status_code, r3.text[:300])
                return None

            log.info("login sukses! token=...%s refresh=...%s", token[-16:], (refresh or "")[-12:])
            return {"token": token, "refresh_token": refresh or ""}

        except requests.HTTPError as e:
            body = e.response.text[:300] if e.response is not None else ""
            log.error("HTTP error: %s - %s", e, body)
            return None
        except Exception as e:
            log.error("login gagal: %s: %s", type(e).__name__, e)
            return None


def simpan_state(token, refresh, mahasiswa=None):
    """Simpan token + refresh_token ke config/state.json."""
    from src.utils import load_state, save_state
    state = load_state()
    state["token"] = token
    state["refresh_token"] = refresh
    if mahasiswa:
        state["mahasiswa"] = mahasiswa
    save_state(state)
    log.info("token disimpan ke config/state.json")


def login_dan_simpan():
    """Login pakai kredensial .env, simpan hasil ke state.json. Return hasil."""
    pw2 = os.environ.get("ETHOL_LOGIN_PASSWORD", "")
    login = EtholLogin(
        username=os.environ.get("ETHOL_LOGIN_USERNAME", ""),
        password=pw2        )
    hasil = login.login()
    if hasil:
        from src.ethol_client import EtholClient
        client = EtholClient(hasil["token"], hasil["refresh_token"])
        identitas = {}
        try:
            identitas = client.validasi_token()
        except Exception as e:
            log.warning("validasi-token gagal setelah login: %s", e)
        mahasiswa = {
            "nomor": identitas.get("nomor"),
            "nipnrp": identitas.get("nipnrp"),
            "nama": identitas.get("nama"),
        }
        simpan_state(hasil["token"], hasil["refresh_token"], mahasiswa)
    return hasil
