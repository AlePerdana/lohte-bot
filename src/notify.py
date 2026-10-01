"""Notifier — kirim pesan ke WhatsApp.

Dua mode:
1. Via OpenClaw message tool (butuh gateway jalan)
2. Via CallMeBot/Fonnte API (butuh API key)

Untuk sekarang: log ke file + print. Integrasi WhatsApp menyusul.
"""

import logging
from src.utils import CONFIG_PATH

log = logging.getLogger("notify")


class Notifier:
    def __init__(self, config: dict):
        self.wa = config.get("whatsapp", {})
        self.enabled = self.wa.get("enabled", False)
        self.target = self.wa.get("target", "")

    def kirim(self, pesan: str):
        """Kirim pesan WhatsApp. Jika disabled, hanya log."""
        if not self.enabled:
            log.info("[NOTIFY-DISABLED]\n%s", pesan)
            return

        # TODO: integrasi WhatsApp (CallMeBot / Fonnte / OpenClaw)
        # Contoh CallMeBot:
        #   url = f"https://api.callmebot.com/whatsapp.php?phone={self.target}&text={urllib.parse.quote(pesan)}&apikey=XXX"
        #   requests.get(url)

        log.info("[NOTIFY→%s]\n%s", self.target, pesan)
        print(pesan)


def kirim_jadwal(notifier: Notifier, jadwal_service):
    pesan = jadwal_service.format_pesan()
    notifier.kirim(pesan)


def kirim_presensi(notifier: Notifier, result: dict, nama_mk: str):
    if result and result.get("sukses"):
        pesan = f"✅ *Presensi Berhasil*\n\n📚 {nama_mk}\n🔑 Key: `{result['key']}`\n\nPresensi otomatis tercatat."
    else:
        pesan = f"❌ *Presensi Gagal*\n\n📚 {nama_mk}\n{result.get('pesan', 'Unknown error') if result else 'Tidak ada presensi aktif'}"
    notifier.kirim(pesan)