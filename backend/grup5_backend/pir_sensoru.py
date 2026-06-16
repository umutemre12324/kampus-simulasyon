# -*- coding: utf-8 -*-
"""
pir_sensoru.py
PIR (Passive Infrared) Hareket Sensörü Modülü
Akıllı Sınıf Otomasyon Sistemi - Takım 5

Bu modül, dijital_ikiz.py (ORİJİNAL KAYNAK KOD - değiştirilmemiştir) içindeki
Sensor sınıf hiyerarşisiyle aynı tasarım deseninde, ama tamamen ayrı ve
bağımsız bir dosyada tanımlanmış PIR hareket sensörünü içerir.

Ara raporda belirtilen "kişi sayısını gerçek zamanlı tespit etme" hedefini
düşük maliyetli ve basit bir donanımla desteklemek amacıyla eklenmiştir.
PIR sensörü, oda içindeki hareketi ikili (var/yok) olarak algılar ve
hâlihazırda simülasyonda hesaplanan 'ActiveOccupants' sayısına dayanarak
gerçekçi bir tetiklenme olasılığı üretir.
"""

import numpy as np


class PIRSensor:
    """
    Pasif Kızılötesi (PIR) hareket sensörünü simüle eder.

    Gerçek bir PIR sensörü (örn. HC-SR501), algılama alanındaki sıcaklık
    farkından kaynaklanan kızılötesi değişimi tespit ederek hareket var/yok
    bilgisini dijital (HIGH/LOW) olarak verir. Bu sınıf, odadaki aktif kişi
    sayısına bağlı olasılıksal bir model ile bu davranışı taklit eder.
    """

    def __init__(self, sensor_id="PIR_1", algilama_aralik_sn=2.0,
                 yanlis_pozitif_orani=0.02, duyarlilik_yaricap_m=6.0):
        self.sensor_id = sensor_id
        self.algilama_aralik_sn = algilama_aralik_sn   # tipik HC-SR501 yeniden tetiklenme aralığı
        self.yanlis_pozitif_orani = yanlis_pozitif_orani  # gürültüden kaynaklı yanlış tetiklenme
        self.duyarlilik_yaricap_m = duyarlilik_yaricap_m
        self.son_tetiklenme_zamani = None
        self.durum = False  # True: hareket algılandı (HIGH), False: hareket yok (LOW)

    def oku(self, aktif_kisi_sayisi, sim_zamani):
        """
        Odadaki aktif kişi sayısına bağlı olarak PIR sensör çıkışını üretir.
        Kişi sayısı arttıkça hareket algılama olasılığı artar (oda boşken
        düşük ama sıfır olmayan bir yanlış-pozitif ihtimali korunur).
        """
        if aktif_kisi_sayisi <= 0:
            algilama_olasiligi = self.yanlis_pozitif_orani
        else:
            # Kişi sayısı arttıkça doygunluğa giden olasılık eğrisi
            algilama_olasiligi = min(0.97, 0.55 + 0.08 * aktif_kisi_sayisi)

        hareket_var = np.random.rand() < algilama_olasiligi

        if hareket_var:
            self.son_tetiklenme_zamani = sim_zamani
            self.durum = True
        else:
            # Yeniden tetiklenme aralığı dolmadıysa sensör hâlâ HIGH tutabilir
            if (self.son_tetiklenme_zamani is not None and
                    (sim_zamani - self.son_tetiklenme_zamani) < self.algilama_aralik_sn):
                self.durum = True
            else:
                self.durum = False

        return self.durum

    def oda_doluluk_tahmini(self, aktif_kisi_sayisi):
        """
        PIR ikili bir sensör olduğu için kişi SAYISINI veremez; ancak
        kamera (YOLO) verisiyle çapraz doğrulama amacıyla basit bir
        'hareket var ise en az 1 kişi' tahmini döndürür. Asıl kişi sayısı
        kaynak koddaki kamera/occupancy mantığından (ActiveOccupants) gelir.
        """
        return aktif_kisi_sayisi if self.durum else 0


class PIRSensorAgi:
    """
    Sınıfın farklı köşelerine yerleştirilmiş birden fazla PIR sensörünü
    yönetir (ör. kapı girişi + iki köşe). Herhangi biri tetiklenirse oda
    'hareketli' kabul edilir; bu, tek nokta körlüğünü azaltır.
    """

    def __init__(self, sensor_sayisi=3):
        self.sensorler = [
            PIRSensor(sensor_id=f"PIR_{i+1}") for i in range(sensor_sayisi)
        ]

    def oku_hepsi(self, aktif_kisi_sayisi, sim_zamani):
        sonuclar = {}
        for sensor in self.sensorler:
            sonuclar[sensor.sensor_id] = sensor.oku(aktif_kisi_sayisi, sim_zamani)
        return sonuclar

    def herhangi_biri_tetiklendi(self, sonuclar):
        return any(sonuclar.values())
