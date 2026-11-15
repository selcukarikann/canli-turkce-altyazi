"""Çeviri motorları: Google (ücretsiz) ve Ollama (bilgisayarda çalışan yapay zekâ).

Üç çalışma biçimi vardır (ayar["motor"]):
  "google" : yalnızca Google — en hızlısı, argoda zayıf
  "ollama" : yalnızca yerel yapay zekâ — yazı kelime kelime akar
  "karma"  : önce Google'ın çevirisi hemen gösterilir, yerel yapay zekânınki
             hazır olunca onun yerine geçer
"""
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

OLLAMA = "http://127.0.0.1:11434"

SISTEM = (
    "You translate video game subtitles (an open-world crime game) from English "
    "to natural, colloquial Turkish, the way a professional game localizer would. "
    "Rules:\n"
    "- Stay faithful: do not add, drop or change the meaning.\n"
    "- Keep the tone, slang and profanity; use Turkish street slang where the "
    "English uses slang.\n"
    "- The speaker talks to one person informally: use 'sen', never 'siz', and "
    "keep second person as second person.\n"
    "- 'Yo', 'Hey', 'Man', 'Dude', 'Bro' are greetings or fillers (Hey, Lan, "
    "Abi, Kanka), never 'no'.\n"
    "- Keep character and place names unchanged.\n"
    "- The text comes from OCR. If a word is broken or has missing letters "
    "(for example 'ga age' is 'garage'), work out the intended English word "
    "from context first, then translate.\n"
    "Reply with the Turkish translation only, nothing else."
)


