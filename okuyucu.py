"""Altyazı okuma: Windows'un yerleşik OCR motorunu kullanır (ücretsiz, hızlı).

OCR, yazı olmayan yerlerde (manzara, mini harita, simgeler) de "kelime"
uydurur. Bu yüzden okunan her parça ayrı ayrı süzülür; yalnızca gerçek
İngilizce yazıya benzeyenler kabul edilir.
"""
import re

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

# Altyazılarda en sık geçen İngilizce kelimeler. Gerçek bir cümlede bunlardan
# en az biri hemen her zaman bulunur; manzaradan uydurulan "kelimelerde" bulunmaz.
ORTAK = frozenset("""
a about after again all alright always am an and any are around as ask at away back bad be
because been before being best better big boss both boy bring but buy by call came can car
come coming cop cops could day dead did do does doing done door down drive drop each end even
ever every eyes face fast feel few find fine first follow for found friend from get gets
getting girl give go god goes going gone good got gotta guess gun guy guys had hand hands
has have he head hear heard hell hello help her here hey him his hit hold home how hurry i if
in into is it its job just keep kid kill kind know last later leave left let life like listen
little long look lot love made make man many may maybe me mean meet men might mind mine money
more most move much must my name need never new next nice night no not nothing now of off oh
ok okay old on once one only open or other our out over own pay people pick place play please
police press pull put ready real really right road run said same saw say see seen she shit
shoot should show shut side sir sit so some someone something soon sorry stay still stop sure
take talk tell than thank thanks that the their them then there these they thing things think
this those though thought three through time to today together told tonight too took town try
turn two under until up us use very wait walk want was watch way we well went were what when
where which while who why will with without woman word work would wrong yeah year yes yet you
your bank mission main objective reach find defeat enemies hold near
""".split())

_HARF_DISI = re.compile(r"[^A-Za-z']")
_UC_TEKRAR = re.compile(r"(.)\1\1")


class Okuyucu:
    def __init__(self, dil="en-US"):
        self.motor = OcrEngine.try_create_from_language(Language(dil))
        self.ingilizce = self.motor is not None  # değilse okuma kalitesi düşer
        if self.motor is None:
            self.motor = OcrEngine.try_create_from_user_profile_languages()
        if self.motor is None:
            raise RuntimeError("Windows OCR motoru açılamadı (İngilizce dil paketi gerekli).")

    def oku(self, gri):
        """gri: HxW uint8 görüntü. (metin, yazının kapladığı alan) döndürür.

        Yalnızca gerçek yazıya benzeyen parçalar metne ve alana katılır.
        Alan [sol, üst, genişlik, yükseklik] biçiminde, görüntünün oranı olarak verilir.
        """
        y, g = gri.shape
        yazar = DataWriter()
        yazar.write_bytes(gri.tobytes())
        bmp = SoftwareBitmap.create_copy_from_buffer(
            yazar.detach_buffer(), BitmapPixelFormat.GRAY8, g, y
        )
        sonuc = self.motor.recognize_async(bmp).get()

        kabul = []
        for satir in sonuc.lines:
            for parca in _parcalara_bol(list(satir.words)):
                if parca_gecerli([k.text for k in parca]):
                    kabul.extend(parca)
        if not kabul:
            return "", None
        metin = " ".join(k.text for k in kabul)
        kutular = [k.bounding_rect for k in kabul]
        x0 = min(k.x for k in kutular)
        y0 = min(k.y for k in kutular)
        x1 = max(k.x + k.width for k in kutular)
        y1 = max(k.y + k.height for k in kutular)
        return metin, [x0 / g, y0 / y, (x1 - x0) / g, (y1 - y0) / y]


