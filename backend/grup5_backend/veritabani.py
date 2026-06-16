# -*- coding: utf-8 -*-
"""
veritabani.py
PostgreSQL bağlantı ve şema yönetimi.
Akıllı Sınıf Otomasyon Sistemi - Takım 5

Bu modül, dijital_ikiz.py'nin (DEĞİŞTİRİLMEMİŞ orijinal kaynak kod) ürettiği
simülasyon olaylarını PostgreSQL veritabanına yazmak için kullanılır.
Kaynak kod dosyasına hiçbir şekilde dokunulmamıştır; bu modül tamamen
bağımsız ve dış bir katman olarak çalışır.
"""

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json


class VeritabaniYoneticisi:
    """PostgreSQL veritabanı bağlantısını ve şemasını yönetir."""

    def __init__(self, host="localhost", port=5432, dbname="akilli_sinif_db",
                 user="postgres", password="lumos123"):
        self.baglanti_bilgisi = dict(
            host=host, port=port, dbname=dbname, user=user, password=password
        )
        self.conn = None

    # ------------------------------------------------------------------
    # BAĞLANTI
    # ------------------------------------------------------------------
    def baglan(self):
        self.conn = psycopg2.connect(**self.baglanti_bilgisi)
        self.conn.autocommit = True
        return self.conn

    def baglantiyi_kapat(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.baglan()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.baglantiyi_kapat()

    # ------------------------------------------------------------------
    # ŞEMA OLUŞTURMA
    # ------------------------------------------------------------------
    SEMA_SQL = """
    CREATE TABLE IF NOT EXISTS simulasyon_oturumu (
        id              SERIAL PRIMARY KEY,
        baslangic_zamani TIMESTAMP NOT NULL DEFAULT NOW(),
        bitis_zamani     TIMESTAMP,
        toplam_sure_sn   NUMERIC,
        durum            VARCHAR(20) DEFAULT 'CALISIYOR'
    );

    CREATE TABLE IF NOT EXISTS ortam_olcumleri (
        id               SERIAL PRIMARY KEY,
        oturum_id        INTEGER REFERENCES simulasyon_oturumu(id) ON DELETE CASCADE,
        sim_zamani_sn    NUMERIC NOT NULL,
        aktif_kisi_sayisi INTEGER NOT NULL,
        acik_isik_adedi  INTEGER NOT NULL,
        havalandirma_durumu BOOLEAN NOT NULL,
        anlik_akim_a     NUMERIC,
        sicaklik_c       NUMERIC,
        co2_ppm          NUMERIC,
        toplam_enerji_wh NUMERIC,
        kayit_zamani     TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS geri_donusum_olaylari (
        id               SERIAL PRIMARY KEY,
        oturum_id        INTEGER REFERENCES simulasyon_oturumu(id) ON DELETE CASCADE,
        sim_zamani_sn    NUMERIC NOT NULL,
        olay_tipi        VARCHAR(30) NOT NULL,
        kutudaki_atik_adedi INTEGER,
        yigin_yuksekligi_m  NUMERIC,
        kayit_zamani     TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS pir_hareket_olaylari (
        id               SERIAL PRIMARY KEY,
        oturum_id        INTEGER REFERENCES simulasyon_oturumu(id) ON DELETE CASCADE,
        sim_zamani_sn    NUMERIC NOT NULL,
        sensor_id        VARCHAR(30) NOT NULL,
        hareket_algilandi BOOLEAN NOT NULL,
        oda_doluluk_tahmini INTEGER,
        kayit_zamani     TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_ortam_oturum ON ortam_olcumleri(oturum_id);
    CREATE INDEX IF NOT EXISTS idx_geridonusum_oturum ON geri_donusum_olaylari(oturum_id);
    CREATE INDEX IF NOT EXISTS idx_pir_oturum ON pir_hareket_olaylari(oturum_id);
    """

    def semayi_olustur(self):
        with self.conn.cursor() as cur:
            cur.execute(self.SEMA_SQL)

    # ------------------------------------------------------------------
    # OTURUM İŞLEMLERİ
    # ------------------------------------------------------------------
    def oturum_baslat(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO simulasyon_oturumu (durum) VALUES ('CALISIYOR') RETURNING id;"
            )
            return cur.fetchone()[0]

    def oturum_bitir(self, oturum_id, toplam_sure_sn):
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE simulasyon_oturumu
                   SET bitis_zamani = NOW(), toplam_sure_sn = %s, durum = 'TAMAMLANDI'
                   WHERE id = %s;""",
                (toplam_sure_sn, oturum_id)
            )

    # ------------------------------------------------------------------
    # VERİ YAZMA
    # ------------------------------------------------------------------
    def ortam_olcumu_ekle(self, oturum_id, sim_zamani_sn, aktif_kisi_sayisi,
                           acik_isik_adedi, havalandirma_durumu, anlik_akim_a,
                           sicaklik_c, co2_ppm, toplam_enerji_wh):
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ortam_olcumleri
                   (oturum_id, sim_zamani_sn, aktif_kisi_sayisi, acik_isik_adedi,
                    havalandirma_durumu, anlik_akim_a, sicaklik_c, co2_ppm, toplam_enerji_wh)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);""",
                (oturum_id, sim_zamani_sn, aktif_kisi_sayisi, acik_isik_adedi,
                 havalandirma_durumu, anlik_akim_a, sicaklik_c, co2_ppm, toplam_enerji_wh)
            )

    def geri_donusum_olayi_ekle(self, oturum_id, sim_zamani_sn, olay_tipi,
                                 kutudaki_atik_adedi=None, yigin_yuksekligi_m=None):
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO geri_donusum_olaylari
                   (oturum_id, sim_zamani_sn, olay_tipi, kutudaki_atik_adedi, yigin_yuksekligi_m)
                   VALUES (%s,%s,%s,%s,%s);""",
                (oturum_id, sim_zamani_sn, olay_tipi, kutudaki_atik_adedi, yigin_yuksekligi_m)
            )

    def pir_olayi_ekle(self, oturum_id, sim_zamani_sn, sensor_id,
                        hareket_algilandi, oda_doluluk_tahmini):
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pir_hareket_olaylari
                   (oturum_id, sim_zamani_sn, sensor_id, hareket_algilandi, oda_doluluk_tahmini)
                   VALUES (%s,%s,%s,%s,%s);""",
                (oturum_id, sim_zamani_sn, sensor_id, hareket_algilandi, oda_doluluk_tahmini)
            )

    # ------------------------------------------------------------------
    # VERİ OKUMA (Arayüz için)
    # ------------------------------------------------------------------
    def son_oturum_id(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM simulasyon_oturumu ORDER BY id DESC LIMIT 1;")
            row = cur.fetchone()
            return row[0] if row else None

    def ortam_son_kayitlar(self, oturum_id, limit=200):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM ortam_olcumleri
                   WHERE oturum_id = %s
                   ORDER BY sim_zamani_sn DESC LIMIT %s;""",
                (oturum_id, limit)
            )
            return cur.fetchall()

    def geri_donusum_son_kayitlar(self, oturum_id, limit=50):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM geri_donusum_olaylari
                   WHERE oturum_id = %s
                   ORDER BY sim_zamani_sn DESC LIMIT %s;""",
                (oturum_id, limit)
            )
            return cur.fetchall()

    def pir_son_kayitlar(self, oturum_id, limit=50):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM pir_hareket_olaylari
                   WHERE oturum_id = %s
                   ORDER BY sim_zamani_sn DESC LIMIT %s;""",
                (oturum_id, limit)
            )
            return cur.fetchall()

    def oturum_ozet(self, oturum_id):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT
                       (SELECT COUNT(*) FROM geri_donusum_olaylari
                        WHERE oturum_id=%s AND olay_tipi='ATIK_DUSTU')      AS toplam_atik,
                       (SELECT COUNT(*) FROM pir_hareket_olaylari
                        WHERE oturum_id=%s AND hareket_algilandi=TRUE)      AS toplam_pir_tetik,
                       (SELECT MAX(toplam_enerji_wh) FROM ortam_olcumleri
                        WHERE oturum_id=%s)                                 AS guncel_enerji_wh,
                       (SELECT MAX(aktif_kisi_sayisi) FROM ortam_olcumleri
                        WHERE oturum_id=%s)                                 AS maks_kisi_sayisi
                   ;""",
                (oturum_id, oturum_id, oturum_id, oturum_id)
            )
            return cur.fetchone()


if __name__ == "__main__":
    # Basit bağlantı/şema testi
    vt = VeritabaniYoneticisi()
    vt.baglan()
    vt.semayi_olustur()
    print("Veritabanı şeması başarıyla oluşturuldu / kontrol edildi.")
    vt.baglantiyi_kapat()
