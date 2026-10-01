#!/usr/bin/env python3
"""Scan semua kuliah semester ini & simpan ke config.

Jalankan sekali untuk populate daftar matkul, lalu hasilnya dipakai
oleh detect_presensi.py / main.py.

Usage:
  .venv/bin/python scan_kuliah.py
"""

import json
from src.utils import setup_logging, load_config, STATE_PATH, save_state
from src.ethol_client import EtholClient
from src.jadwal import JadwalService


def main():
    setup_logging()
    cfg = load_config()
    client = EtholClient(cfg["token"], cfg["refresh_token"])

    print(f"🔍 Scan kuliah semester {cfg['semester']}/{cfg['tahun']}...\n")

    if not client.ensure_auth():
        print("❌ Auth gagal — jalankan: .venv/bin/python login.py")
        raise SystemExit(1)

    svc = JadwalService(client, cfg)
    kuliahs = svc.scan_semua_kuliah()

    if not kuliahs:
        print("❌ Tidak ada kuliah ditemukan")
        raise SystemExit(1)

    print(f"✅ Ditemukan {len(kuliahs)} matkul:\n")
    for i, k in enumerate(kuliahs, 1):
        print(f"  {i:2}. [{k['nomor']}] {k['nama']} (jenis={k['jenisSchema']})")

    # Simpan ke state.json (bukan .env)
    from src.utils import load_state
    state = load_state()
    state["kuliah"] = kuliahs
    save_state(state)

    print(f"\n💾 Tersimpan ke config/state.json")
    print(f"\nLangkah berikutnya:")
    print(f"  .venv/bin/python detect_presensi.py --loop --auto")


if __name__ == "__main__":
    main()