def _parcalara_bol(kelimeler):
    """Aynı satırda birbirinden çok uzak duran kelimeleri ayrı parçalara böler.

    Böylece altyazının yanına düşen harita/simge gürültüsü altyazıya yapışmaz.
    """
    parcalar, grup, onceki = [], [], None
    for k in kelimeler:
        r = k.bounding_rect
        if onceki is not None and r.x - (onceki.x + onceki.width) > 2.5 * max(r.height, onceki.height):
            parcalar.append(grup)
            grup = []
        grup.append(k)
        onceki = r
    if grup:
        parcalar.append(grup)
    return parcalar


def kelime_makul(k):
    """Bir kelime gerçek İngilizce kelimeye benziyor mu?"""
    if not k.isascii():
        return False
    harfler = _HARF_DISI.sub("", k).lower().replace("'", "")
    if not harfler:
        return any(c.isdigit() for c in k)  # sayılar zararsız
    if harfler in ORTAK:
        return True
    n = len(harfler)
    if n == 1:
        return False
    if _UC_TEKRAR.search(harfler):
        return False
    if n >= 3:
        if max(harfler.count(c) for c in set(harfler)) / n >= 0.6:
            return False
        sesli = sum(c in "aeiouy" for c in harfler) / n
        if sesli == 0 or sesli > 0.65:
            return False
    return True


def ortak_sayisi(metin):
    return sum(1 for k in metin.split() if _HARF_DISI.sub("", k).lower().replace("'", "") in ORTAK)


def parca_gecerli(kelimeler):
    """Bir kelime öbeği gerçek yazı mı, yoksa manzaradan uydurulmuş gürültü mü?"""
    harfli = [k for k in kelimeler if any(c.isalpha() for c in k)]
    if not harfli or sum(len(_HARF_DISI.sub("", k)) for k in harfli) < 4:
        return False
    makul = [k for k in harfli if kelime_makul(k)]
    if len(makul) / len(harfli) < 0.7:
        return False
    if ortak_sayisi(" ".join(harfli)) >= 1:
        return True
    # ortak kelime yok: yalnızca uzunca, tamamı düzgün kelimelerden oluşan başlıklar
    if len(makul) < len(harfli) or len(harfli) < 2:
        return False
    return sum(len(_HARF_DISI.sub("", k)) for k in harfli) / len(harfli) >= 4.5


def hazirla(rgb, parlak_filtre=False):
    """Altyazı bölgesini OCR için hazırlar.

    parlak_filtre açıkken yalnızca parlak (beyaz/açık renkli) pikseller yazı
    sayılır; arkadaki sahne büyük ölçüde temizlenir.
    """
    if parlak_filtre:
        en_parlak = rgb.max(axis=2)
        gri = np.where(en_parlak > 185, 0, 255).astype(np.uint8)
    else:
        # tam sayı aritmetiğiyle gri ton (0.299 R + 0.587 G + 0.114 B)
        r, g_, b = (rgb[..., i].astype(np.uint16) for i in range(3))
        gri = ((r * 77 + g_ * 150 + b * 29) >> 8).astype(np.uint8)
    y, g = gri.shape
    if y < 500:
        k = 2 if y >= 120 else 3
        gri = _buyut(np.ascontiguousarray(gri), g * k, y * k)
    return np.ascontiguousarray(gri)


def _buyut(gri, yeni_g, yeni_y):
    """Küçük yazılar daha iyi okunsun diye görüntüyü yumuşak biçimde büyütür."""
    y, g = gri.shape
    img = QImage(gri.data, g, y, g, QImage.Format.Format_Grayscale8).scaled(
        yeni_g, yeni_y, Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation)
    ham = np.frombuffer(img.constBits(), np.uint8).reshape(yeni_y, img.bytesPerLine())
    return ham[:, :yeni_g].copy()


def temizle(metin):
    return re.sub(r"\s+", " ", metin).strip(" |_~-—.·•")


def gecerli_mi(metin):
    """Süzgeçten geçen metin çevrilmeye değer mi?"""
    return len(metin) >= 3 and sum(c.isalpha() for c in metin) >= 3
