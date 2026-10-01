#!/usr/bin/env python3
"""Smart scheduler presensi otomatis ETHOL.

Siklus:
  1. Ambil jadwal hari ini, urutkan per matkul berdasarkan jam mulai.
  2. Per matkul:
     - SLEEP sampai (jam_mulai - warmup) sebelum mulai scan.
     - SCAN presensi tiap interval random (5-10 menit default).
     - STOP matkul jika: presensi sukses / server "sudah melakukan" /
       jam kuliah selesai.
  3. Setelah semua matkul hari ini habis -> self-stop service
     (agar tidak jalan di background saat tidak ada kuliah).

Di luar jam matkul, tidak ada request sama sekali (hemat & aman dari blokir).

Manual (di luar window service): .venv/bin/python detect_presensi.py --auto
"""

import sys
import time
import argparse
import subprocess
from datetime import datetime, timedelta

from src.utils import setup_logging, load_config, random_interval
from src.ethol_client import EtholClient
from src.presensi import PresensiAuto
from src.notify import Notifier, kirim_presensi


# ---------- helpers jadwal ----------

def jadwal_hari_ini(client, cfg, max_retry=5):
    """Return jadwal HARI INI saja, atau None jika GAGAL (bukan kosong).

    Return None = gagal ambil jadwal (network/auth error) -> caller harus retry,
    BUKAN anggap "tidak ada kuliah". Return [] = benar-benar tidak ada kuliah
    hari ini (valid) -> caller boleh self-stop.

    Endpoint /api/kuliah/hari-kuliah-in ternyata mengembalikan SEMUA jadwal
    semester (Senin-Jumat) tanpa filter hari. Kita filter sendiri pakai field
    `nomor_hari` (1=Senin .. 5=Jum'at) sesuai hari ini.
    """
    kuliahs = [{"nomor": k["nomor"], "jenisSchema": k.get("jenisSchema", 4)}
               for k in cfg["kuliah"]]

    last_err = None
    for attempt in range(1, max_retry + 1):
        try:
            if not client.ensure_auth():
                last_err = "auth gagal"
                print("[!] auth gagal saat ambil jadwal (attempt %d/%d)" % (attempt, max_retry))
            else:
                semua = client.jadwal_hari_ini(kuliahs, cfg["tahun"], cfg["semester"]) or []

                # filter hari ini: Python isoweekday() -> 1=Senin .. 7=Minggu
                hari_ini = datetime.now().isoweekday()
                hasil = [x for x in semua if int(x.get("nomor_hari", 0)) == hari_ini]
                print("[i] jadwal: %d total semester, %d hari ini (nomor_hari=%d)"
                      % (len(semua), len(hasil), hari_ini))
                return hasil
        except Exception as e:
            last_err = str(e)
            print("[x] gagal ambil jadwal hari ini (attempt %d/%d): %s"
                  % (attempt, max_retry, e))

        if attempt < max_retry:
            backoff = min(30 * attempt, 120)
            print("[.] retry jadwal dalam %ds..." % backoff)
            time.sleep(backoff)

    print("[X] jadwal gagal total setelah %d percobaan: %s -> keep alive (retry nanti)"
          % (max_retry, last_err))
    return None  # GAGAL, bukan kosong


