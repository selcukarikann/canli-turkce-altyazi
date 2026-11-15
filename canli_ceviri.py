"""Canlı Türkçe altyazı: capture card görüntüsünü gösterir, İngilizce altyazıyı
okur, çevirir ve Türkçesini görüntünün üstüne yazar.

Çalıştırma:  py canli_ceviri.py            (capture card)
             py canli_ceviri.py --video x.mp4   (dosyayla deneme)
"""
import argparse
import difflib
import json
import os
import queue
import re
import shutil
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QPainter, QPen
from PySide6.QtMultimedia import (
    QAudioOutput,
    QAudioSink,
    QAudioSource,
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
    QMediaPlayer,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QInputDialog, QMainWindow, QMenu, QWidget

from cevirmen import Cevirmen
from okuyucu import Okuyucu, gecerli_mi, hazirla, ortak_sayisi, temizle

_RAKAM = re.compile(r"\d+")


def _benzer(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()

UYGULAMA_ADI = "Canlı Türkçe Altyazı"
SURUM = "1.0.0"

# Program klasörü kurulumdan sonra yazmaya kapalıdır; ayarlar ve çeviri hafızası
# kullanıcının kendi veri klasöründe tutulur.
PROGRAM_KLASORU = os.path.dirname(
    sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
VERI_KLASORU = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "CanliTurkceAltyazi")
os.makedirs(VERI_KLASORU, exist_ok=True)
AYAR_YOLU = os.path.join(VERI_KLASORU, "ayarlar.json")
ONBELLEK_YOLU = os.path.join(VERI_KLASORU, "ceviri_onbellek.json")
for _ad in ("ayarlar.json", "ceviri_onbellek.json"):  # eski yerdeki dosyaları taşı
    _eski, _yeni = os.path.join(PROGRAM_KLASORU, _ad), os.path.join(VERI_KLASORU, _ad)
    if os.path.exists(_eski) and not os.path.exists(_yeni):
        try:
            shutil.copy2(_eski, _yeni)
        except OSError:
            pass

VARSAYILAN = {
    "video_aygiti": "",  # boşsa ilk açılışta sorulur
    "ses_aygiti": "",
    "ses_acik": True,
    "motor": "google",  # "google", "ollama" ya da "karma" (önce Google, sonra yerel)
    "ollama_model": "gemma3:12b",
    # bölgeler: [sol, üst, genişlik, yükseklik] — görüntünün oranı olarak
    "bolgeler": {"altyazi": [0.15, 0.74, 0.70, 0.20], "gorev": None},
    "yazi_boyutu": 0.034,  # görüntü yüksekliğinin oranı
    "kutu_opakligi": 0.85,
    "parlak_filtre": False,
    "okuma_araligi_ms": 100,
}
BOLGE_ADLARI = {"altyazi": "Altyazı", "gorev": "Görev metni"}


def ayar_yukle():
    ayar = json.loads(json.dumps(VARSAYILAN))
    try:
        with open(AYAR_YOLU, encoding="utf-8") as f:
            kayitli = json.load(f)
        for k, v in kayitli.items():
            if k == "bolgeler":
                ayar["bolgeler"].update(v)
            else:
                ayar[k] = v
    except (OSError, ValueError):
        pass
    return ayar


def ayar_kaydet(ayar):
    try:
        with open(AYAR_YOLU, "w", encoding="utf-8") as f:
            json.dump(ayar, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def qimage_rgb(img):
    img = img.convertToFormat(img.Format.Format_RGB888)
    g, y = img.width(), img.height()
    ham = np.frombuffer(img.constBits(), np.uint8).reshape(y, img.bytesPerLine())
    return ham[:, : g * 3].reshape(y, g, 3).copy()


# ---------------------------------------------------------------- okuma işçisi
class Isci(threading.Thread):
    """Kareleri alır, altyazıyı okur, yeni metinleri çeviriye gönderir."""

    def __init__(self, ayar, cevirmen, pencere):
        super().__init__(daemon=True)
        self.ayar = ayar
        self.cevirmen = cevirmen
        self.pencere = pencere
        self.kuyruk = queue.Queue(maxsize=1)
        self.durum = {
            ad: {"ozet": None, "son": ("", None), "kaynak": "", "aday": None, "sira": 0,
                 "son_gorulme": 0.0, "bos": True}
            for ad in BOLGE_ADLARI
        }
        self.okuyucu = None
        # Çeviri sırası: her bölgeden yalnızca EN GÜNCEL satır bekler; eskisi
        # çevrilmeden yenisi gelirse eskisi atılır. Böylece sıra hiç birikmez.
        self.kosul = threading.Condition()
        self.bekleyen = {ad: None for ad in BOLGE_ADLARI}
        self.mesgul = {ad: False for ad in BOLGE_ADLARI}
        for ad in BOLGE_ADLARI:
            threading.Thread(target=self._ceviri_dongusu, args=(ad,), daemon=True).start()

    def bosta(self):
        return self.kuyruk.empty()

    def gonder(self, parcalar):
        try:
            self.kuyruk.put_nowait(parcalar)
        except queue.Full:
            pass

    def run(self):
        try:
            self.okuyucu = Okuyucu()
        except Exception as h:  # noqa: BLE001
            self.pencere.bildirim.emit(str(h))
            return
        if not self.okuyucu.ingilizce:
            self.pencere.kalici_uyari.emit(
                "Windows'ta İngilizce yazı tanıma paketi kurulu değil, okuma hatalı olabilir. "
                "Ayarlar > Saat ve Dil > Dil ve Bölge > Dil ekle > English (United States) "
                "kur, sonra programı yeniden aç.")
        while True:
            parcalar = self.kuyruk.get()
            for ad, img in parcalar.items():
                try:
                    self._isle(ad, img)
                except Exception as h:  # noqa: BLE001
                    self.pencere.bildirim.emit(f"Okuma hatası: {h}")

    def _isle(self, ad, img):
        d = self.durum[ad]
        simdi = time.monotonic()
        rgb = qimage_rgb(img)
        gri = hazirla(rgb, self.ayar["parlak_filtre"])
        ozet = hash(gri[::4, ::4].tobytes())
        if ozet == d["ozet"]:
            metin, kutu = d["son"]  # görüntü değişmedi, yeniden okumaya gerek yok
        else:
            d["ozet"] = ozet
            metin, kutu = self.okuyucu.oku(gri)
            metin = temizle(metin)
            d["son"] = (metin, kutu)
        if not gecerli_mi(metin):
            d["aday"] = None
            self._kayboldu_mu(ad, d, simdi)
            return
        # sayaçlar (ör. "1583 m") değiştikçe satır yeni sayılmasın
        anahtar = _RAKAM.sub("#", metin.lower())
        if d["kaynak"] and _benzer(anahtar, d["kaynak"]) > 0.85:
            d["son_gorulme"] = simdi  # aynı satır hâlâ ekranda
            d["aday"] = None
            return
        # Farklı bir yazı: ya yeni satır ya da gürültü. İçinde birkaç sık kelime
        # geçen düzgün bir cümleyse hemen çevrilir; değilse bir sonraki okumada
        # da aynı çıkması beklenir (gürültü her karede değişir, yazı değişmez).
        onayli = ortak_sayisi(metin) >= 3 or (
            d["aday"] is not None and _benzer(anahtar, d["aday"]) > 0.9)
        if not onayli:
            d["aday"] = anahtar
            self._kayboldu_mu(ad, d, simdi)
            return
        d["aday"] = None
        d["kaynak"] = anahtar
        d["son_gorulme"] = simdi
        d["bos"] = False
        d["sira"] += 1
        sira = d["sira"]
        self.pencere.yeni_kaynak.emit(ad, sira, kutu)
        with self.kosul:
            self.bekleyen[ad] = (sira, metin)
            self.kosul.notify_all()

    def _kayboldu_mu(self, ad, d, simdi):
        """Gösterilen satır bir süredir okunmuyorsa ekrandaki çeviriyi kaldırır."""
        if not d["bos"] and simdi - d["son_gorulme"] > 0.45:
            d["bos"] = True
            d["kaynak"] = ""
            with self.kosul:
                self.bekleyen[ad] = None
            self.pencere.temizle.emit(ad)

    def _ceviri_dongusu(self, ad):
        while True:
            with self.kosul:
                # görev metni, bekleyen ya da çevrilmekte olan altyazı varken sıraya girmez
                while self.bekleyen[ad] is None or (ad != "altyazi" and (
                        self.mesgul["altyazi"] or self.bekleyen["altyazi"] is not None)):
                    self.kosul.wait()
                sira, metin = self.bekleyen[ad]
                self.bekleyen[ad] = None
                self.mesgul[ad] = True
            try:
                # çeviri parça parça gelebilir (önce hızlı/kısmi sonuç, sonra kesin olan)
                self.cevirmen.cevir(
                    metin, lambda tr, _kesin, s=sira: self.pencere.sonuc.emit(ad, s, tr))
                if self.cevirmen.uyari:
                    self.pencere.bildirim.emit(self.cevirmen.uyari)
            except Exception as h:  # noqa: BLE001
                self.pencere.bildirim.emit(f"Çeviri hatası: {h}")
            finally:
                with self.kosul:
                    self.mesgul[ad] = False
                    self.kosul.notify_all()


# ------------------------------------------------------------- yazı katmanı
class Katman(QWidget):
    """Videonun üstünde duran saydam katman: Türkçe yazılar, bölge seçimi, menü."""

    def __init__(self, pencere):
        super().__init__(pencere, Qt.Tool | Qt.FramelessWindowHint)
        self.p = pencere
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.metinler = {ad: "" for ad in BOLGE_ADLARI}
        self.kutular = {ad: None for ad in BOLGE_ADLARI}  # İngilizce yazının yeri
        self.secim_modu = None  # "altyazi" / "gorev"
        self.surukle = None  # (başlangıç, bitiş)
        self.bildirim = ""
        self.bildirim_bitis = 0.0
        self.imlec_sayaci = QTimer(self, interval=2500, singleShot=True)
        self.imlec_sayaci.timeout.connect(self._imlec_gizle)

    def _imlec_gizle(self):
        if not self.secim_modu:
            self.setCursor(Qt.BlankCursor)

    # videonun katman içindeki gerçek alanı (kenar boşlukları hariç)
    def video_alani(self):
        g, y = self.width(), self.height()
        oran = self.p.kare_orani
        if g / max(1, y) > oran:
            vg = y * oran
            return QRectF((g - vg) / 2, 0, vg, y)
        vy = g / oran
        return QRectF(0, (y - vy) / 2, g, vy)

    def bolge_alani(self, ad):
        b = self.p.ayar["bolgeler"].get(ad)
        if not b:
            return None
        v = self.video_alani()
        return QRectF(
            v.x() + b[0] * v.width(), v.y() + b[1] * v.height(),
            b[2] * v.width(), b[3] * v.height(),
        )

    def paintEvent(self, _):
        r = QPainter(self)
        r.setRenderHint(QPainter.Antialiasing)
        # neredeyse görünmez dolgu: fare tıklamaları bu katmana gelsin
        r.fillRect(self.rect(), QColor(0, 0, 0, 1))
        v = self.video_alani()
        ayar = self.p.ayar

        yazi = QFont("Segoe UI")
        yazi.setPixelSize(max(12, int(v.height() * ayar["yazi_boyutu"])))
        yazi.setWeight(QFont.DemiBold)
        r.setFont(yazi)

        if not self.secim_modu:
            for ad, metin in self.metinler.items():
                alan = self.bolge_alani(ad)
                if not metin or alan is None:
                    continue
                bosluk = yazi.pixelSize() * 0.5
                ic = alan.adjusted(bosluk, 0, -bosluk, 0)
                olcu = r.boundingRect(ic, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, metin)
                kutu = QRectF(0, 0, olcu.width() + 2 * bosluk, olcu.height() + bosluk)
                k = self.kutular.get(ad)
                if k:  # İngilizce yazının tam üstüne otur ve onu ört
                    ing = QRectF(alan.x() + k[0] * alan.width(), alan.y() + k[1] * alan.height(),
                                 k[2] * alan.width(), k[3] * alan.height())
                    ing.adjust(-bosluk, -bosluk / 2, bosluk, bosluk / 2)
                else:
                    ing = QRectF(alan.center().x(), alan.bottom() - kutu.height(), 0, kutu.height())
                kutu.moveCenter(ing.center())
                ortu = ing.united(kutu)
                kayma = min(0, v.bottom() - 4 - ortu.bottom()) + max(0, v.top() + 4 - ortu.top())
                ortu.translate(0, kayma)
                kutu.translate(0, kayma)
                r.setPen(Qt.NoPen)
                r.setBrush(QColor(0, 0, 0, int(255 * ayar["kutu_opakligi"])))
                r.drawRoundedRect(ortu, 8, 8)
                r.setPen(QColor(255, 255, 255))
                r.drawText(kutu, Qt.AlignCenter | Qt.TextWordWrap, metin)
        else:
            r.fillRect(self.rect(), QColor(0, 0, 0, 110))
            for ad in BOLGE_ADLARI:
                alan = self.bolge_alani(ad)
                if alan is None:
                    continue
                r.setPen(QPen(QColor(120, 200, 255), 2, Qt.DashLine))
                r.setBrush(Qt.NoBrush)
                r.drawRect(alan)
                r.drawText(alan.adjusted(6, 4, 0, 0), Qt.AlignLeft | Qt.AlignTop, BOLGE_ADLARI[ad])
            if self.surukle:
                r.setPen(QPen(QColor(255, 220, 60), 3))
                r.setBrush(QColor(255, 220, 60, 40))
                r.drawRect(QRectF(self.surukle[0], self.surukle[1]).normalized())
            r.setPen(QColor(255, 255, 255))
            r.drawText(
                QRectF(v.x(), v.y() + 20, v.width(), 80), Qt.AlignHCenter | Qt.AlignTop,
                f"{BOLGE_ADLARI[self.secim_modu]} bölgesi: İngilizce yazının çıktığı alanı "
                "fareyle sürükleyerek çiz  (Esc: vazgeç)",
            )

        if self.bildirim and time.monotonic() < self.bildirim_bitis:
            kucuk = QFont("Segoe UI")
            kucuk.setPixelSize(max(11, int(v.height() * 0.022)))
            r.setFont(kucuk)
            alan = QRectF(v.x() + 16, v.y() + 12, v.width() - 32, 200)
            olcu = r.boundingRect(alan, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.bildirim)
            r.setPen(Qt.NoPen)
            r.setBrush(QColor(0, 0, 0, 190))
            r.drawRoundedRect(olcu.adjusted(-8, -5, 8, 5), 6, 6)
            r.setPen(QColor(255, 230, 150))
            r.drawText(olcu, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.bildirim)

    # ---- fare ve klavye ----
    def mousePressEvent(self, e):
        if self.secim_modu and e.button() == Qt.LeftButton:
            self.surukle = (e.position(), e.position())
            self.update()

    def mouseMoveEvent(self, e):
        self.unsetCursor() if not self.secim_modu else self.setCursor(Qt.CrossCursor)
        self.imlec_sayaci.start()
        if self.secim_modu and self.surukle:
            self.surukle = (self.surukle[0], e.position())
            self.update()

    def mouseReleaseEvent(self, e):
        if not (self.secim_modu and self.surukle and e.button() == Qt.LeftButton):
            return
        d = QRectF(self.surukle[0], self.surukle[1]).normalized().intersected(self.video_alani())
        v = self.video_alani()
        ad, self.surukle = self.secim_modu, None
        if d.width() > 30 and d.height() > 12:
            self.p.ayar["bolgeler"][ad] = [
                round((d.x() - v.x()) / v.width(), 4), round((d.y() - v.y()) / v.height(), 4),
                round(d.width() / v.width(), 4), round(d.height() / v.height(), 4),
            ]
            ayar_kaydet(self.p.ayar)
            self.secim_modu = None
            self.p.bildir(f"{BOLGE_ADLARI[ad]} bölgesi kaydedildi")
        self.update()

    def mouseDoubleClickEvent(self, _):
        if not self.secim_modu:
            self.p.tam_ekran_degistir()

    def contextMenuEvent(self, e):
        self.unsetCursor()
        self.p.menu().exec(e.globalPos())

    def keyPressEvent(self, e):
        self.p.tus(e)


# ---------------------------------------------------------------- ana pencere
class Pencere(QMainWindow):
    yeni_kaynak = Signal(str, int, object)
    sonuc = Signal(str, int, str)
    temizle = Signal(str)
    bildirim = Signal(str)
    kalici_uyari = Signal(str)  # uzun süre ekranda kalan önemli uyarı

    def __init__(self, ayar, video_dosyasi=None):
        super().__init__()
        self.ayar = ayar
        self.setWindowTitle(UYGULAMA_ADI)
        self.resize(1280, 720)
        self.setStyleSheet("background:#000;")
        self.kare_orani = 16 / 9
        self.ceviri_acik = True
        self.video = QVideoWidget(self)
        self.setCentralWidget(self.video)
        self.katman = Katman(self)

        self.gui = {ad: {"sira": 0, "gosterim": 0.0, "kaynak_var": False} for ad in BOLGE_ADLARI}
        self.yeni_kaynak.connect(self._yeni_kaynak)
        self.sonuc.connect(self._sonuc)
        self.temizle.connect(self._temizle)
        self.bildirim.connect(self.bildir)
        self.kalici_uyari.connect(lambda yazi: self.bildir(yazi, 45))

        self.cevirmen = Cevirmen(ayar, ONBELLEK_YOLU)
        self.isci = Isci(ayar, self.cevirmen, self)
        self.isci.start()
        if ayar["motor"] in ("ollama", "karma"):
            threading.Thread(target=self._ollama_hazirla, daemon=True).start()

        # görüntü kaynağı
        self.oturum = self.kamera = self.oynatici = None
        self.ses_kaynak = self.ses_cikis = None
        if video_dosyasi:
            self.oynatici = QMediaPlayer(self)
            self._dosya_ses = QAudioOutput(self)
            self.oynatici.setAudioOutput(self._dosya_ses)
            self.oynatici.setVideoOutput(self.video)
            self.oynatici.setSource(QUrl.fromLocalFile(os.path.abspath(video_dosyasi)))
            self.oynatici.setLoops(QMediaPlayer.Infinite)
            self.oynatici.play()
        else:
            self.kamera_ac()
            self.ses_ac()

        self.okuma = QTimer(self, interval=ayar["okuma_araligi_ms"])
        self.okuma.timeout.connect(self.kare_al)
        self.okuma.start()
        self.installEventFilter(self)
        self.bildir("Sağ tık: menü   •   F2: altyazı bölgesi   •   F4: çeviri aç/kapat   •   F11 / çift tık: tam ekran", 7)

    # ---- aygıtlar ----
    def kamera_ac(self):
        aygitlar = QMediaDevices.videoInputs()
        if self.kamera:
            self.kamera.stop()
        if not aygitlar:
            self.bildir("Hiç görüntü aygıtı bulunamadı", 15)
            return
        aranan = self.ayar["video_aygiti"].lower()
        secilen = next(
            (a for a in aygitlar if aranan and aranan in a.description().lower()), None)
        if secilen is None:
            # kayıtlı aygıt yok ya da takılı değil: kullanıcıya sor
            adlar = [a.description() for a in aygitlar]
            ipucu = ("capture", "hdmi", "cam link", "elgato", "avermedia", "game", "usb video")
            tahmin = next((i for i, ad in enumerate(adlar)
                           if any(k in ad.lower() for k in ipucu)), 0)
            ad, tamam = QInputDialog.getItem(
                self, UYGULAMA_ADI,
                "Oyun görüntüsünün geldiği aygıtı seç (capture card):", adlar, tahmin, False)
            if not tamam:
                self.bildir("Görüntü aygıtı seçilmedi (sağ tık > Görüntü aygıtı)", 15)
                return
            secilen = aygitlar[adlar.index(ad)]
            self.ayar["video_aygiti"] = ad
            ayar_kaydet(self.ayar)
        self.kamera = QCamera(secilen, self)
        uygun = [f for f in secilen.videoFormats() if f.resolution().width() <= 1920]
        if uygun:
            en_iyi = max(uygun, key=lambda f: (
                f.resolution().width() * f.resolution().height(), f.maxFrameRate()))
            self.kamera.setCameraFormat(en_iyi)
        self.kamera.errorOccurred.connect(
            lambda _h, yazi: self.bildir(f"Görüntü aygıtı hatası: {yazi}", 15))
        self.oturum = QMediaCaptureSession(self)
        self.oturum.setCamera(self.kamera)
        self.oturum.setVideoOutput(self.video)
        self.kamera.start()

    def ses_ac(self):
        for nesne in (self.ses_kaynak, self.ses_cikis):
            if nesne:
                nesne.stop()
        self.ses_kaynak = self.ses_cikis = None
        if not self.ayar["ses_acik"]:
            return
        girisler = QMediaDevices.audioInputs()
        aranan = self.ayar["ses_aygiti"].lower()
        giris = next(
            (a for a in girisler if aranan and aranan in a.description().lower()), None)
        if giris is None:
            # capture card'ın ses girişi çoğunlukla görüntü aygıtının adını taşır
            video_adi = self.ayar["video_aygiti"].lower()
            giris = next(
                (a for a in girisler if video_adi and video_adi in a.description().lower()), None)
            if giris is not None:
                self.ayar["ses_aygiti"] = self.ayar["video_aygiti"]
            else:
                yok = "Ses aktarma (sesi başka yoldan dinliyorum)"
                adlar = [a.description() for a in girisler] + [yok]
                ad, tamam = QInputDialog.getItem(
                    self, UYGULAMA_ADI,
                    "Oyun sesinin geldiği aygıtı seç (capture card'ın ses girişi):",
                    adlar, len(adlar) - 1, False)
                if not tamam or ad == yok:
                    self.ayar["ses_acik"] = False
                    ayar_kaydet(self.ayar)
                    return
                giris = girisler[adlar.index(ad)]
                self.ayar["ses_aygiti"] = ad
            ayar_kaydet(self.ayar)
        cikis = QMediaDevices.defaultAudioOutput()
        bicim = giris.preferredFormat()
        if not cikis.isFormatSupported(bicim):
            bicim = cikis.preferredFormat()
        self.ses_kaynak = QAudioSource(giris, bicim, self)
        self.ses_cikis = QAudioSink(cikis, bicim, self)
        hedef = self.ses_cikis.start()
        kaynak = self.ses_kaynak.start()
        if hedef is None or kaynak is None:
            self.bildir("Ses başlatılamadı", 10)
            return
        self._ses_uc = (kaynak, hedef)
        kaynak.readyRead.connect(lambda: hedef.write(kaynak.readAll()))

    def _ollama_hazirla(self):
        self.bildirim.emit("Yerel yapay zekâ modeli yükleniyor…")
        self.cevirmen.ollama_hazirla()
        self.bildirim.emit(self.cevirmen.uyari or "Yerel yapay zekâ hazır")

    # ---- kare okuma ----
    def kare_al(self):
        if not self.ceviri_acik or self.katman.secim_modu or not self.isci.bosta():
            return
        kare = self.video.videoSink().videoFrame()
        if not kare.isValid():
            return
        img = kare.toImage()
        if img.isNull() or img.height() == 0:
            return
        oran = img.width() / img.height()
        if abs(oran - self.kare_orani) > 0.01:
            self.kare_orani = oran
            self.katman.update()
        parcalar = {}
        for ad, b in self.ayar["bolgeler"].items():
            if not b:
                continue
            x, y = int(b[0] * img.width()), int(b[1] * img.height())
            g, yuk = int(b[2] * img.width()), int(b[3] * img.height())
            if g > 8 and yuk > 8:
                parcalar[ad] = img.copy(x, y, g, yuk)
        if parcalar:
            self.isci.gonder(parcalar)

    # ---- çeviri sonuçları ----
    def _yeni_kaynak(self, ad, sira, kutu):
        self.gui[ad].update(sira=sira, kaynak_var=True, kutu=kutu)

    def _sonuc(self, ad, sira, metin):
        d = self.gui[ad]
        if sira != d["sira"]:
            return  # daha yeni bir satır var
        self.katman.metinler[ad] = metin
        self.katman.kutular[ad] = d.get("kutu")
        d["gosterim"] = time.monotonic()
        self.katman.update()
        if not d["kaynak_var"]:
            QTimer.singleShot(1500, lambda: self._sil(ad, sira))

    def _temizle(self, ad):
        d = self.gui[ad]
        d["kaynak_var"] = False
        kalan = 1.2 - (time.monotonic() - d["gosterim"])
        sira = d["sira"]
        QTimer.singleShot(int(max(0, kalan) * 1000), lambda: self._sil(ad, sira))

    def _sil(self, ad, sira):
        d = self.gui[ad]
        if d["sira"] == sira and not d["kaynak_var"]:
            self.katman.metinler[ad] = ""
            self.katman.update()

    def bildir(self, yazi, sure=4):
        self.katman.bildirim = yazi
        self.katman.bildirim_bitis = time.monotonic() + sure
        self.katman.update()
        QTimer.singleShot(int(sure * 1000) + 50, self.katman.update)

    # ---- menü ve tuşlar ----
    def menu(self):
        m = QMenu(self)
        c = QAction("Çeviri açık	F4", m, checkable=True, checked=self.ceviri_acik)
        c.triggered.connect(self.ceviri_degistir)
        m.addAction(c)
        m.setStyleSheet("QMenu{background:#222;color:#eee;} QMenu::item:selected{background:#3a6ea5;}")
        m.addAction("Altyazı bölgesini seç\tF2", lambda: self.bolge_sec("altyazi"))
        m.addAction("Görev metni bölgesini seç\tF3", lambda: self.bolge_sec("gorev"))
        if self.ayar["bolgeler"].get("gorev"):
            m.addAction("Görev metni bölgesini kapat", self.gorev_kapat)
        m.addSeparator()

        motor = m.addMenu("Çeviri motoru")
        grup = QActionGroup(motor)
        for kod, ad in (("karma", "Hızlı + kaliteli (önce Google, sonra yerel yapay zekâ)"),
                        ("google", "Yalnız Google (en hızlı, argoda zayıf)"),
                        ("ollama", f"Yalnız yerel yapay zekâ ({self.ayar['ollama_model']})")):
            a = QAction(ad, motor, checkable=True, checked=self.ayar["motor"] == kod)
            a.triggered.connect(lambda _=False, k=kod: self.motor_sec(k))
            grup.addAction(a)
            motor.addAction(a)

        if self.oynatici is None:
            vm = m.addMenu("Görüntü aygıtı")
            for a in QMediaDevices.videoInputs():
                vm.addAction(a.description(),
                             lambda ad=a.description(): self.aygit_sec("video_aygiti", ad))
            sm = m.addMenu("Ses aygıtı")
            ses = QAction("Sesi programdan çal", sm, checkable=True, checked=self.ayar["ses_acik"])
            ses.triggered.connect(self.ses_degistir)
            sm.addAction(ses)
            sm.addSeparator()
            for a in QMediaDevices.audioInputs():
                sm.addAction(a.description(),
                             lambda ad=a.description(): self.aygit_sec("ses_aygiti", ad))

        m.addSeparator()
        f = QAction("Parlak yazı filtresi\tF6", m, checkable=True, checked=self.ayar["parlak_filtre"])
        f.triggered.connect(self.filtre_degistir)
        m.addAction(f)
        m.addAction("Yazıyı büyüt\t+", lambda: self.yazi_boyutu(1.1))
        m.addAction("Yazıyı küçült\t-", lambda: self.yazi_boyutu(1 / 1.1))
        m.addAction("Tam ekran\tF11", self.tam_ekran_degistir)
        m.addSeparator()
        m.addAction("Çıkış", self.close)
        return m

    def tus(self, e):
        t = e.key()
        if t == Qt.Key_Escape:
            if self.katman.secim_modu:
                self.katman.secim_modu = self.katman.surukle = None
                self.katman.update()
            elif self.isFullScreen():
                self.tam_ekran_degistir()
        elif t == Qt.Key_F2:
            self.bolge_sec("altyazi")
        elif t == Qt.Key_F3:
            self.bolge_sec("gorev")
        elif t == Qt.Key_F4:
            self.ceviri_degistir()
        elif t == Qt.Key_F6:
            self.filtre_degistir()
        elif t == Qt.Key_F11:
            self.tam_ekran_degistir()
        elif t in (Qt.Key_Plus, Qt.Key_Equal):
            self.yazi_boyutu(1.1)
        elif t == Qt.Key_Minus:
            self.yazi_boyutu(1 / 1.1)

    def keyPressEvent(self, e):
        self.tus(e)

    def ceviri_degistir(self):
        self.ceviri_acik = not self.ceviri_acik
        if not self.ceviri_acik:
            for ad in BOLGE_ADLARI:
                self.gui[ad]["sira"] += 1000000  # yoldaki çeviriler gösterilmesin
                self.gui[ad]["kaynak_var"] = False
                self.katman.metinler[ad] = ""
        self.bildir("Çeviri " + ("açık" if self.ceviri_acik else "kapalı (F4 ile aç)"))

    def bolge_sec(self, ad):
        self.katman.secim_modu = ad
        self.katman.surukle = None
        self.katman.setCursor(Qt.CrossCursor)
        self.katman.update()

    def gorev_kapat(self):
        self.ayar["bolgeler"]["gorev"] = None
        self.katman.metinler["gorev"] = ""
        ayar_kaydet(self.ayar)
        self.katman.update()

    def motor_sec(self, kod):
        self.ayar["motor"] = kod
        ayar_kaydet(self.ayar)
        if kod in ("ollama", "karma"):
            threading.Thread(target=self._ollama_hazirla, daemon=True).start()
        else:
            self.bildir("Çeviri motoru: yalnız Google")

    def aygit_sec(self, anahtar, ad):
        self.ayar[anahtar] = ad
        ayar_kaydet(self.ayar)
        self.kamera_ac() if anahtar == "video_aygiti" else self.ses_ac()

    def ses_degistir(self):
        self.ayar["ses_acik"] = not self.ayar["ses_acik"]
        ayar_kaydet(self.ayar)
        self.ses_ac()

    def filtre_degistir(self):
        self.ayar["parlak_filtre"] = not self.ayar["parlak_filtre"]
        ayar_kaydet(self.ayar)
        self.bildir("Parlak yazı filtresi: " + ("açık" if self.ayar["parlak_filtre"] else "kapalı"))

    def yazi_boyutu(self, carpan):
        self.ayar["yazi_boyutu"] = round(min(0.08, max(0.015, self.ayar["yazi_boyutu"] * carpan)), 4)
        ayar_kaydet(self.ayar)
        self.katman.update()

    def tam_ekran_degistir(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    # ---- katmanı pencereyle birlikte taşı ----
    def katman_yerlestir(self):
        if self.isMinimized() or not self.isVisible():
            self.katman.hide()
            return
        ust_sol = self.video.mapToGlobal(self.video.rect().topLeft())
        self.katman.setGeometry(ust_sol.x(), ust_sol.y(), self.video.width(), self.video.height())
        if not self.katman.isVisible():
            self.katman.show()

    def eventFilter(self, nesne, olay):
        if nesne is self and olay.type() in (
            QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.WindowStateChange
        ):
            QTimer.singleShot(0, self.katman_yerlestir)
        return super().eventFilter(nesne, olay)

    def closeEvent(self, e):
        self.cevirmen.kaydet()
        ayar_kaydet(self.ayar)
        if self.kamera:
            self.kamera.stop()
        super().closeEvent(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", help="capture card yerine bir video dosyasıyla dene")
    ap.add_argument("--tam-ekran", action="store_true")
    ap.add_argument("--deneme-sure", type=float, help=argparse.SUPPRESS)
    ap.add_argument("--deneme-goruntu", help=argparse.SUPPRESS)
    a = ap.parse_args()

    uyg = QApplication(sys.argv)
    p = Pencere(ayar_yukle(), a.video)
    p.showFullScreen() if a.tam_ekran else p.show()
    if a.deneme_sure:
        def bitir():
            if a.deneme_goruntu:
                g = p.frameGeometry()
                p.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(a.deneme_goruntu)
            p.close()
        QTimer.singleShot(int(a.deneme_sure * 1000), bitir)
    sys.exit(uyg.exec())


if __name__ == "__main__":
    main()
