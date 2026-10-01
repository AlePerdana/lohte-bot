#!/usr/bin/env python3
"""CLI login ETHOL — isi kredensial di .env lalu jalankan:

  .venv/bin/python login.py
"""

from src.utils import setup_logging
from src.login import login_dan_simpan


def main():
    setup_logging()
    hasil = login_dan_simpan()
    if hasil:
        print("✅ Login sukses!")
        print(f"   token:        {hasil['token'][:60]}...")
        print(f"   refresh_token: {hasil['refresh_token'][:40]}...")
        print(f"\nTersimpan di .env (refresh berlaku 7 hari)")
    else:
        print("❌ Login gagal — cek logs/bot.log")
        raise SystemExit(1)


if __name__ == "__main__":
    main()