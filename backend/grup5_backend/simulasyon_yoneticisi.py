# -*- coding: utf-8 -*-
"""
simulasyon_yoneticisi.py
Akıllı Sınıf Otomasyon Sistemi - Takım 5

ÖNEMLİ NOT (KAYNAK KOD POLİTİKASI):
    kaynak/dijital_ikiz.py dosyası ORİJİNAL haliyle, HİÇBİR satırı
    değiştirilmeden bırakılmıştır. Bu dosya, dijital_ikiz.py'yi bir
    alt-süreç (subprocess) olarak ÇALIŞTIRIR ve onun konsol çıktısını
    (stdout) gerçek zamanlı olarak okuyarak ayrıştırır (parse eder).
    Böylece:
      1) Kaynak kod bütünlüğü %100 korunur (öğretim üyesine teslim edilen
         kod ile çalışan kod birebir aynıdır),
      2) Üretilen tüm olaylar (insan girişi/çıkışı, geri dönüşüm kutusu
         olayları, saatlik çevresel raporlar) yakalanıp PostgreSQL
         veritabanına kaydedilir,
      3) Kaynak kodda fiziksel olarak bulunmayan PIR hareket sensörü,
         bu dış katmanda simüle edilerek aynı zaman çizgisine (sim_zamani)
         paralel şekilde üretilir ve veritabanına ayrı tablolarda yazılır.

Bu dosya, raporun "Bu bir simülasyondur, gerçek görüntü işleme/donanım
çalıştırılmamaktadır" notuyla tam uyumludur: hiçbir gerçek kamera veya
GPIO erişimi yapılmaz, sadece dijital_ikiz.py'nin ürettiği olay akışı
okunur.
"""

import re
import subprocess
import sys
import threading
import queue
import time
import os

from pir_sensoru import PIRSensorAgi

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "db"))
from veritabani import VeritabaniYoneticisi  # noqa: E402


KAYNAK_DOSYA = os.path.join(os.path.dirname(__file__), "dijital_ikiz.py")

# --- dijital_ikiz.py çıktısındaki satırları yakalamak için regex'ler ---
RE_ATIK_DUSTU = re.compile(
    r"\[(?P<zaman>[\d.]+) sn\] -> Çöp atıldı\. Yığın Yüksekliği: (?P<yukseklik>[\d.]+)m "
    r"\(Kutudaki: (?P<adet>\d+)/(?P<kapasite>\d+)\)"
)
RE_KUTU_BOSALTILDI = re.compile(
    r"\[(?P<zaman>[\d.]+) sn\] -> \[GERİ DÖNÜŞÜM GÖREVLİSİ\] Kutu boşaltıldı!"
)
RE_KUTU_TASTI = re.compile(
    r"\[(?P<zaman>[\d.]+) sn\] -> UYARI: Geri dönüşüm kutusu zaten dolu"
)
RE_SAAT_RAPORU = re.compile(
    r"\[(?P<saat>\d+)\. SAAT RAPORU \| Zaman: (?P<zaman>[\d.]+)s\]"
)
RE_AKTIF_INSAN = re.compile(r"Odadaki Aktif İnsan: (?P<adet>\d+)")
RE_ISIK = re.compile(r"Işık Durumu: (?P<adet>\d+) Işık Açık")
RE_HAVALANDIRMA = re.compile(r"Havalandırma Durumu: (?P<durum>AÇIK|KAPALI)")
RE_AKIM = re.compile(r"Anlık Akım \(Şebeke Çekişi\): (?P<deger>[\d.]+)A")
RE_ENERJI = re.compile(r"Toplam Enerji Tüketimi: (?P<deger>[\d.]+) Wh")
RE_SENSORLER = re.compile(
    r"Sensörler -> Sıcaklık: (?P<sicaklik>[\-\d.]+)°C \| CO2: (?P<co2>[\d.]+) ppm"
)
RE_SIMULASYON_BITTI_ATIK = re.compile(
    r"Gün Sonu Geri Dönüşüm Kutusunda Kalan Atık Sayısı: (?P<adet>\d+)"
)
RE_SIMULASYON_TOPLAM_ATIK = re.compile(
    r"Gün İçinde Atılan TOPLAM Atık Sayısı: (?P<adet>\d+)"
)
RE_SIMULASYON_ENERJI = re.compile(
    r"Gün Sonu Toplam Enerji Tüketimi: (?P<deger>[\d.]+) Wh"
)