class Cevirmen:
    def __init__(self, ayar, onbellek_yolu):
        self.ayar = ayar
        self.yol = onbellek_yolu
        self.kilit = threading.Lock()
        self.onbellek = {}
        self.kaydedilmemis = 0
        self.uyari = ""  # arayüzde gösterilecek son sorun
        self._ollama_denendi = False
        self.google_engel_bitis = 0.0  # Google kısıtlarsa bu ana kadar istek atılmaz
        # bağlantılar açık tutulur; her motorun kendi oturumu var
        self.google_http = requests.Session()
        self.ollama_http = requests.Session()
        self.ollama_http.trust_env = False
        self.yan = ThreadPoolExecutor(max_workers=2)  # karma modda Google için
        try:
            with open(self.yol, encoding="utf-8") as f:
                self.onbellek = json.load(f)
        except (OSError, ValueError):
            pass

    # ---- dışa açık ----
    def cevir(self, metin, bildir):
        """metin'i çevirir ve sonucu bildir(turkce, kesin) ile iletir.

        bildir birden çok kez çağrılabilir: önce geçici sonuçlar (kesin=False),
        en sonda kesin sonuç (kesin=True).
        """
        motor = self.ayar["motor"]
        kucuk = metin.lower()
        if motor in ("ollama", "karma"):
            hazir = self._bak("ollama|" + kucuk)
            if hazir:
                bildir(hazir, True)
                return
            sira = threading.Lock()
            bitti = threading.Event()
            google_geldi = threading.Event()
            if motor == "karma":
                def hizli():
                    try:
                        g = self._google_onbellekli(metin)
                    except Exception:  # noqa: BLE001
                        return
                    with sira:
                        if g and not bitti.is_set():
                            google_geldi.set()
                            bildir(g, False)
                self.yan.submit(hizli)

            def akis(kismi):
                # Google'ın tam cümlesi ekrandaysa yarım cümleyle değiştirme
                if not google_geldi.is_set():
                    bildir(kismi, False)
            try:
                sonuc = self._ollama(metin, akis)
                with sira:
                    bitti.set()
                    bildir(sonuc, True)
                self.uyari = ""
                self._sakla("ollama|" + kucuk, sonuc)
                return
            except Exception as h:  # noqa: BLE001
                bitti.set()
                self.uyari = f"Yerel yapay zekâ çalışmadı ({_kisa(h)}), Google kullanılıyor"
        try:
            bildir(self._google_onbellekli(metin), True)
            if motor == "google":
                self.uyari = ""
        except Exception as h:  # noqa: BLE001
            if motor == "google":  # Google yoksa yerel yapay zekâyı dene
                try:
                    sonuc = self._ollama(metin, lambda kismi: bildir(kismi, False))
                    bildir(sonuc, True)
                    self._sakla("ollama|" + kucuk, sonuc)
                    self.uyari = f"Google çalışmadı ({_kisa(h)}), yerel yapay zekâ kullanılıyor"
                    return
                except Exception:  # noqa: BLE001
                    pass
            self.uyari = f"Çeviri yapılamadı ({_kisa(h)})"

    def kaydet(self):
        with self.kilit:
            veri = dict(self.onbellek)
            self.kaydedilmemis = 0
        try:
            with open(self.yol + ".tmp", "w", encoding="utf-8") as f:
                json.dump(veri, f, ensure_ascii=False)
            os.replace(self.yol + ".tmp", self.yol)
        except OSError:
            pass

    def ollama_hazirla(self):
        """Ollama kapalıysa arka planda başlatır ve modeli belleğe yükler."""
        try:
            self.ollama_http.get(OLLAMA, timeout=1)
        except requests.RequestException:
            if not self._ollama_denendi:
                self._ollama_denendi = True
                try:
                    subprocess.Popen(
                        ["ollama", "serve"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    time.sleep(3)
                except OSError:
                    return
        try:
            self._ollama("Hello.", None, bekleme=120)
            self.uyari = ""
        except Exception as h:  # noqa: BLE001
            self.uyari = f"Yerel yapay zekâ çalışmadı ({_kisa(h)}), Google kullanılıyor"

    # ---- önbellek ----
    def _bak(self, anahtar):
        with self.kilit:
            return self.onbellek.get(anahtar)

    def _sakla(self, anahtar, deger):
        with self.kilit:
            self.onbellek[anahtar] = deger
            self.kaydedilmemis += 1
            kaydet = self.kaydedilmemis >= 20
        if kaydet:
            self.kaydet()

    # ---- motorlar ----
    def _google_onbellekli(self, metin):
        anahtar = "google|" + metin.lower()
        hazir = self._bak(anahtar)
        if hazir:
            return hazir
        if time.monotonic() < self.google_engel_bitis:
            raise RuntimeError("Google geçici olarak kısıtladı")
        r = self.google_http.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "tr", "dt": "t", "q": metin},
            timeout=4,
        )
        if r.status_code == 429:  # çok fazla istek: 10 dakika ara ver
            self.google_engel_bitis = time.monotonic() + 600
            raise RuntimeError("Google geçici olarak kısıtladı")
        r.raise_for_status()
        sonuc = "".join(p[0] for p in r.json()[0] if p and p[0]).strip()
        if sonuc:
            self._sakla(anahtar, sonuc)
        return sonuc

    def _ollama(self, metin, akis, bekleme=20):
        """akis verilirse yazı üretildikçe akis(o_ana_kadarki_metin) çağrılır."""
        with self.ollama_http.post(
            OLLAMA + "/api/chat",
            stream=True,
            timeout=bekleme,
            json={
                "model": self.ayar["ollama_model"],
                "stream": True,
                "keep_alive": "30m",
                "options": {"temperature": 0.2, "num_predict": 160},
                "messages": [
                    {"role": "system", "content": SISTEM},
                    {"role": "user", "content": metin},
                ],
            },
        ) as r:
            if r.status_code == 404:
                raise RuntimeError(f"'{self.ayar['ollama_model']}' modeli indirilmemiş")
            r.raise_for_status()
            toplam = ""
            for satir in r.iter_lines():
                if not satir:
                    continue
                p = json.loads(satir)
                if p.get("error"):
                    raise RuntimeError(p["error"])
                toplam += p.get("message", {}).get("content", "")
                if akis and toplam.strip():
                    akis(toplam.strip().strip('"'))
                if p.get("done"):
                    break
        sonuc = toplam.strip().strip('"')
        if not sonuc:
            raise RuntimeError("boş yanıt")
        return sonuc


def _kisa(hata):
    if isinstance(hata, requests.ConnectionError):
        return "bağlantı yok"
    if isinstance(hata, requests.Timeout):
        return "zaman aşımı"
    return str(hata)[:60]
