"""ETHOL Client — wrapper API untuk ethol.pens.ac.id."""

import json
import time
import logging
import requests
from pathlib import Path

log = logging.getLogger("ethol")


class EtholClient:
    BASE = "https://ethol.pens.ac.id"

    def __init__(self, token: str, refresh_token: str, timeout: int = 15):
        self.token = token
        self.refresh_token = refresh_token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        })

    # ---------- auth ----------

    def _cookies(self):
        return {"token": self.token}

    def validasi_token(self) -> dict:
        r = self.session.get(
            f"{self.BASE}/api/auth/validasi-token",
            cookies=self._cookies(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def refresh(self) -> bool:
        """Refresh token. Return True if success."""
        r = self.session.post(
            f"{self.BASE}/api/auth/refresh",
            cookies={"refresh_token": self.refresh_token},
            json={}, timeout=self.timeout,
        )
        if r.status_code != 200:
            log.warning("refresh failed: %s %s", r.status_code, r.text[:200])
            return False
        data = r.json()
        if not data.get("sukses"):
            log.warning("refresh not success: %s", data)
            return False
        new_token = data.get("token")
        if new_token:
            self.token = new_token
            log.info("token refreshed, expires in ~15m")
        return True

    def ensure_auth(self) -> bool:
        """Cek token; refresh jika expired; fallback login jika perlu.

        Return True jika auth OK.
        """
        try:
            self.validasi_token()
            return True
        except Exception:
            log.info("token expired, attempting refresh...")
            if self.refresh():
                return True

            # Fallback: coba login ulang
            log.info("refresh gagal, attempting auto-login...")
            from src.login import EtholLogin
            import os
            login = EtholLogin(
                username=os.getenv("ETHOL_LOGIN_USERNAME", ""),
                password=os.getenv("ETHOL_LOGIN_PASSWORD", ""),
            )
            hasil = login.login()
            if hasil and hasil.get("token"):
                self.token = hasil["token"]
                self.refresh_token = hasil.get("refresh_token") or self.refresh_token
                self._simpan_state()
                log.info("auto-login sukses, token baru tersimpan di state.json")
                return True
            return False

    def _simpan_state(self):
        """Simpan token+refresh_token ke config/state.json."""
        from src.utils import load_state, save_state
        state = load_state()
        state["token"] = self.token
        state["refresh_token"] = self.refresh_token
        save_state(state)

    # ---------- generic ----------

    def get(self, path: str, params: dict | None = None) -> dict | list:
        r = self.session.get(
            f"{self.BASE}{path}",
            params=params, cookies=self._cookies(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> dict | list:
        r = self.session.post(
            f"{self.BASE}{path}",
            json=body, cookies=self._cookies(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    # ---------- jadwal ----------

    def jadwal_hari_ini(self, kuliahs: list[dict], tahun: int, semester: int) -> list[dict]:
        body = {"kuliahs": kuliahs, "tahun": tahun, "semester": semester}
        return self.post("/api/kuliah/hari-kuliah-in", body)

    def detail_kuliah(self, kuliah: int, jenis_schema: int = 4) -> dict:
        data = self.get("/api/kuliah/by-kuliah-js", {"kuliah": kuliah, "jenisSchema": jenis_schema})
        return data[0] if data else {}

    def peserta_kuliah(self, kuliah: int, jenis_schema: int = 4) -> list[dict]:
        return self.get("/api/kuliah/peserta-kuliah", {"kuliah": kuliah, "jenis_schema": jenis_schema})

    # ---------- presensi ----------

    def presensi_aktif(self, kuliah: int, jenis_schema: int = 4) -> dict | None:
        """Return dict {kuliah, key, jenisSchema, open} atau None jika tidak ada."""
        data = self.get(
            "/api/presensi/aktif-kuliah",
            {"kuliah": kuliah, "jenis_schema": jenis_schema},
        )
        return data[0] if data else None

    def presensi_terakhir(self, kuliah: int, jenis_schema: int = 4) -> dict:
        return self.get(
            "/api/presensi/terakhir-kuliah",
            {"kuliah": kuliah, "jenis_schema": jenis_schema},
        )

    def riwayat_presensi(self, kuliah: int, nomor: int, jenis_schema: int = 4) -> list[dict]:
        return self.get(
            "/api/presensi/riwayat",
            {"kuliah": kuliah, "jenis_schema": jenis_schema, "nomor": nomor},
        )

    def submit_presensi(self, kuliah: int, mahasiswa: int, key: str, jenis_schema: int = 4) -> dict:
        body = {
            "kuliah": kuliah,
            "jenis_schema": jenis_schema,
            "mahasiswa": mahasiswa,
            "key": key,
            "kuliah_asal": kuliah,
        }
        return self.post("/api/presensi/mahasiswa", body)

    # ---------- daftar kuliah ----------

    def daftar_kuliah(self, tahun: int, semester: int) -> list[dict]:
        """Ambil semua kuliah yang diambil semester ini.

        Return list: [{nomor, matakuliah, dosen, jenisSchema, ...}]
        """
        return self.get("/api/kuliah", {"tahun": tahun, "semester": semester})

    # ---------- lainnya ----------

    def zoom_dosen(self, dosen: int) -> dict:
        return self.get("/api/conference-lainnya", {"dosen": dosen})

    def info_dosen(self, nomor: int) -> dict:
        data = self.get("/api/pegawai/dosenemailpens", {"nomor": nomor})
        return data[0] if data else {}

    def notifikasi_belum_baca(self) -> dict:
        return self.get("/api/notifikasi/mahasiswa-belum-baca")