def parse_menit(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def fmt(menit):
    return "%02d:%02d" % divmod(int(menit), 60)


def nama_mk(cfg, nomor):
    for k in cfg["kuliah"]:
        if k["nomor"] == nomor:
            return k.get("nama", str(nomor))
    return str(nomor)


# ---------- inti: proses satu matkul ----------

def proses_matkul(client, cfg, jadwal, auto, lo, hi, sudah_submit):
    """Poll satu matkul sampai selesai. Return True jika sukses/tercatat."""
    nomor = jadwal["kuliah"]
    nama = nama_mk(cfg, nomor)
    jenis = next((k.get("jenisSchema", 4) for k in cfg["kuliah"] if k["nomor"] == nomor), 4)

    start = parse_menit(jadwal["jam_awal"])
    end = parse_menit(jadwal["jam_akhir"])
    pres = PresensiAuto(client, cfg)

    print("[*] Matkul: %s (%s-%s)" % (nama, jadwal["jam_awal"], jadwal["jam_akhir"]))

    while True:
        menit_now = datetime.now().hour * 60 + datetime.now().minute
        if menit_now > end:
            print("[=] %s: jam kuliah selesai (%s), stop." % (nama, jadwal["jam_akhir"]))
            return False

        try:
            info = client.presensi_aktif(nomor, jenis)
        except Exception as e:
            print("[x] %s: cek gagal: %s" % (nama, e))
            info = None

        if info and info.get("open"):
            key = info.get("key")
            print("[+] %s: presensi TERBUKA key=%s" % (nama, key))
            if auto and key not in sudah_submit:
                result = pres.sekali(nomor, jenis)
                if result and result.get("sukses"):
                    sudah_submit.add(key)
                    print("[OK] %s: PRESENSI BERHASIL" % nama)
                    kirim_presensi(Notifier(cfg), result, nama)
                    return True
                elif result and not result.get("sukses"):
                    pesan = result.get("pesan") or ""
                    if "sudah melakukan" in pesan:
                        sudah_submit.add(key)
                        print("[OK] %s: sudah tercatat sebelumnya" % nama)
                        return True
                    else:
                        print("[?] %s: %s" % (nama, pesan))
        else:
            print("[-] %s: belum buka (scan berikutnya %d-%ds)" % (nama, lo, hi))

        time.sleep(random_interval(lo, hi))


# ---------- main loop ----------

def main():
    ap = argparse.ArgumentParser(description="ETHOL smart scheduler")
    ap.add_argument("--loop", action="store_true", help="loop sepanjang hari")
    ap.add_argument("--auto", action="store_true", help="submit otomatis")
    ap.add_argument("--interval", default="300,600",
                    help="interval scan saat jam kuliah, detik (default 300,600 = 5-10m)")
    ap.add_argument("--warmup", type=int, default=15,
                    help="mulai scan N menit sebelum jam mulai (default 15)")
    ap.add_argument("--all", action="store_true", help="tanpa filter jadwal")
    args = ap.parse_args()

    setup_logging()
    cfg = load_config()
    client = EtholClient(cfg["token"], cfg["refresh_token"])
    lo, hi = map(int, args.interval.split(","))

    print("[*] ETHOL smart scheduler (scan %d-%ds)" % (lo, hi))

    sudah_submit = set()

    while True:
        jadwal = jadwal_hari_ini(client, cfg)

        if jadwal is None:
            # gagal ambil jadwal (network/auth) -> JANGAN self-stop, retry nanti
            print("[=] Gagal ambil jadwal -> coba lagi dalam 5 menit...")
            time.sleep(300)
            continue

        if not jadwal:
            # valid: memang tidak ada kuliah hari ini -> self-stop
            print("[=] Tidak ada kuliah hari ini -> self-stop.")
            self_stop()
            return

        # urutkan berdasarkan jam mulai
        jadwal.sort(key=lambda j: parse_menit(j["jam_awal"]))
        print("[*] Jadwal hari ini (%d matkul):" % len(jadwal))
        for j in jadwal:
            print("    - %s (%s-%s)" % (nama_mk(cfg, j["kuliah"]), j["jam_awal"], j["jam_akhir"]))

        for j in jadwal:
            nomor = j["kuliah"]
            start = parse_menit(j["jam_awal"]) - args.warmup
            end = parse_menit(j["jam_akhir"])

            # sleep sampai waktu mulai scan
            while True:
                now = datetime.now()
                menit_now = now.hour * 60 + now.minute
                if menit_now >= start:
                    break
                wait_sec = (start - menit_now) * 60
                # jangan sleep lebih dari 10 menit sekaligus (biar bisa re-check jadwal)
                chunk = min(wait_sec, 600)
                print("[z] %s mulai %s -> sleep %ds" % (nama_mk(cfg, nomor), fmt(start), chunk))
                time.sleep(chunk)

            # proses sampai selesai
            proses_matkul(client, cfg, j, args.auto, lo, hi, sudah_submit)

        # semua jadwal hari ini selesai
        if not args.loop:
            print("[=] Semua matkul hari ini selesai -> exit.")
            return

        # loop: re-check jadwal (mungkin ada matkul baru / besok)
        # kalau sudah lewat tengah malam, stop saja
        now = datetime.now()
        if now.hour >= 23 or now.hour < 4:
            print("[=] Lewat tengah malam -> self-stop.")
            self_stop()
            return
        print("[=] Semua jadwal hari ini selesai, re-check dalam 10 menit...")
        time.sleep(600)


def self_stop():
    """Matikan service systemd diri sendiri."""
    try:
        subprocess.run(
            ["systemctl", "--user", "stop", "ethol-bot.service"],
            check=False, timeout=15,
        )
        print("[=] Service ethol-bot dihentikan (tidak ada kuliah).")
    except Exception as e:
        print("[!] gagal stop service: %s" % e)


if __name__ == "__main__":
    main()