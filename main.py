#!/usr/bin/env python3
"""ETHOL Bot — Entry point.

Usage:
  python main.py --test      # Test sekali jalan
  python main.py --daemon    # Jalankan scheduler terus-menerus
  python main.py --presensi  # Poll presensi saja
  python main.py --jadwal    # Kirim jadwal saja
"""

import sys
import argparse
from src.utils import setup_logging, load_config
from src.ethol_client import EtholClient
from src.jadwal import JadwalService
from src.presensi import PresensiAuto
from src.notify import Notifier, kirim_jadwal
from src.scheduler import Scheduler


def test():
    """Test semua endpoint sekali jalan."""
    cfg = load_config()
    client = EtholClient(cfg["token"], cfg["refresh_token"])

    print("=== Auth ===")
    print(client.validasi_token())

    print("\n=== Jadwal ===")
    jadwal = JadwalService(client, cfg)
    print(jadwal.format_pesan())

    print("\n=== Detail MK ===")
    for d in jadwal.detail_semua():
        print(f"  {d['nama']} — {d['dosen']} ({d['kelas']})")

    print("\n=== Presensi Aktif ===")
    for k in cfg["kuliah"]:
        info = client.presensi_aktif(k["nomor"], k["jenisSchema"])
        print(f"  kuliah {k['nomor']}: {info}")


def presensi_saja():
    """Poll presensi semua kuliah sampai berhasil."""
    cfg = load_config()
    sched = Scheduler()
    for k in cfg["kuliah"]:
        sched.polling_presensi(k["nomor"], k["jenisSchema"])


def jadwal_saja():
    cfg = load_config()
    client = EtholClient(cfg["token"], cfg["refresh_token"])
    jadwal = JadwalService(client, cfg)
    notifier = Notifier(cfg)
    kirim_jadwal(notifier, jadwal)


def daemon():
    sched = Scheduler()
    sched.jalan()


def main():
    parser = argparse.ArgumentParser(description="ETHOL Bot")
    parser.add_argument("--test", action="store_true", help="Test semua endpoint")
    parser.add_argument("--daemon", action="store_true", help="Jalankan scheduler")
    parser.add_argument("--presensi", action="store_true", help="Poll presensi saja")
    parser.add_argument("--jadwal", action="store_true", help="Kirim jadwal saja")
    args = parser.parse_args()

    setup_logging()

    if args.test:
        test()
    elif args.presensi:
        presensi_saja()
    elif args.jadwal:
        jadwal_saja()
    elif args.daemon:
        daemon()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()