# -*- coding: utf-8 -*-
"""
arayuz.py
Akıllı Sınıf Otomasyon Sistemi - Takım 5
Masaüstü İzleme ve Kontrol Paneli (Tkinter)

Bu arayüz:
  - dijital_ikiz.py'yi (ORİJİNAL, DEĞİŞTİRİLMEMİŞ kaynak kod) başlatıp durdurur,
  - Simülasyonun ürettiği ortam verilerini (kişi sayısı, sıcaklık, CO2, enerji,
    aydınlatma/havalandırma durumu) gerçek zamanlı gösterir,
  - Geri dönüşüm kutusu ve PIR hareket sensörü olaylarını canlı log olarak listeler,
  - Tüm verilerin PostgreSQL'e yazıldığını ve geçmiş oturumların
    sorgulanabildiğini gösterir.

NOT: Bu HTML/web tabanlı bir arayüz DEĞİLDİR; tamamen Python'un standart
kütüphanesi olan Tkinter ile yazılmış bağımsız bir masaüstü uygulamasıdır.
Raporda "simülasyon" olarak tanımlanan bu proje gerçek bir kamerayı veya
GPIO donanımını sürmez.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "kaynak"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "db"))

from simulasyon_yoneticisi import SimulasyonYoneticisi  # noqa: E402
from veritabani import VeritabaniYoneticisi  # noqa: E402


# ---------------------------------------------------------------------------
# RENK VE STİL TOKENLARI
# ---------------------------------------------------------------------------
RENK_ARKAPLAN = "#101820"
RENK_PANEL = "#16222C"
RENK_PANEL_ACIK = "#1C2B38"
RENK_VURGU = "#3FA796"        # enerji/yeşil vurgu
RENK_VURGU2 = "#E8A33D"       # uyarı/turuncu vurgu
RENK_KIRMIZI = "#D9534F"
RENK_METIN = "#EAF2F1"
RENK_METIN_SOLUK = "#8FA3AC"
FONT_BASLIK = ("Segoe UI", 16, "bold")
FONT_ALT_BASLIK = ("Segoe UI", 11, "bold")
FONT_NORMAL = ("Segoe UI", 10)
FONT_BUYUK_DEGER = ("Segoe UI", 22, "bold")
FONT_MONO = ("Consolas", 9)


class KartWidget(ttk.Frame):
    """Tek bir metriği büyük puntoyla gösteren kart (KPI kartı)."""

    def __init__(self, parent, baslik, birim="", renk=RENK_VURGU):
        super().__init__(parent, style="Kart.TFrame")
        self.renk = renk
        self.birim = birim

        self.baslik_lbl = tk.Label(
            self, text=baslik, font=FONT_NORMAL,
            bg=RENK_PANEL_ACIK, fg=RENK_METIN_SOLUK, anchor="w"
        )
        self.baslik_lbl.pack(fill="x", padx=14, pady=(10, 0))

        self.deger_lbl = tk.Label(
            self, text="--", font=FONT_BUYUK_DEGER,
            bg=RENK_PANEL_ACIK, fg=renk, anchor="w"
        )
        self.deger_lbl.pack(fill="x", padx=14, pady=(0, 10))

        self.configure(style="Kart.TFrame")
        self["padding"] = 0

    def guncelle(self, deger):
        self.deger_lbl.config(text=f"{deger}{self.birim}")


class AkilliSinifArayuzu:
    def __init__(self, root):
        self.root = root
        self.root.title("Akıllı Sınıf Otomasyon ve Analitik Karar Destek Sistemi — Takım 5")
        self.root.geometry("1180x760")
        self.root.configure(bg=RENK_ARKAPLAN)
        self.root.minsize(1000, 680)

        self._stil_kur()

        self.mesaj_kuyrugu = queue.Queue()
        self.yonetici = None
        self.vt_goruntule = VeritabaniYoneticisi()

        self._arayuzu_olustur()
        self._kuyruk_dinleyiciyi_baslat()

    # ------------------------------------------------------------------
    def _stil_kur(self):
        stil = ttk.Style()
        try:
            stil.theme_use("clam")
        except tk.TclError:
            pass

        stil.configure("Kart.TFrame", background=RENK_PANEL_ACIK, relief="flat")
        stil.configure("Panel.TFrame", background=RENK_PANEL)
        stil.configure("TNotebook", background=RENK_ARKAPLAN, borderwidth=0)
        stil.configure("TNotebook.Tab", background=RENK_PANEL,
                        foreground=RENK_METIN, padding=(16, 8), font=FONT_ALT_BASLIK)
        stil.map("TNotebook.Tab",
                 background=[("selected", RENK_VURGU)],
                 foreground=[("selected", "#0B1014")])

        stil.configure("Baslat.TButton", font=FONT_ALT_BASLIK, padding=10)
        stil.configure("Durdur.TButton", font=FONT_ALT_BASLIK, padding=10)

    # ------------------------------------------------------------------
    def _arayuzu_olustur(self):
        # ÜST BAŞLIK ÇUBUĞU
        ust = tk.Frame(self.root, bg=RENK_ARKAPLAN)
        ust.pack(fill="x", padx=20, pady=(16, 8))

        tk.Label(
            ust, text="Akıllı Sınıf Otomasyon Sistemi",
            font=FONT_BASLIK, bg=RENK_ARKAPLAN, fg=RENK_METIN
        ).pack(side="left")

        self.durum_etiketi = tk.Label(
            ust, text="● Beklemede", font=FONT_ALT_BASLIK,
            bg=RENK_ARKAPLAN, fg=RENK_METIN_SOLUK
        )
        self.durum_etiketi.pack(side="right")

        # KONTROL ÇUBUĞU
        kontrol = tk.Frame(self.root, bg=RENK_ARKAPLAN)
        kontrol.pack(fill="x", padx=20, pady=(0, 12))

        self.baslat_btn = ttk.Button(
            kontrol, text="▶  Simülasyonu Başlat", style="Baslat.TButton",
            command=self.simulasyonu_baslat
        )
        self.baslat_btn.pack(side="left", padx=(0, 10))

        self.durdur_btn = ttk.Button(
            kontrol, text="■  Durdur", style="Durdur.TButton",
            command=self.simulasyonu_durdur, state="disabled"
        )
        self.durdur_btn.pack(side="left")

        tk.Label(
            kontrol, text="Veritabanı: PostgreSQL  |  Oturum ID: —",
            font=FONT_NORMAL, bg=RENK_ARKAPLAN, fg=RENK_METIN_SOLUK
        ).pack(side="right")
        self.oturum_lbl = kontrol.winfo_children()[-1]

        # SEKME (TAB) YAPISI
        self.defter = ttk.Notebook(self.root)
        self.defter.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self.sekme_anlik = tk.Frame(self.defter, bg=RENK_ARKAPLAN)
        self.sekme_olaylar = tk.Frame(self.defter, bg=RENK_ARKAPLAN)
        self.sekme_pir = tk.Frame(self.defter, bg=RENK_ARKAPLAN)
        self.sekme_log = tk.Frame(self.defter, bg=RENK_ARKAPLAN)

        self.defter.add(self.sekme_anlik, text="  Anlık Durum  ")
        self.defter.add(self.sekme_olaylar, text="  Geri Dönüşüm Olayları  ")
        self.defter.add(self.sekme_pir, text="  PIR Hareket Sensörleri  ")
        self.defter.add(self.sekme_log, text="  Konsol Günlüğü  ")

        self._anlik_sekmesini_kur()
        self._olaylar_sekmesini_kur()
        self._pir_sekmesini_kur()
        self._log_sekmesini_kur()

    # ------------------------------------------------------------------
    def _anlik_sekmesini_kur(self):
        # KPI Kartları - 8 sütun ızgara
        izgara = tk.Frame(self.sekme_anlik, bg=RENK_ARKAPLAN)
        izgara.pack(fill="x", pady=(16, 8))
        for i in range(4):
            izgara.columnconfigure(i, weight=1, uniform="kart")

        self.kart_zaman = KartWidget(izgara, "SİMÜLASYON ZAMANI", " sn", RENK_METIN)
        self.kart_kisi = KartWidget(izgara, "AKTİF KİŞİ SAYISI", " kişi", RENK_VURGU)
        self.kart_isik = KartWidget(izgara, "AÇIK IŞIK ADEDİ", " / 4", RENK_VURGU2)
        self.kart_havalandirma = KartWidget(izgara, "HAVALANDIRMA", "", RENK_VURGU)

        self.kart_sicaklik = KartWidget(izgara, "SICAKLIK (Sensör)", " °C", RENK_METIN)
        self.kart_co2 = KartWidget(izgara, "CO2 (Sensör)", " ppm", RENK_METIN)
        self.kart_akim = KartWidget(izgara, "ANLIK AKIM", " A", RENK_METIN)
        self.kart_enerji = KartWidget(izgara, "TOPLAM ENERJİ", " Wh", RENK_VURGU)

        for idx, kart in enumerate([
            self.kart_zaman, self.kart_kisi, self.kart_isik, self.kart_havalandirma,
            self.kart_sicaklik, self.kart_co2, self.kart_akim, self.kart_enerji
        ]):
            r, c = divmod(idx, 4)
            kart.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)

        # GERİ DÖNÜŞÜM KUTUSU GÖSTERGESİ (basit görsel çubuk - HTML değil, Canvas)
        kutu_cerceve = tk.Frame(self.sekme_anlik, bg=RENK_PANEL)
        kutu_cerceve.pack(fill="x", pady=(16, 0), padx=2)

        tk.Label(
            kutu_cerceve, text="GERİ DÖNÜŞÜM KUTUSU DOLULUK SEVİYESİ",
            font=FONT_ALT_BASLIK, bg=RENK_PANEL, fg=RENK_METIN_SOLUK
        ).pack(anchor="w", padx=14, pady=(10, 4))

        self.kutu_canvas = tk.Canvas(
            kutu_cerceve, height=36, bg=RENK_PANEL_ACIK,
            highlightthickness=0
        )
        self.kutu_canvas.pack(fill="x", padx=14, pady=(0, 14))
        self.kutu_metin = tk.Label(
            kutu_cerceve, text="0 / 40 atık", font=FONT_NORMAL,
            bg=RENK_PANEL, fg=RENK_METIN_SOLUK
        )
        self.kutu_metin.pack(anchor="e", padx=14, pady=(0, 10))

        self.root.update_idletasks()

    def _olaylar_sekmesini_kur(self):
        cerceve = tk.Frame(self.sekme_olaylar, bg=RENK_ARKAPLAN)
        cerceve.pack(fill="both", expand=True, pady=(16, 0))

        kolonlar = ("zaman", "olay", "kutudaki_atik", "yukseklik")
        self.olaylar_tablo = ttk.Treeview(
            cerceve, columns=kolonlar, show="headings", height=18
        )
        basliklar = {
            "zaman": "Sim. Zamanı (sn)", "olay": "Olay Tipi",
            "kutudaki_atik": "Kutudaki Atık", "yukseklik": "Yığın Yüksekliği (m)"
        }
        for k in kolonlar:
            self.olaylar_tablo.heading(k, text=basliklar[k])
            self.olaylar_tablo.column(k, anchor="center", width=180)
        self.olaylar_tablo.pack(fill="both", expand=True, side="left")

        kaydirma = ttk.Scrollbar(cerceve, orient="vertical", command=self.olaylar_tablo.yview)
        kaydirma.pack(side="right", fill="y")
        self.olaylar_tablo.configure(yscrollcommand=kaydirma.set)

    def _pir_sekmesini_kur(self):
        ust_aciklama = tk.Label(
            self.sekme_pir,
            text=("PIR (Pasif Kızılötesi) hareket sensörleri, raporda belirtilen düşük maliyetli "
                  "donanım önerisini tamamlayıcı şekilde eklenmiştir. Kamera tabanlı kişi sayma "
                  "algoritmasını (YOLO) hareket bilgisiyle çapraz doğrulamak için kullanılır."),
            font=FONT_NORMAL, bg=RENK_ARKAPLAN, fg=RENK_METIN_SOLUK,
            wraplength=1080, justify="left"
        )
        ust_aciklama.pack(fill="x", pady=(16, 12), anchor="w")

        izgara = tk.Frame(self.sekme_pir, bg=RENK_ARKAPLAN)
        izgara.pack(fill="x")
        self.pir_kartlari = {}
        for i in range(3):
            sensor_id = f"PIR_{i+1}"
            kart = KartWidget(izgara, f"{sensor_id} DURUMU", "", RENK_METIN_SOLUK)
            kart.pack(side="left", expand=True, fill="x", padx=6)
            self.pir_kartlari[sensor_id] = kart

        cerceve = tk.Frame(self.sekme_pir, bg=RENK_ARKAPLAN)
        cerceve.pack(fill="both", expand=True, pady=(16, 0))

        kolonlar = ("zaman", "sensor", "hareket", "doluluk")
        self.pir_tablo = ttk.Treeview(cerceve, columns=kolonlar, show="headings", height=14)
        basliklar = {
            "zaman": "Sim. Zamanı (sn)", "sensor": "Sensör",
            "hareket": "Hareket Algılandı", "doluluk": "Doluluk Tahmini"
        }
        for k in kolonlar:
            self.pir_tablo.heading(k, text=basliklar[k])
            self.pir_tablo.column(k, anchor="center", width=200)
        self.pir_tablo.pack(fill="both", expand=True, side="left")

        kaydirma = ttk.Scrollbar(cerceve, orient="vertical", command=self.pir_tablo.yview)
        kaydirma.pack(side="right", fill="y")
        self.pir_tablo.configure(yscrollcommand=kaydirma.set)

    def _log_sekmesini_kur(self):
        cerceve = tk.Frame(self.sekme_log, bg=RENK_ARKAPLAN)
        cerceve.pack(fill="both", expand=True, pady=(16, 0))

        self.log_metin = tk.Text(
            cerceve, bg="#0B1014", fg="#A9C6BF", font=FONT_MONO,
            wrap="word", insertbackground="white"
        )
        self.log_metin.pack(fill="both", expand=True, side="left")

        kaydirma = ttk.Scrollbar(cerceve, orient="vertical", command=self.log_metin.yview)
        kaydirma.pack(side="right", fill="y")
        self.log_metin.configure(yscrollcommand=kaydirma.set)

    # ------------------------------------------------------------------
    # SİMÜLASYON KONTROLÜ
    # ------------------------------------------------------------------
    def simulasyonu_baslat(self):
        self.baslat_btn.config(state="disabled")
        self.durdur_btn.config(state="normal")
        self.durum_etiketi.config(text="● Çalışıyor", fg=RENK_VURGU)
        self.log_metin.delete("1.0", "end")
        for tablo in (self.olaylar_tablo, self.pir_tablo):
            for item in tablo.get_children():
                tablo.delete(item)

        try:
            self.yonetici = SimulasyonYoneticisi(
                durum_callback=self._durum_callback_thread_guvenli,
                log_callback=self._log_callback_thread_guvenli,
            )
            self.yonetici.baslat()
            self.oturum_lbl.config(
                text=f"Veritabanı: PostgreSQL  |  Oturum ID: {self.yonetici.oturum_id}"
            )
        except Exception as e:
            messagebox.showerror(
                "Veritabanı Bağlantı Hatası",
                f"PostgreSQL'e bağlanılamadı:\n{e}\n\n"
                "Lütfen db/veritabani.py içindeki bağlantı bilgilerini "
                "(host, port, dbname, user, password) kontrol edin."
            )
            self.baslat_btn.config(state="normal")
            self.durdur_btn.config(state="disabled")
            self.durum_etiketi.config(text="● Hata", fg=RENK_KIRMIZI)

    def simulasyonu_durdur(self):
        if self.yonetici:
            self.yonetici.durdur()
        self.baslat_btn.config(state="normal")
        self.durdur_btn.config(state="disabled")
        self.durum_etiketi.config(text="● Durduruldu", fg=RENK_VURGU2)

    # ------------------------------------------------------------------
    # THREAD GÜVENLİ GERİ ÇAĞIRIMLAR (callback'ler simülasyon thread'inden
    # gelir; Tkinter ana thread dışı çağrılarda güvenli değildir, bu yüzden
    # bir queue üzerinden ana thread'e aktarılır.)
    # ------------------------------------------------------------------
    def _durum_callback_thread_guvenli(self, durum):
        self.mesaj_kuyrugu.put(("durum", durum))

    def _log_callback_thread_guvenli(self, satir):
        self.mesaj_kuyrugu.put(("log", satir))

    def _kuyruk_dinleyiciyi_baslat(self):
        self._kuyruk_isle()
        self.root.after(150, self._kuyruk_dinleyiciyi_baslat)

    def _kuyruk_isle(self):
        islenen = 0
        while not self.mesaj_kuyrugu.empty() and islenen < 200:
            tip, veri = self.mesaj_kuyrugu.get()
            if tip == "durum":
                self._anlik_durumu_guncelle(veri)
            elif tip == "log":
                self._log_ekle(veri)
            islenen += 1

    # ------------------------------------------------------------------
    def _anlik_durumu_guncelle(self, durum):
        self.kart_zaman.guncelle(f"{durum['sim_zamani']:.0f}")
        self.kart_kisi.guncelle(durum["aktif_kisi"])
        self.kart_isik.guncelle(durum["acik_isik"])

        havalandirma_metin = "AÇIK" if durum["havalandirma"] else "KAPALI"
        self.kart_havalandirma.deger_lbl.config(
            text=havalandirma_metin,
            fg=RENK_VURGU2 if durum["havalandirma"] else RENK_METIN_SOLUK
        )

        self.kart_sicaklik.guncelle(f"{durum['sicaklik_c']:.1f}")
        self.kart_co2.guncelle(f"{durum['co2_ppm']:.0f}")
        self.kart_akim.guncelle(f"{durum['akim_a']:.3f}")
        self.kart_enerji.guncelle(f"{durum['toplam_enerji_wh']:.2f}")

        # Geri dönüşüm kutusu çubuğu
        self._kutu_cubugunu_ciz(durum["kutudaki_atik"], 40)
        self.kutu_metin.config(text=f"{durum['kutudaki_atik']} / 40 atık")

        # PIR kartları
        for sensor_id, kart in self.pir_kartlari.items():
            tetiklendi = durum.get("pir_durum", {}).get(sensor_id, False)
            kart.deger_lbl.config(
                text="HAREKET VAR" if tetiklendi else "HAREKET YOK",
                fg=RENK_VURGU if tetiklendi else RENK_METIN_SOLUK
            )

        if durum["durum_metni"] == "Tamamlandı":
            self.durum_etiketi.config(text="● Tamamlandı", fg=RENK_VURGU2)
            self.baslat_btn.config(state="normal")
            self.durdur_btn.config(state="disabled")

    def _kutu_cubugunu_ciz(self, dolu, kapasite):
        self.kutu_canvas.delete("all")
        genislik = self.kutu_canvas.winfo_width() or 1000
        yukseklik = 36
        oran = min(1.0, dolu / kapasite) if kapasite else 0
        dolu_genislik = int(genislik * oran)

        renk = RENK_VURGU
        if oran >= 0.9:
            renk = RENK_KIRMIZI
        elif oran >= 0.6:
            renk = RENK_VURGU2

        self.kutu_canvas.create_rectangle(0, 0, genislik, yukseklik, fill=RENK_PANEL_ACIK, width=0)
        self.kutu_canvas.create_rectangle(0, 0, dolu_genislik, yukseklik, fill=renk, width=0)

    def _log_ekle(self, satir):
        self.log_metin.insert("end", satir + "\n")
        self.log_metin.see("end")

        if "Çöp atıldı" in satir or "boşaltıldı" in satir or "taştı" in satir:
            self._olaylar_tablosuna_satir_ekle(satir)

    def _olaylar_tablosuna_satir_ekle(self, satir):
        # Basit görsel amaçlı; gerçek veri zaten veritabanına yazılıyor.
        import re
        m = re.search(r"\[([\d.]+) sn\]", satir)
        zaman = m.group(1) if m else "-"
        if "boşaltıldı" in satir:
            self.olaylar_tablo.insert("", 0, values=(zaman, "KUTU BOŞALTILDI", "0", "0.00"))
        elif "taştı" in satir:
            self.olaylar_tablo.insert("", 0, values=(zaman, "KUTU TAŞTI (UYARI)", "-", "-"))
        else:
            m2 = re.search(r"Yığın Yüksekliği: ([\d.]+)m \(Kutudaki: (\d+)/", satir)
            if m2:
                self.olaylar_tablo.insert("", 0, values=(zaman, "ATIK DÜŞTÜ", m2.group(2), m2.group(1)))


def main():
    root = tk.Tk()
    AkilliSinifArayuzu(root)
    root.mainloop()


if __name__ == "__main__":
    main()
