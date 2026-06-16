# Akıllı Sınıf Otomasyon ve Analitik Karar Destek Sistemi — Takım 5

Bu depo, MDB308 Çok Disiplinli Takım Projesi Ara Raporu'na uygun olarak
hazırlanmış **simülasyon tabanlı** sistemi içerir. Gerçek bir kamera,
ESP32 kartı veya GPIO donanımı **çalıştırılmamaktadır**; raporda da
belirtildiği gibi sistem bir dijital ikiz (digital twin) simülasyonudur.

## Önemli: Kaynak Kod Politikası

`kaynak/dijital_ikiz.py` dosyası, derste paylaşılan **orijinal kaynak
koddur ve hiçbir satırı değiştirilmemiştir.** Bu dosyaya yeni özellik
eklemek yerine, tüm ek işlevler (veritabanı kaydı, PIR sensörü, arayüz)
dış katmanlarda, ayrı dosyalarda uygulanmıştır:

- `kaynak/simulasyon_yoneticisi.py`, `dijital_ikiz.py`'yi bir alt süreç
  (subprocess) olarak **olduğu gibi çalıştırır**, konsol çıktısını okuyup
  ayrıştırır (parse eder) ve PostgreSQL'e yazar. Kaynak kod tek satır
  değişmeden çalışır.
- `kaynak/pir_sensoru.py`, ayrı ve bağımsız bir modül olarak eklenen PIR
  hareket sensörü simülasyonunu içerir.

## Klasör Yapısı

```
akilli_sinif_sistemi/
├── kaynak/
│   ├── dijital_ikiz.py          (ORİJİNAL - DEĞİŞTİRİLMEDİ)
│   ├── pir_sensoru.py           (YENİ - PIR sensör modülü)
│   └── simulasyon_yoneticisi.py (YENİ - çalıştırıcı + parser + DB köprüsü)
├── db/
│   ├── veritabani.py            (YENİ - PostgreSQL şema ve sorgular)
│   └── olustur_veritabani.sql   (YENİ - veritabanı oluşturma betiği)
├── arayuz/
│   └── arayuz.py                (YENİ - Tkinter masaüstü dashboard)
├── loglar/                      (çalışma zamanı log dosyaları için)
└── requirements.txt
```

## Kurulum

1. PostgreSQL'in yerel makinenizde kurulu ve çalışır olduğundan emin olun.
2. Veritabanını oluşturun:
   ```bash
   psql -U postgres -f db/olustur_veritabani.sql
   ```
   (Şema tabloları, program ilk çalıştığında otomatik oluşturulur;
   bu adımı atlarsanız sadece `akilli_sinif_db` veritabanının var
   olduğundan emin olun.)
3. Bağlantı bilgilerinizi gerekirse güncelleyin: `db/veritabani.py`
   içindeki `VeritabaniYoneticisi.__init__` varsayılanları
   (`host`, `port`, `dbname`, `user`, `password`) sizin PostgreSQL
   kurulumunuza göre düzenlenebilir, ya da `arayuz/arayuz.py`
   içinde `SimulasyonYoneticisi(db_ayarlari={...})` şeklinde override
   edebilirsiniz.
4. Python paketlerini kurun:
   ```bash
   pip install -r requirements.txt
   ```

## Çalıştırma

Masaüstü arayüzünü başlatmak için:
```bash
cd arayuz
python arayuz.py
```

Arayüzdeki **"Simülasyonu Başlat"** düğmesi, `dijital_ikiz.py`'yi arka
planda çalıştırır; canlı veriler "Anlık Durum" sekmesinde, geri dönüşüm
kutusu olayları "Geri Dönüşüm Olayları" sekmesinde, PIR sensör
tetiklenmeleri "PIR Hareket Sensörleri" sekmesinde ve ham konsol
çıktısı "Konsol Günlüğü" sekmesinde görüntülenir. Tüm veriler eşzamanlı
olarak PostgreSQL veritabanına (`akilli_sinif_db`) yazılır.

Kaynak kodu veritabanı/arayüz olmadan, orijinal haliyle tek başına
çalıştırmak isterseniz:
```bash
cd kaynak
python dijital_ikiz.py
```

## Veritabanı Şeması (PostgreSQL)

| Tablo | Açıklama |
|---|---|
| `simulasyon_oturumu` | Her çalıştırmayı (run) temsil eden oturum kaydı |
| `ortam_olcumleri` | Saatlik ortam raporları (kişi sayısı, sıcaklık, CO2, enerji, ışık, havalandırma) |
| `geri_donusum_olaylari` | Atık düşme, kutu boşaltma, kutu taşma olayları |
| `pir_hareket_olaylari` | Eklenen PIR sensör ağının hareket tetiklenme kayıtları |

## Eklenen PIR Sensörü Hakkında

Ara raporda donanım listesi ESP32, DHT22 ve BH1750 sensörlerini
içermektedir. Bu çalışmada, düşük maliyetli ve kamera ile çapraz
doğrulama sağlayan bir **PIR (Pasif Kızılötesi) hareket sensörü**
eklenmiştir (`kaynak/pir_sensoru.py`). Gerçek bir PIR sensörü (örn.
HC-SR501) ikili (hareket var/yok) çıkış verir; bu modül, simülasyondaki
aktif kişi sayısına bağlı olasılıksal bir tetiklenme modeli ile bu
davranışı taklit eder ve sonuçlarını `pir_hareket_olaylari` tablosuna
yazar.
