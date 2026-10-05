"""Logic presensi otomatis — polling aktif-kuliah dengan interval random."""

import time
import logging
from src.ethol_client import EtholClient
from src.utils import random_interval

log = logging.getLogger("presensi")


class PresensiAuto:
    def __init__(self, client: EtholClient, config: dict):
        self.client = client
        self.cfg = config
        self.mahasiswa = (config.get("mahasiswa") or {}).get("nomor")
        self.lo, self.hi = config.get("presensi_interval", [5, 60])

    def _mahasiswa_nomor(self) -> int | None:
        """Nomor mahasiswa; resolve dari token/state bila belum diketahui."""
        if self.mahasiswa:
            return self.mahasiswa
        mhs = self.client.sync_identitas()
        self.mahasiswa = mhs.get("nomor")
        return self.mahasiswa

    def sekali(self, kuliah: int, jenis_schema: int = 4) -> dict | None:
        """Cek & submit presensi sekali. Return result dict atau None."""
        if not self.client.ensure_auth():
            log.error("auth gagal")
            return None

        info = self.client.presensi_aktif(kuliah, jenis_schema)
        if not info or not info.get("open"):
            return None

        key = info.get("key")
        log.info("presensi aktif! kuliah=%s key=%s", kuliah, key)

        mahasiswa = self._mahasiswa_nomor()
        if not mahasiswa:
            log.error("nomor mahasiswa tidak diketahui (set ETHOL_NOMOR atau jalankan login.py)")
            return {"sukses": False, "pesan": "nomor mahasiswa tidak diketahui", "key": key}

        try:
            hasil = self.client.submit_presensi(
                kuliah=kuliah,
                mahasiswa=mahasiswa,
                key=key,
                jenis_schema=jenis_schema,
            )
            log.info("submit hasil: %s", hasil)
            return {"sukses": hasil.get("sukses"), "pesan": hasil.get("pesan"), "key": key}
        except Exception as e:
            log.error("submit gagal: %s", e)
            return {"sukses": False, "pesan": str(e), "key": key}

    def jalan_terus(self, kuliah: int, jenis_schema: int = 4, max_poll: int = 200):
        """Poll terus sampai presensi berhasil atau max_poll habis."""
        sudah = set()  # key yang sudah disubmit
        for i in range(max_poll):
            result = self.sekali(kuliah, jenis_schema)
            if result and result["sukses"] and result["key"] not in sudah:
                sudah.add(result["key"])
                log.info("PRESENSI BERHASIL ✅ key=%s", result["key"])
                return result
            # Random interval
            wait = random_interval(self.lo, self.hi)
            log.debug("poll #%d, waiting %.1fs...", i + 1, wait)
            time.sleep(wait)
        return None