class SimulasyonYoneticisi:
    """
    dijital_ikiz.py'yi değiştirmeden çalıştırır, çıktısını canlı parse eder,
    PIR sensör ağını aynı zaman çizgisinde simüle eder ve tüm veriyi
    PostgreSQL'e yazar. Aynı zamanda arayüzün (Tkinter) okuyabileceği bir
    "anlık durum" sözlüğünü thread-safe şekilde güncel tutar.
    """

    def __init__(self, db_ayarlari=None, durum_callback=None, log_callback=None):
        self.db_ayarlari = db_ayarlari or {}
        self.durum_callback = durum_callback or (lambda durum: None)
        self.log_callback = log_callback or (lambda satir: None)

        self.vt = VeritabaniYoneticisi(**self.db_ayarlari)
        self.pir_agi = PIRSensorAgi(sensor_sayisi=3)

        self.oturum_id = None
        self.calisiyor = False
        self.proc = None
        self._thread = None

        self.anlik_durum = {
            "sim_zamani": 0.0,
            "aktif_kisi": 0,
            "acik_isik": 0,
            "havalandirma": False,
            "akim_a": 0.0,
            "sicaklik_c": 0.0,
            "co2_ppm": 400.0,
            "toplam_enerji_wh": 0.0,
            "kutudaki_atik": 0,
            "toplam_atik": 0,
            "pir_durum": {},
            "son_saat_raporu": 0,
            "durum_metni": "Beklemede",
        }

        # Saatlik rapor satırları birden çok satıra yayıldığı için
        # bir "biriktirici" tutuyoruz.
        self._son_saat_zamani = None

    # ------------------------------------------------------------------
    def baslat(self):
        """Veritabanı bağlantısını açar, şemayı kontrol eder, oturumu başlatır
        ve simülasyon sürecini ayrı bir thread üzerinde çalıştırır."""
        self.vt.baglan()
        self.vt.semayi_olustur()
        self.oturum_id = self.vt.oturum_baslat()

        self.calisiyor = True
        self._thread = threading.Thread(target=self._calistir, daemon=True)
        self._thread.start()

    def durdur(self):
        self.calisiyor = False
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()

    # ------------------------------------------------------------------
    def _calistir(self):
        baslangic = time.time()
        self.anlik_durum["durum_metni"] = "Çalışıyor"
        self.durum_callback(dict(self.anlik_durum))

        # ÖNEMLİ: dijital_ikiz.py hiçbir parametre/argüman almaz; olduğu gibi
        # `python3 dijital_ikiz.py` şeklinde çalıştırılır (kaynak kod sıfır
        # değişiklikle çalışır).
        self.proc = subprocess.Popen(
            [sys.executable, "-u", KAYNAK_DOSYA],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(KAYNAK_DOSYA),
        )

        # Saatlik rapor satırlarını grupla
        rapor_tamponu = {}

        for satir in self.proc.stdout:
            satir = satir.rstrip("\n")
            if not self.calisiyor:
                break
            self.log_callback(satir)
            self._satiri_isle(satir, rapor_tamponu)

        self.proc.wait()
        toplam_sure = time.time() - baslangic
        if self.oturum_id is not None:
            try:
                self.vt.oturum_bitir(self.oturum_id, round(toplam_sure, 2))
            except Exception as e:
                self.log_callback(f"[VERITABANI HATASI] Oturum kapatılamadı: {e}")

        self.calisiyor = False
        self.anlik_durum["durum_metni"] = "Tamamlandı"
        self.durum_callback(dict(self.anlik_durum))

    # ------------------------------------------------------------------
    def _guvenli_yaz(self, fonksiyon, *args, **kwargs):
        try:
            fonksiyon(*args, **kwargs)
        except Exception as e:
            self.log_callback(f"[VERITABANI HATASI] {e}")

    def _satiri_isle(self, satir, rapor_tamponu):
        m = RE_ATIK_DUSTU.search(satir)
        if m:
            zaman = float(m.group("zaman"))
            adet = int(m.group("adet"))
            yukseklik = float(m.group("yukseklik"))
            self.anlik_durum["kutudaki_atik"] = adet
            self.anlik_durum["toplam_atik"] += 1
            self.anlik_durum["sim_zamani"] = zaman
            self._guvenli_yaz(
                self.vt.geri_donusum_olayi_ekle,
                self.oturum_id, zaman, "ATIK_DUSTU", adet, yukseklik
            )
            self._pir_guncelle(zaman)
            self.durum_callback(dict(self.anlik_durum))
            return

        m = RE_KUTU_BOSALTILDI.search(satir)
        if m:
            zaman = float(m.group("zaman"))
            self.anlik_durum["kutudaki_atik"] = 0
            self._guvenli_yaz(
                self.vt.geri_donusum_olayi_ekle,
                self.oturum_id, zaman, "KUTU_BOSALTILDI", 0, 0.0
            )
            self.durum_callback(dict(self.anlik_durum))
            return

        m = RE_KUTU_TASTI.search(satir)
        if m:
            zaman = float(m.group("zaman"))
            self._guvenli_yaz(
                self.vt.geri_donusum_olayi_ekle,
                self.oturum_id, zaman, "KUTU_TASTI",
                self.anlik_durum["kutudaki_atik"], None
            )
            return

        m = RE_SAAT_RAPORU.search(satir)
        if m:
            rapor_tamponu.clear()
            rapor_tamponu["zaman"] = float(m.group("zaman"))
            return

        m = RE_AKTIF_INSAN.search(satir)
        if m:
            rapor_tamponu["aktif_kisi"] = int(m.group("adet"))
            return

        m = RE_ISIK.search(satir)
        if m:
            rapor_tamponu["acik_isik"] = int(m.group("adet"))
            return

        m = RE_HAVALANDIRMA.search(satir)
        if m:
            rapor_tamponu["havalandirma"] = (m.group("durum") == "AÇIK")
            return

        m = RE_AKIM.search(satir)
        if m:
            rapor_tamponu["akim_a"] = float(m.group("deger"))
            return

        m = RE_ENERJI.search(satir)
        if m:
            rapor_tamponu["toplam_enerji_wh"] = float(m.group("deger"))
            return

        m = RE_SENSORLER.search(satir)
        if m:
            rapor_tamponu["sicaklik_c"] = float(m.group("sicaklik"))
            rapor_tamponu["co2_ppm"] = float(m.group("co2"))
            self._saat_raporunu_tamamla(rapor_tamponu)
            return

        m = RE_SIMULASYON_BITTI_ATIK.search(satir)
        if m:
            self.anlik_durum["kutudaki_atik"] = int(m.group("adet"))
            return

        m = RE_SIMULASYON_TOPLAM_ATIK.search(satir)
        if m:
            self.anlik_durum["toplam_atik"] = int(m.group("adet"))
            return

        m = RE_SIMULASYON_ENERJI.search(satir)
        if m:
            self.anlik_durum["toplam_enerji_wh"] = float(m.group("deger"))
            return

    def _saat_raporunu_tamamla(self, rapor):
        """Saatlik rapor bloğu tamamlandığında veritabanına ve PIR'a yazar."""
        zaman = rapor.get("zaman", self.anlik_durum["sim_zamani"])
        aktif_kisi = rapor.get("aktif_kisi", self.anlik_durum["aktif_kisi"])
        acik_isik = rapor.get("acik_isik", self.anlik_durum["acik_isik"])
        havalandirma = rapor.get("havalandirma", self.anlik_durum["havalandirma"])
        akim_a = rapor.get("akim_a", self.anlik_durum["akim_a"])
        sicaklik = rapor.get("sicaklik_c", self.anlik_durum["sicaklik_c"])
        co2 = rapor.get("co2_ppm", self.anlik_durum["co2_ppm"])
        enerji = rapor.get("toplam_enerji_wh", self.anlik_durum["toplam_enerji_wh"])

        self.anlik_durum.update({
            "sim_zamani": zaman,
            "aktif_kisi": aktif_kisi,
            "acik_isik": acik_isik,
            "havalandirma": havalandirma,
            "akim_a": akim_a,
            "sicaklik_c": sicaklik,
            "co2_ppm": co2,
            "toplam_enerji_wh": enerji,
        })

        self._guvenli_yaz(
            self.vt.ortam_olcumu_ekle,
            self.oturum_id, zaman, aktif_kisi, acik_isik, havalandirma,
            akim_a, sicaklik, co2, enerji
        )

        self._pir_guncelle(zaman)
        self.durum_callback(dict(self.anlik_durum))

    def _pir_guncelle(self, sim_zamani):
        """PIR sensör ağını mevcut aktif kişi sayısına göre okur ve kaydeder."""
        aktif_kisi = self.anlik_durum["aktif_kisi"]
        sonuclar = self.pir_agi.oku_hepsi(aktif_kisi, sim_zamani)
        self.anlik_durum["pir_durum"] = sonuclar

        for sensor_id, tetiklendi in sonuclar.items():
            self._guvenli_yaz(
                self.vt.pir_olayi_ekle,
                self.oturum_id, sim_zamani, sensor_id, tetiklendi, aktif_kisi
            )


if __name__ == "__main__":
    # Komut satırından bağımsız test: konsola yazarak çalıştırır.
    def yazdir_log(satir):
        print(satir)

    def yazdir_durum(durum):
        pass

    yonetici = SimulasyonYoneticisi(log_callback=yazdir_log, durum_callback=yazdir_durum)
    yonetici.baslat()
    while yonetici.calisiyor:
        time.sleep(0.5)
    print("\n[YÖNETİCİ] Simülasyon ve veritabanı kaydı tamamlandı.")
