"""Logic jadwal kuliah hari ini + detail mata kuliah."""

import logging
from src.ethol_client import EtholClient

log = logging.getLogger("jadwal")


class JadwalService:
    def __init__(self, client: EtholClient, config: dict):
        self.client = client
        self.cfg = config

    def scan_semua_kuliah(self) -> list[dict]:
        """Scan & simpan semua kuliah semester ini ke config.

        Return list kuliah yang ditemukan.
        """
        data = self.client.daftar_kuliah(self.cfg["tahun"], self.cfg["semester"])
        if not data:
            log.warning("tidak ada kuliah ditemukan")
            return []

        # Konversi ke format config
        kuliahs = []
        for k in data:
            # Field bisa berbeda-beda, coba beberapa variasi
            nomor = k.get("nomor") or k.get("kuliah") or k.get("id")
            nama = (
                k.get("nama")
                or k.get("matakuliah", {}).get("nama")
                if isinstance(k.get("matakuliah"), dict)
                else k.get("matakuliah")
                or k.get("nama_matakuliah")
                or "?"
            )
            jenis = k.get("jenisSchema") or k.get("jenis_schema") or k.get("jenisSchemaMk") or 4
            if nomor:
                kuliahs.append({
                    "nomor": int(nomor),
                    "jenisSchema": int(jenis),
                    "nama": nama,
                })

        # Update config
        self.cfg["kuliah"] = kuliahs
        log.info("scan kuliah: ditemukan %d matkul", len(kuliahs))
        return kuliahs

    def hari_ini(self) -> list[dict]:
        """Ambil jadwal kuliah hari ini untuk semua kuliah di config."""
        kuliahs = [{"nomor": k["nomor"], "jenisSchema": k["jenisSchema"]}
                   for k in self.cfg["kuliah"]]
        data = self.client.jadwal_hari_ini(
            kuliahs, self.cfg["tahun"], self.cfg["semester"],
        )
        log.info("jadwal hari ini: %d kuliah", len(data))
        return data

    def detail_semua(self) -> list[dict]:
        """Detail semua kuliah di config."""
        hasil = []
        for k in self.cfg["kuliah"]:
            try:
                d = self.client.detail_kuliah(k["nomor"], k["jenisSchema"])
                hasil.append({
                    "kuliah": k["nomor"],
                    "nama": d.get("matakuliah", {}).get("nama", "?"),
                    "dosen": d.get("dosen", "?"),
                    "kelas": d.get("kode_kelas", "?"),
                    "nomor_dosen": d.get("nomor_dosen"),
                })
            except Exception as e:
                log.warning("detail kuliah %s gagal: %s", k["nomor"], e)
        return hasil

    def format_pesan(self) -> str:
        """Format jadwal hari ini jadi teks siap kirim WhatsApp."""
        jadwal = self.hari_ini()
        detail = {d["kuliah"]: d for d in self.detail_semua()}

        if not jadwal:
            return "📅 *Jadwal Hari Ini*\nTidak ada kuliah hari ini. 🎉"

        lines = ["📅 *Jadwal Kuliah Hari Ini*"]
        for j in jadwal:
            d = detail.get(j["kuliah"], {})
            lines.append("")
            lines.append(f"📚 *{d.get('nama', j['kuliah'])}*")
            lines.append(f"🕐 {j['jam_awal']} - {j['jam_akhir']}")
            lines.append(f"📍 {j.get('ruang', '-')}")
            if d.get("dosen"):
                lines.append(f"👨‍🏫 {d['dosen']}")
        return "\n".join(lines)