"""Scheduler — penjadwalan harian: kirim jadwal pagi, polling presensi."""

import time
import logging
from datetime import datetime, timedelta
from src.ethol_client import EtholClient
from src.jadwal import JadwalService
from src.presensi import PresensiAuto
from src.notify import Notifier, kirim_jadwal, kirim_presensi
from src.utils import load_config, random_interval

log = logging.getLogger("scheduler")


class Scheduler:
    def __init__(self):
        self.cfg = load_config()
        self.client = EtholClient(
            token=self.cfg["token"],
            refresh_token=self.cfg["refresh_token"],
        )
        self.jadwal = JadwalService(self.client, self.cfg)
        self.presensi = PresensiAuto(self.client, self.cfg)
        self.notifier = Notifier(self.cfg)

    def jam_kirim_jadwal(self) -> time.struct_time:
        jam = self.cfg.get("jadwal_kirim", "06:30")
        h, m = map(int, jam.split(":"))
        now = datetime.now()
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        return target.timetuple()

    def jadwal_hari_ini(self):
        """Kirim jadwal pagi."""
        log.info("mengirim jadwal pagi...")
        kirim_jadwal(self.notifier, self.jadwal)

    def polling_presensi(self, kuliah: int, jenis_schema: int = 4, max_poll: int = 300):
        """Poll presensi sampai berhasil atau batas habis."""
        log.info("mulai polling presensi kuliah=%s", kuliah)
        result = self.presensi.jalan_terus(kuliah, jenis_schema, max_poll)
        if result:
            # Cari nama MK dari config
            nama = next(
                (k["nama"] for k in self.cfg["kuliah"] if k["nomor"] == kuliah),
                str(kuliah),
            )
            kirim_presensi(self.notifier, result, nama)
        else:
            log.warning("presensi tidak ditemukan/timeout")

    def jalan(self):
        """Loop utama — cek tiap 30 detik."""
        log.info("scheduler started")
        last_jadwal = None
        while True:
            now = datetime.now()
            hari_ini = now.date()

            # Kirim jadwal pagi (sekali sehari)
            if last_jadwal != hari_ini and now.hour >= 6:
                self.jadwal_hari_ini()
                last_jadwal = hari_ini

            # Cek presensi untuk semua kuliah
            for k in self.cfg["kuliah"]:
                try:
                    self.presensi.sekali(k["nomor"], k["jenisSchema"])
                except Exception as e:
                    log.warning("presensi check kuliah %s: %s", k["nomor"], e)

            # Tunggu random 30-60 detik sebelum cek lagi
            wait = random_interval(30, 60)
            log.debug("next check in %.0fs", wait)
            time.sleep(wait)