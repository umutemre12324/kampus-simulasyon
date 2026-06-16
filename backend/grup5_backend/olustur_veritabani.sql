-- olustur_veritabani.sql
-- Akıllı Sınıf Otomasyon Sistemi - Takım 5
--
-- Bu betik, akilli_sinif_db adlı PostgreSQL veritabanını oluşturur.
-- Tablo şeması, ilk çalıştırmada db/veritabani.py tarafından otomatik
-- oluşturulur; bu dosya isteğe bağlı olarak veritabanını manuel
-- oluşturmak isteyenler içindir.
--
-- Kullanım (psql ile):
--   psql -U postgres -f olustur_veritabani.sql

CREATE DATABASE akilli_sinif_db
    WITH ENCODING 'UTF8'
    TEMPLATE template0;

-- Not: Bağlantı kullanıcı adı/şifresi db/veritabani.py içindeki
-- VeritabaniYoneticisi sınıfının varsayılan parametrelerinden
-- (user="postgres", password="postgres") veya arayuz/arayuz.py
-- üzerinden değiştirilebilir.
