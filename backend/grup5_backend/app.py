# -*- coding: utf-8 -*-
"""
app.py
Akilli Sinif Otomasyon Sistemi - Web arayuzu

Ek web framework gerektirmez. Python'un standart http.server modulu ile:
  - index.html dosyasini yayinlar,
  - simulasyonu web uzerinden baslatip durdurur,
  - canli durum/log akisini Server-Sent Events ile tarayiciya aktarir,
  - PostgreSQL'deki son oturum verilerini API olarak sunar.
"""

from __future__ import annotations

import json
import os
import queue
import random
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")


class WebDurumMerkezi:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.yonetici: Any | None = None
        self.istemciler: list[queue.Queue] = []
        self.loglar: list[str] = []
        self.son_hata: str | None = None
        self._web_akisi_yavaslat = False
        self._son_sim_zamani = 0.0
        self._son_gercek_zaman = time.monotonic()
        self._sim_saniye_basi_gercek_saniye = 360.0
        self.durum: dict[str, Any] = {
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
            "oturum_id": None,
            "calisiyor": False,
            "mod": "Gerçek simülasyon",
        }

    def anlik(self) -> dict[str, Any]:
        with self.lock:
            durum = dict(self.durum)
            durum["loglar"] = self.loglar[-80:]
            durum["son_hata"] = self.son_hata
            if self.yonetici is not None:
                durum["calisiyor"] = bool(self.yonetici.calisiyor)
                durum["oturum_id"] = self.yonetici.oturum_id
            return durum

    def baslat(self) -> tuple[bool, str]:
        with self.lock:
            if self.yonetici is not None and self.yonetici.calisiyor:
                return False, "Simülasyon zaten çalışıyor."
            self.loglar.clear()
            self.son_hata = None
            self._web_akisi_yavaslat = False
            self._son_sim_zamani = 0.0
            self._son_gercek_zaman = time.monotonic()
            self.durum.update({
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
                "durum_metni": "Başlatılıyor",
                "calisiyor": True,
            })

        try:
            from simulasyon_yoneticisi import SimulasyonYoneticisi

            yonetici = SimulasyonYoneticisi(
                durum_callback=self.durum_guncelle,
                log_callback=self.log_ekle,
            )
            mod = "Gerçek simülasyon"
            uyari = None
            with self.lock:
                self._web_akisi_yavaslat = True
        except ModuleNotFoundError as exc:
            yonetici = DemoSimulasyonYoneticisi(
                durum_callback=self.durum_guncelle,
                log_callback=self.log_ekle,
            )
            mod = "Demo akış"
            uyari = (
                f"Eksik Python paketi: {exc.name}. Gerçek simülasyon için "
                "requirements.txt bağımlılıkları kurulmalı; web paneli demo akışla açıldı."
            )

        try:
            yonetici.baslat()
        except Exception as exc:
            mesaj = str(exc)
            with self.lock:
                self.son_hata = mesaj
                self.durum["durum_metni"] = "Hata"
                self.durum["calisiyor"] = False
            self.yayinla("error", {"message": mesaj})
            return False, mesaj

        with self.lock:
            self.yonetici = yonetici
            self.durum["oturum_id"] = yonetici.oturum_id
            self.durum["calisiyor"] = True
            self.durum["durum_metni"] = "Çalışıyor"
            self.durum["mod"] = mod
            self.son_hata = uyari
        if uyari:
            self.log_ekle(f"[WEB UYARI] {uyari}")
        self.yayinla("status", self.anlik())
        return True, "Simülasyon başlatıldı."

    def durdur(self) -> tuple[bool, str]:
        with self.lock:
            yonetici = self.yonetici
        if yonetici is None:
            return False, "Durdurulacak aktif simülasyon yok."
        yonetici.durdur()
        with self.lock:
            self._web_akisi_yavaslat = False
            self.durum["calisiyor"] = False
            self.durum["durum_metni"] = "Durduruldu"
        self.yayinla("status", self.anlik())
        return True, "Simülasyon durduruldu."

    def durum_guncelle(self, durum: dict[str, Any]) -> None:
        self._web_akis_hizini_uygula(durum)
        with self.lock:
            self.durum.update(durum)
            if self.yonetici is not None:
                self.durum["oturum_id"] = self.yonetici.oturum_id
                self.durum["calisiyor"] = bool(self.yonetici.calisiyor)
            else:
                self.durum["calisiyor"] = durum.get("durum_metni") == "Çalışıyor"
        self.yayinla("status", self.anlik())

    def _web_akis_hizini_uygula(self, durum: dict[str, Any]) -> None:
        sim_zamani = float(durum.get("sim_zamani") or 0.0)
        with self.lock:
            yavaslat = self._web_akisi_yavaslat
            onceki_sim = self._son_sim_zamani
            onceki_gercek = self._son_gercek_zaman
            yonetici = self.yonetici

        if not yavaslat or sim_zamani <= onceki_sim:
            with self.lock:
                self._son_sim_zamani = max(self._son_sim_zamani, sim_zamani)
                self._son_gercek_zaman = time.monotonic()
            return

        hedef_bekleme = (sim_zamani - onceki_sim) / self._sim_saniye_basi_gercek_saniye
        gecen = time.monotonic() - onceki_gercek
        kalan = min(10.0, max(0.0, hedef_bekleme - gecen))

        bitis = time.monotonic() + kalan
        while time.monotonic() < bitis:
            if yonetici is not None and not yonetici.calisiyor:
                break
            time.sleep(min(0.15, bitis - time.monotonic()))

        with self.lock:
            self._son_sim_zamani = sim_zamani
            self._son_gercek_zaman = time.monotonic()

    def log_ekle(self, satir: str) -> None:
        with self.lock:
            self.loglar.append(satir)
            self.loglar = self.loglar[-300:]
        self.yayinla("log", {"line": satir})

    def abone_ekle(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=120)
        with self.lock:
            self.istemciler.append(q)
        return q

    def abone_sil(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.istemciler:
                self.istemciler.remove(q)

    def yayinla(self, event: str, payload: dict[str, Any]) -> None:
        veri = {"event": event, "payload": payload, "ts": time.time()}
        with self.lock:
            istemciler = list(self.istemciler)
        for q in istemciler:
            try:
                q.put_nowait(veri)
            except queue.Full:
                pass


merkez = WebDurumMerkezi()


class DemoSimulasyonYoneticisi:
    """Bagimlilikler eksikken web panelinin canli davranisini gosteren hafif akış."""

    def __init__(self, durum_callback, log_callback) -> None:
        self.durum_callback = durum_callback
        self.log_callback = log_callback
        self.oturum_id = "demo"
        self.calisiyor = False
        self._thread: threading.Thread | None = None
        self._durum = {
            "sim_zamani": 0.0,
            "aktif_kisi": 0,
            "acik_isik": 0,
            "havalandirma": False,
            "akim_a": 0.0,
            "sicaklik_c": 22.0,
            "co2_ppm": 400.0,
            "toplam_enerji_wh": 0.0,
            "kutudaki_atik": 0,
            "toplam_atik": 0,
            "pir_durum": {},
            "son_saat_raporu": 0,
            "durum_metni": "Beklemede",
            "oturum_id": self.oturum_id,
            "calisiyor": False,
            "mod": "Demo akış",
        }

    def baslat(self) -> None:
        self.calisiyor = True
        self._thread = threading.Thread(target=self._calistir, daemon=True)
        self._thread.start()

    def durdur(self) -> None:
        self.calisiyor = False

    def _calistir(self) -> None:
        self.log_callback("--- WEB DEMO AKIŞI BAŞLIYOR ---")
        while self.calisiyor and self._durum["sim_zamani"] < 28800:
            time.sleep(0.45)
            sim_zamani = self._durum["sim_zamani"] + 300
            dalga = (1 + __import__("math").sin(sim_zamani / 2400)) / 2
            aktif_kisi = max(0, int(4 + dalga * 32 + random.randint(-3, 3)))
            acik_isik = 0 if aktif_kisi == 0 else min(4, (aktif_kisi + 9) // 10)
            havalandirma = aktif_kisi > 22
            co2 = 420 + aktif_kisi * 18 + (80 if havalandirma else 0)
            sicaklik = 21.8 + aktif_kisi * 0.08 + random.uniform(-0.25, 0.25)
            akim = ((acik_isik * 60) + (1000 if havalandirma else 0)) / 220
            enerji = self._durum["toplam_enerji_wh"] + ((acik_isik * 60) + (1000 if havalandirma else 0)) * (300 / 3600)

            if random.random() < 0.34:
                self._durum["kutudaki_atik"] = min(40, self._durum["kutudaki_atik"] + 1)
                self._durum["toplam_atik"] += 1
                yukseklik = self._durum["kutudaki_atik"] * 0.02
                self.log_callback(
                    f"   [{sim_zamani:.1f} sn] -> Çöp atıldı. Yığın Yüksekliği: "
                    f"{yukseklik:.2f}m (Kutudaki: {self._durum['kutudaki_atik']}/40)"
                )

            if self._durum["kutudaki_atik"] >= 40:
                self.log_callback(f"   [{sim_zamani:.1f} sn] -> [GERİ DÖNÜŞÜM GÖREVLİSİ] Kutu boşaltıldı!")
                self._durum["kutudaki_atik"] = 0

            pir = {f"PIR_{i}": (aktif_kisi > 0 and random.random() < 0.82) for i in range(1, 4)}

            self._durum.update({
                "sim_zamani": sim_zamani,
                "aktif_kisi": aktif_kisi,
                "acik_isik": acik_isik,
                "havalandirma": havalandirma,
                "akim_a": akim,
                "sicaklik_c": sicaklik,
                "co2_ppm": co2,
                "toplam_enerji_wh": enerji,
                "pir_durum": pir,
                "durum_metni": "Çalışıyor",
                "calisiyor": True,
            })

            if sim_zamani % 3600 == 0:
                saat = int(sim_zamani // 3600)
                self.log_callback(f"[{saat}. SAAT RAPORU | Zaman: {sim_zamani:.0f}s] ---")

            self.durum_callback(dict(self._durum))

        self.calisiyor = False
        self._durum["durum_metni"] = "Tamamlandı"
        self._durum["calisiyor"] = False
        self.durum_callback(dict(self._durum))
        self.log_callback("--- WEB DEMO AKIŞI TAMAMLANDI ---")


def json_uyumlu(deger: Any) -> Any:
    if isinstance(deger, Decimal):
        return float(deger)
    if isinstance(deger, (datetime, date)):
        return deger.isoformat()
    if isinstance(deger, list):
        return [json_uyumlu(x) for x in deger]
    if isinstance(deger, dict):
        return {k: json_uyumlu(v) for k, v in deger.items()}
    return deger


def json_bytes(veri: Any) -> bytes:
    return json.dumps(json_uyumlu(veri), ensure_ascii=False).encode("utf-8")


def db_oku(fonksiyon, *args):
    from veritabani import VeritabaniYoneticisi

    vt = VeritabaniYoneticisi()
    vt.baglan()
    try:
        return fonksiyon(vt, *args)
    finally:
        vt.baglantiyi_kapat()


class AkilliSinifHandler(BaseHTTPRequestHandler):
    server_version = "AkilliSinifWeb/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.html_gonder()
        elif parsed.path == "/api/status":
            self.json_gonder(HTTPStatus.OK, merkez.anlik())
        elif parsed.path == "/api/history":
            self.gecmis_gonder(parsed.query)
        elif parsed.path == "/api/events":
            self.sse_gonder()
        else:
            self.json_gonder(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Bulunamadı."})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/start":
            basarili, mesaj = merkez.baslat()
            self.json_gonder(
                HTTPStatus.OK if basarili else HTTPStatus.CONFLICT,
                {"ok": basarili, "message": mesaj, "status": merkez.anlik()},
            )
        elif parsed.path == "/api/stop":
            basarili, mesaj = merkez.durdur()
            self.json_gonder(
                HTTPStatus.OK if basarili else HTTPStatus.CONFLICT,
                {"ok": basarili, "message": mesaj, "status": merkez.anlik()},
            )
        else:
            self.json_gonder(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Bulunamadı."})

    def html_gonder(self) -> None:
        try:
            with open(INDEX_PATH, "rb") as f:
                icerik = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(icerik)))
            self.end_headers()
            self.wfile.write(icerik)
        except OSError as exc:
            self.json_gonder(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(exc)})

    def json_gonder(self, status: HTTPStatus, veri: Any) -> None:
        icerik = json_bytes(veri)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(icerik)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(icerik)

    def gecmis_gonder(self, query: str) -> None:
        params = parse_qs(query)
        oturum_id = None
        if params.get("oturum_id"):
            try:
                oturum_id = int(params["oturum_id"][0])
            except ValueError:
                self.json_gonder(HTTPStatus.BAD_REQUEST, {"ok": False, "message": "Geçersiz oturum_id."})
                return

        try:
            def oku(vt: VeritabaniYoneticisi, secilen_oturum: int | None):
                aktif_oturum = secilen_oturum or vt.son_oturum_id()
                if aktif_oturum is None:
                    return {
                        "oturum_id": None,
                        "ozet": {},
                        "ortam": [],
                        "geri_donusum": [],
                        "pir": [],
                    }
                return {
                    "oturum_id": aktif_oturum,
                    "ozet": vt.oturum_ozet(aktif_oturum),
                    "ortam": vt.ortam_son_kayitlar(aktif_oturum, limit=80),
                    "geri_donusum": vt.geri_donusum_son_kayitlar(aktif_oturum, limit=80),
                    "pir": vt.pir_son_kayitlar(aktif_oturum, limit=80),
                }

            self.json_gonder(HTTPStatus.OK, {"ok": True, "data": db_oku(oku, oturum_id)})
        except Exception as exc:
            self.json_gonder(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "message": str(exc)})

    def sse_gonder(self) -> None:
        q = merkez.abone_ekle()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def yaz(event: str, payload: Any) -> None:
            self.wfile.write(f"event: {event}\n".encode("utf-8"))
            self.wfile.write(b"data: ")
            self.wfile.write(json_bytes(payload))
            self.wfile.write(b"\n\n")
            self.wfile.flush()

        try:
            yaz("status", merkez.anlik())
            while True:
                try:
                    mesaj = q.get(timeout=15)
                    yaz(mesaj["event"], mesaj["payload"])
                except queue.Empty:
                    yaz("ping", {})
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            merkez.abone_sil(q)


def main() -> None:
    adres = ("127.0.0.1", 5000)
    sunucu = ThreadingHTTPServer(adres, AkilliSinifHandler)
    print("Akıllı Sınıf web arayüzü hazır:")
    print("  http://127.0.0.1:5000")
    print("Kapatmak için Ctrl+C")
    sunucu.serve_forever()


if __name__ == "__main__":
    main()
