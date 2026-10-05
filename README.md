# ETHOL Bot — Setup & Penggunaan

Bot otomatis untuk **ETHOL PENS** (`ethol.pens.ac.id`): jadwal kuliah, deteksi presensi terbuka, presensi otomatis, dan notifikasi WhatsApp.

---

## Daftar Isi

1. [Prasyarat](#1-prasyarat)
2. [Setup (Sekali Jalan)](#2-setup-sekali-jalan)
3. [Login & Token](#3-login--token)
4. [Pemakaian Manual](#4-pemakaian-manual)
5. [Setup sebagai Service (Otomatis)](#5-sebagai-service-otomatis)
6. [Notifikasi WhatsApp](#6-notifikasi-whatsapp)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prasyarat

- **Python 3.10+** (cek: `python3 --version`)
- Akun ETHOL PENS (email PENS + password)
- *(Opsional)* API WhatsApp: [CallMeBot](https://www.callmebot.com/) atau [Fonnte](https://fonnte.com/)

---

## 2. Setup (Sekali Jalan)

```bash
cd ~/Documents/ethol-bot

# 1. Buat virtual environment
python3 -m venv .venv

# 2. Install dependensi
.venv/bin/pip install -r requirements.txt

# 3. Salin template .env
cp .env.example .env
```

### Isi `.env`

Edit `~/Documents/ethol-bot/.env` lalu isi minimal bagian ini:

```ini
# Login ETHOL (WAJIB untuk login pertama / re-login)
ETHOL_LOGIN_USERNAME=email_kamu@it.student.pens.ac.id
ETHOL_LOGIN_PASSWORD=***

# Kuliah yang dipantau (format: nomor:jenisSchema:nama)
# nomor kuliah = ID dari daftar kuliah di ETHOL
ETHOL_KULIAH=123456:4:Nama Mata Kuliah
ETHOL_TAHUN=2026
ETHOL_SEMESTER=1
```

> **Cara tahu `nomor` kuliah:** jalankan `main.py --test`, lihat output `presensi aktif` / jadwal, atau buka halaman kuliah di ETHOL lalu lihat URL-nya.

**Variabel lain (opsional):**

| Variabel | Default | Fungsi |
|----------|---------|--------|
| `ETHOL_NOMOR` | - | Nomor mahasiswa |
| `ETHOL_NIPNRP` | - | NRP |
| `PRESENSI_INTERVAL` | 5,60 | Interval random polling (detik) |
| `WA_ENABLED` | false | Aktifkan notifikasi WhatsApp |
| `WA_PROVIDER` | callmebot | `callmebot` \| `fonnte` \| `openclaw` |
| `WA_TARGET` | - | Nomor HP (format `+628xxx`) |
| `WA_APIKEY` | - | API key penyedia WhatsApp |
| `jadwal_kirim` (config) | 06:30 | Jam kirim jadwal pagi |

---

## 3. Login & Token

ETHOL memakai **CAS PENS** (`login.pens.ac.id`). Token berlaku:

- **`token`** → 15 menit (di-auto-refresh oleh bot)
- **`refresh_token`** → **7 hari** (jadi login manual cukup ~seminggu sekali)

### Login pertama

```bash
cd ~/Documents/ethol-bot
.venv/bin/python login.py
```

Output sukses:
```
✅ Login sukses!
   token:        eyJhbGciOiJIUzI1NiIs...
   refresh_token: xxxxxxxxxxxxxxxxxx...
Tersimpan di .env (refresh berlaku 7 hari)
```

Token otomatis ditulis ke `.env`.

### Kapan login ulang?

- Error: `"Refresh token tidak valid, silakan login kembali"`
- Setelah **7 hari** tidak dipakai
- Solusi: jalankan lagi `.venv/bin/python login.py`

---

## 4. Pemakaian Manual

Semua perintah dijalankan dari folder `~/Documents/ethol-bot`.

### 4.1 Test koneksi & endpoint

```bash
.venv/bin/python main.py --test
```

Memeriksa: auth, jadwal hari ini, detail MK, presensi aktif.

### 4.2 Kirim jadwal hari ini

```bash
.venv/bin/python main.py --jadwal
```

Mencetak (dan kirim WhatsApp jika `WA_ENABLED=true`) jadwal hari ini.

### 4.3 Deteksi presensi terbuka

```bash
# Sekali cek
.venv/bin/python detect_presensi.py

# Loop terus (cek tiap 15-45 detik)
.venv/bin/python detect_presensi.py --loop

# Custom interval (misal 5-60 detik)
.venv/bin/python detect_presensi.py --loop --interval 5,60
```

Output jika ada presensi terbuka:
```
[16:30:12] 🔔 1 presensi TERBUKA:
   📚 Nama Mata Kuliah (kuliah 123456)
      key=CPfXXZepzg open=1
```

### 4.4 Deteksi + presensi otomatis

```bash
# Sekali deteksi, langsung submit jika terbuka
.venv/bin/python detect_presensi.py --auto

# Loop + auto submit (disarankan untuk dipakai saat jam kuliah)
.venv/bin/python detect_presensi.py --loop --auto --interval 5,60
```

Jika berhasil:
```
      ✅ PRESENSI BERHASIL!
```

### 4.5 Poll presensi sampai berhasil

```bash
.venv/bin/python main.py --presensi
```

### 4.6 Daemon mode (jadwal + polling terus-menerus)

```bash
.venv/bin/python main.py --daemon
```

Menjalankan loop abadi: kirim jadwal pagi (sekali sehari) + cek presensi tiap 30-60 detik.

> Untuk pemakaian harian, **disarankan pakai service (bagian 5)** supaya jalan otomatis di background.

---

## 5. Sebagai Service (Otomatis)

Agar bot jalan otomatis tanpa terminal terbuka, gunakan **systemd user service**.

### 5.1 Buat file service

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ethol-bot.service << 'EOF'
[Unit]
Description=ETHOL Bot - Presensi & Jadwal Otomatis
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/Documents/ethol-bot
ExecStart=%h/Documents/ethol-bot/.venv/bin/python main.py --daemon
Restart=on-failure
RestartSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
```

### 5.2 Aktifkan & jalankan

```bash
# Reload systemd
systemctl --user daemon-reload

# Mulai service
systemctl --user start ethol-bot

# Cek status
systemctl --user status ethol-bot

# Lihat log real-time
journalctl --user -u ethol-bot -f
```

### 5.3 Agar jalan saat login (boot)

```bash
systemctl --user enable ethol-bot
```

> **Catatan:** service user hanya jalan setelah user login ke desktop. Agar jalan **tanpa login**, jalankan sekali:
> ```bash
> sudo loginctl enable-linger $USER
> ```

### 5.4 Stop / restart / disable

```bash
systemctl --user stop ethol-bot       # stop
systemctl --user restart ethol-bot    # restart (setelah edit .env)
systemctl --user disable ethol-bot    # matikan auto-start
```

### 5.5 Alternatif: cron (hanya presensi saat jam kuliah)

Jika tidak ingin service jalan 24 jam, cukup jalankan deteksi saat jam kuliah:

```bash
crontab -e
```

Tambahkan (contoh: deteksi tiap menit Senin–Jumat jam 07.00–18.00):

```cron
* 7-18 * * 1-5  cd /home/USERNAME/Documents/ethol-bot && .venv/bin/python detect_presensi.py --loop --auto --interval 15,45 >> logs/cron.log 2>&1
```

---

## 6. Notifikasi WhatsApp

### Option A — CallMeBot (paling mudah, gratis)

1. Simpan nomor `+34 644 84 44 84` ke kontak, kirim pesan: `I allow callmebot to send me messages`
2. Balasan berisi **API key**
3. Isi di `.env`:
   ```ini
   WA_ENABLED=true
   WA_PROVIDER=callmebot
   WA_TARGET=+628xxxxxxx
   WA_APIKEY=xxxxx
   ```

### Option B — Fonnte

1. Daftar di [fonnte.com](https://fonnte.com), ambil token dari dashboard
2. Isi di `.env`:
   ```ini
   WA_ENABLED=true
   WA_PROVIDER=fonnte
   WA_TARGET=628xxxxxxx
   WA_APIKEY=***
   ```

> **Status saat ini:** integrasi notifier masih tahap dasar (log + print). Untuk mengaktifkan pengiriman sungguhan, lengkapi fungsi di `src/notify.py` sesuai provider yang dipilih.

---

## 7. Troubleshooting

| Gejala | Penyebab | Solusi |
|--------|----------|--------|
| `Refresh token tidak valid` | refresh_token expired (7 hari) | `.venv/bin/python login.py` |
| `login gagal: username/password salah` | kredensial salah / password berubah | Cek `ETHOL_LOGIN_USERNAME`/`PASSWORD` di `.env` |
| `token expired` terus-menerus | auto-refresh belum jalan | `systemctl --user restart ethol-bot` |
| `timeout` / `The read operation timed out` | server ETHOL lambat | Normal — bot punya retry; cek lagi nanti |
| Presensi tidak terdeteksi | dosen belum buka presensi | Presensi hanya muncul saat dosen membukanya |
| `Parameter tidak valid` saat submit presensi | nomor mahasiswa belum terisi (auto-diisi dari token) | Jalankan `.venv/bin/python login.py`, atau set `ETHOL_NOMOR` di `.env` |
| `ModuleNotFoundError: dotenv` | lupa venv | Pakai `.venv/bin/python ...` (bukan `python3`) |
| Service tidak jalan | linger belum aktif | `sudo loginctl enable-linger $USER` |

### Lihat log

```bash
# Log file
tail -f ~/Documents/ethol-bot/logs/bot.log

# Log service
journalctl --user -u ethol-bot -f
```

### Ganti daftar kuliah

Edit `.env` → `ETHOL_KULIAH`, format多名 kuliah dipisah koma:

```ini
ETHOL_KULIAH=123456:4:Nama MK Pertama,123457:4:Nama MK Kedua
```

Lalu restart:
```bash
systemctl --user restart ethol-bot
```

---

## Ringkasan Perintah

| Perintah | Fungsi |
|----------|--------|
| `.venv/bin/python login.py` | Login → simpan token (7 hari) |
| `.venv/bin/python main.py --test` | Test semua endpoint |
| `.venv/bin/python main.py --jadwal` | Kirim jadwal hari ini |
| `.venv/bin/python detect_presensi.py` | Cek presensi terbuka (sekali) |
| `.venv/bin/python detect_presensi.py --loop --auto` | Polling + presensi otomatis |
| `.venv/bin/python main.py --daemon` | Mode jalan terus |
| `systemctl --user start ethol-bot` | Jalankan sebagai service |
| `systemctl --user status ethol-bot` | Cek status service |