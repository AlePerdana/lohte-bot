#!/usr/bin/env python3
"""Deteksi + presensi otomatis, HANYA untuk matkul hari ini dan HANYA dalam
rentang jam kuliah hari itu.

Aturan:
  - Ambil jadwal hari ini (POST /api/kuliah/hari-kuliah-in) untuk semua matkul.
  - Poll hanya matkul yang punya jadwal hari ini.
  - Poll hanya dalam window [jam_awal kuliah paling awal, jam_akhir kuliah
    paling akhir] hari itu. Di luar window -> diam (hemat request, aman).
  - Matkul yang sudah presensi sukses (per key sesi) berhenti di-poll.
  - Interval random antar poll.

Manual di luar jam: jalankan `detect_presensi.py --auto` (sekali cek semua).

Usage:
  .venv/bin/python detect_presensi.py --loop --auto
  .venv/bin/python detect_presensi.py            # sekali cek semua matkul
"""

import sys
import time
import argparse
from datetime import datetime

from src.utils import setup_logging, load_config, random_interval
from src.ethol_client import EtholClient
from src.presensi import PresensiAuto
from src.notify import Notifier, kirim_presensi


def cek_semua(client, cfg, kuliahs=None):
    """Cek daftar matkul -> return yang presensinya open."""
    if kuliahs is None:
        kuliahs = cfg["kuliah"]
    hasil = []
    for k in kuliahs:
        try:
            if not client.ensure_auth():
                print("  [!] auth gagal untuk kuliah %s" % k["nomor"])
                continue
            info = client.presensi_aktif(k["nomor"], k["jenisSchema"])
            if info and info.get("open"):
                hasil.append({
                    "kuliah": k["nomor"],
                    "nama": k.get("nama", str(k["nomor"])),
                    "key": info.get("key"),
                    "open": info.get("open"),
                    "jenisSchema": info.get("jenisSchema") or k.get("jenisSchema", 4),
                })
        except Exception as e:
            print("  [x] kuliah %s: %s: %s" % (k["nomor"], type(e).__name__, e))
    return hasil


def jadwal_hari_ini(client, cfg):
    """Return list jadwal hari ini: [{kuliah, jam_awal, jam_akhir, ...}]."""
    kuliahs = [{"nomor": k["nomor"], "jenisSchema": k.get("jenisSchema", 4)}
               for k in cfg["kuliah"]]
    try:
        if not client.ensure_auth():
            print("  [!] auth gagal saat ambil jadwal")
            return []
        return client.jadwal_hari_ini(kuliahs, cfg["tahun"], cfg["semester"]) or []
    except Exception as e:
        print("  [x] gagal ambil jadwal hari ini: %s" % e)
        return []


def window_hari_ini(jadwal):
    """Gabungkan semua jadwal hari ini jadi satu window jam:
    (menit_awal_terkecil, menit_akhir_terbesar). None jika tidak ada jadwal."""
    if not jadwal:
        return None
    awal = []
    akhir = []
    for j in jadwal:
        try:
            h, m = map(int, j["jam_awal"].split(":"))
            awal.append(h * 60 + m)
            h2, m2 = map(int, j["jam_akhir"].split(":"))
            akhir.append(h2 * 60 + m2)
        except Exception:
            continue
    if not awal or not akhir:
        return None
    return (min(awal), max(akhir))


def matkul_hari_ini(jadwal, cfg):
    """Filter config kuliah -> hanya yang ada jadwal hari ini."""
    ids = {j["kuliah"] for j in jadwal}
    return [k for k in cfg["kuliah"] if k["nomor"] in ids]


def main():
    parser = argparse.ArgumentParser(description="Deteksi presensi terbuka")
    parser.add_argument("--loop", action="store_true", help="Loop terus")
    parser.add_argument("--auto", action="store_true", help="Deteksi + submit otomatis")
    parser.add_argument("--interval", type=str, default="30,90",
                        help="min,max detik (default 30,90)")
    parser.add_argument("--all", action="store_true",
                        help="Poll semua matkul tanpa filter jadwal/hari ini")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config()
    client = EtholClient(cfg["token"], cfg["refresh_token"])

    lo, hi = map(int, args.interval.split(","))
    print("[*] Presensi otomatis (interval %d-%ds)" % (lo, hi))

    sudah_submit = set()   # key yang sudah disubmit (hindari dobel)
    sudah_sukses = set()   # nomor kuliah yang sudah presensi sukses -> stop poll

    while True:
        # --- tentukan target polling ---
        if args.all:
            target = cfg["kuliah"]
            win = None
            judul = "SEMUA matkul (tanpa filter)"
        else:
            jadwal = jadwal_hari_ini(client, cfg)
            target = matkul_hari_ini(jadwal, cfg)
            win = window_hari_ini(jadwal)
            judul = "%d matkul hari ini" % len(target)

        now = datetime.now()
        menit_now = now.hour * 60 + now.minute
        stamp = now.strftime("%H:%M:%S")

        # --- cek apakah sekarang dalam window jam kuliah ---
        if win is None:
            if not args.all:
                print("[%s] - tidak ada kuliah hari ini, idle" % stamp)
        elif not (win[0] <= menit_now <= win[1] + 5):
            # di luar rentang jam kuliah -> diam
            if not args.all:
                j0 = "%02d:%02d" % divmod(win[0], 60)
                j1 = "%02d:%02d" % divmod(win[1], 60)
                print("[%s] - di luar jam kuliah (%s-%s), idle" % (stamp, j0, j1))
        else:
            # --- dalam window: poll target yang belum selesai ---
            aktif = [k for k in target if k["nomor"] not in sudah_sukses]
            if aktif:
                open_list = cek_semua(client, cfg, aktif)
                if not open_list:
                    print("[%s] - %d matkul dipantau, belum ada presensi terbuka"
                          % (stamp, len(aktif)))
                else:
                    print("[%s] - %d presensi TERBUKA:" % (stamp, len(open_list)))
                    for o in open_list:
                        print("   [+] %s (kuliah %s) key=%s" % (o["nama"], o["kuliah"], o["key"]))

                        if args.auto and o["key"] not in sudah_submit:
                            pres = PresensiAuto(client, cfg)
                            result = pres.sekali(o["kuliah"], o["jenisSchema"])
                            if result and result.get("sukses"):
                                sudah_submit.add(o["key"])
                                sudah_sukses.add(o["kuliah"])
                                notifier = Notifier(cfg)
                                kirim_presensi(notifier, result, o["nama"])
                                print("      [OK] PRESENSI BERHASIL - %s berhenti dipoll" % o["nama"])
                            elif result and not result.get("sukses"):
                                # kemungkinan sudah pernah -> tandai selesai
                                pesan = (result.get("pesan") or "")
                                if "sudah melakukan" in pesan:
                                    sudah_sukses.add(o["kuliah"])
                                    print("      [OK] sudah tercatat sebelumnya -> stop poll %s" % o["nama"])
            else:
                print("[%s] - semua matkul hari ini sudah presensi, idle" % stamp)

        if not args.loop:
            break

        wait = random_interval(lo, hi)
        time.sleep(wait)


if __name__ == "__main__":
    main()