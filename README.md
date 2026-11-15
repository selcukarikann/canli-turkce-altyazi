# Canlı Türkçe Altyazı

Türkçe altyazısı olmayan konsol oyunlarını Türkçe altyazıyla oynamak için bir Windows programı.

Oyunu capture card üzerinden bilgisayar ekranında gösterir, ekrandaki İngilizce altyazıyı okur ve Türkçesini aynı yerin üstüne yazar. Oyunun kendisine dokunmaz; yalnızca ekrandaki görüntüyü okur. PS5, Xbox, Switch ya da HDMI çıkışı olan herhangi bir cihazla çalışır.

## Nasıl çalışır

1. Konsolun görüntüsü capture card ile bilgisayara gelir, program bunu tam ekran gösterir ve sesini çalar.
2. Program, senin işaretlediğin altyazı bölgesini saniyede 10 kez okur (Windows'un yerleşik yazı tanıma motoruyla).
3. Yeni bir satır görünce çevirir ve Türkçesini İngilizce yazının üstüne koyu bir kutu içinde yazar.

Çeviri, satır ekrana geldikten yaklaşık 0,1–1 saniye sonra görünür (seçtiğin çeviri motoruna göre).

## Gerekenler

| Gereken | Açıklama |
|---|---|
| Windows 10 ya da 11 (64 bit) | |
| Capture card | HDMI görüntüsünü USB'den bilgisayara aktaran aygıt. 1080p 60 fps destekleyen herhangi bir UVC kart olur. |
| İngilizce yazı tanıma paketi | Windows'un ücretsiz bir dil bileşeni. Aşağıda nasıl kurulacağı yazıyor. |
| İnternet | Google Çeviri için. Yalnız yerel yapay zekâ modunda gerekmez. |
| *İsteğe bağlı:* Ollama | Argoyu ve küfrü daha iyi çeviren yerel yapay zekâ için. Güçlü bir ekran kartı ister. |

Python ya da başka bir program kurmana **gerek yok**; hepsi kurulum dosyasının içinde.

## Kurulum

1. [Releases](../../releases) sayfasından `CanliTurkceAltyazi-Kurulum-1.0.0.exe` dosyasını indir ve çalıştır.
2. Windows "Windows kişisel bilgisayarınızı korudu" uyarısı gösterirse **Ek bilgi > Yine de çalıştır**'a tıkla. Uyarı, programın ücretli bir kod imzasıyla imzalanmamış olmasından kaynaklanır.
3. Kurulum yönetici izni istemez.

Kurmak istemeyenler aynı sayfadaki `tasinabilir.zip` dosyasını indirip bir klasöre açabilir ve `CanliTurkceAltyazi.exe` dosyasını çalıştırabilir.

### İngilizce yazı tanıma paketini kurma

Program İngilizce yazıyı okumak için Windows'un kendi bileşenini kullanır. Türkçe Windows'larda bu çoğunlukla kurulu değildir:

1. **Ayarlar > Saat ve Dil > Dil ve Bölge** bölümünü aç.
2. **Dil ekle**'ye tıkla, **English (United States)** seç.
3. Kurulum bitince programı yeniden aç.

Windows'un dilini değiştirmene gerek yok; paketin kurulu olması yeterli. Paket yoksa program açılışta uyarır.

## İlk kullanım

1. Konsolu capture card'ın girişine, capture card'ı bilgisayara bağla.
2. **PS5 kullanıyorsan HDCP'yi kapat:** Ayarlar > Sistem > HDMI > HDCP'yi Etkinleştir. Açıkken görüntü gelmez.
3. Programı aç. İlk açılışta görüntü ve ses aygıtını sorar; capture card'ını seç.
4. Oyunun ayarlarından İngilizce altyazıyı aç. Varsa altyazı arka planını da aç, okuma belirgin biçimde iyileşir.
5. Oyunda bir altyazı çıkınca **F2**'ye bas ve altyazının çıktığı alanı fareyle çiz. Bu bir kez yapılır ve kaydedilir.
6. Görev metinleri de çevrilsin istersen aynısını **F3** ile yap.

**Bölgeleri dar tut.** Yalnızca yazının çıktığı alanı çiz; mini haritayı ve manzarayı içine alma. Geniş bölgede program manzaradaki şekilleri yazı sanıp anlamsız çeviriler üretebilir.

## Tuşlar

| Tuş | İşlev |
|---|---|
| F2 | Altyazı bölgesini seç |
| F3 | Görev metni bölgesini seç |
| F4 | Çeviriyi aç / kapat |
| F6 | Parlak yazı filtresi |
| F11 ya da çift tık | Tam ekran |
| + / - | Yazıyı büyüt / küçült |
| Esc | Seçimden ya da tam ekrandan çık |
| Sağ tık | Menü: çeviri motoru, görüntü ve ses aygıtı, diğer ayarlar |

## Çeviri motorları

Sağ tık > **Çeviri motoru** menüsünden seçilir.

| Motor | Hız | Kalite | Gereken |
|---|---|---|---|
| Yalnız Google | En hızlı (yaklaşık 0,1 sn) | Düz cümlelerde iyi, argoda zayıf | İnternet |
| Yalnız yerel yapay zekâ | Yaklaşık 1 sn | Argoyu ve bozuk okunan kelimeleri daha iyi çevirir | Ollama |
| Hızlı + kaliteli | Önce Google'ınki, sonra yerelinki | İkisinin birleşimi | İnternet ve Ollama |

Yeni kurulumda **Yalnız Google** seçili gelir ve ek bir şey kurmadan çalışır.

### Yerel yapay zekâyı kurma (isteğe bağlı)

1. [ollama.com](https://ollama.com) adresinden Ollama'yı kur.
2. Bir komut penceresinde modeli indir (yaklaşık 8 GB):

   ```
   ollama pull gemma3:12b
   ```

3. Programda sağ tık > Çeviri motoru'ndan yerel yapay zekâlı seçeneklerden birini seç.

Model yaklaşık 8 GB ekran kartı belleği kullanır. Oyun konsolda çalıştığı için bilgisayarın ekran kartı bu işe ayrılabilir.

## Canlı yayın (OBS)

- Capture card'ı OBS'e **ekleme**. Kartı aynı anda tek program açabilir.
- OBS'te **Ekran Yakalama** kaynağı ekle ve programın tam ekran açık olduğu monitörü seç. Pencere Yakalama, Türkçe yazı katmanını almaz.
- Program oyunun sesini hoparlöre verdiği için OBS'in Masaüstü Sesi onu zaten yakalar.

## Sık sorunlar

| Sorun | Çözüm |
|---|---|
| Görüntü yok, siyah ekran | Konsolda HDCP açıktır ya da kartı başka bir program (OBS gibi) kullanıyordur. |
| Görüntü çizgili, bozuk | Kartın USB kablosunu çıkar, 10 saniye sonra mavi (USB 3.0) bir girişe doğrudan tak. HDMI kablolarını kontrol et. |
| Görüntü bulanık | Konsol çıkışını 1080p ve HDR kapalı yap. Çoğu kart en fazla 1080p yakalar ve 4K/HDR sinyali kendi içinde kötü küçültür. |
| Ses çift geliyor | Sağ tık > Ses aygıtı > "Sesi programdan çal" işaretini kaldır. |
| Anlamsız çeviriler çıkıyor | Bölge çok geniştir. F2 / F3 ile yalnızca yazının çıktığı alanı çiz. |
| "Google geçici olarak kısıtladı" | Çok sık istek gitmiştir. Program 10 dakika Google'a istek atmaz; Ollama kuruluysa onunla devam eder. Bölgeleri daraltmak istek sayısını azaltır. |
| Yazı tanıma uyarısı çıkıyor | İngilizce yazı tanıma paketi kurulu değil; yukarıdaki adımları izle. |

## Bilinen sınırlar

- Çeviri gerçek zamanlı ama anlık değil; hızlı diyaloglarda biraz geriden gelebilir.
- Yazı tanıma, hareketli ve parlak sahnelerin üstündeki arka plansız altyazılarda hata yapabilir.
- Capture card üzerinden oynarken görüntüde kartına bağlı olarak 50–100 ms gecikme olur.
- Makine çevirisi profesyonel yerelleştirmenin yerini tutmaz; espriler ve kelime oyunları kaybolabilir.
- Google çevirisi, Google Çeviri'nin belgelenmemiş ücretsiz adresini kullanır. Resmî bir hizmet değildir; kısıtlanabilir ya da ileride çalışmayabilir.

## Gizlilik

- Program yalnızca işaretlediğin bölgelerdeki yazıyı okur.
- Google motorunda, okunan altyazı metni çevrilmek üzere Google'a gönderilir. Başka hiçbir veri gönderilmez.
- Yalnız yerel yapay zekâ modunda hiçbir şey bilgisayarından dışarı çıkmaz.
- Ayarlar ve daha önce çevrilmiş satırlar `%APPDATA%\CanliTurkceAltyazi` klasöründe tutulur. Programı kaldırmak bu klasörü silmez.

## Kaynak koddan çalıştırma

Python gerekir (3.14 ile denendi).

```
py -m pip install -r requirements.txt
py canli_ceviri.py
```

Bir video dosyasıyla denemek için (capture card gerekmez):

```
py canli_ceviri.py --video ornek.mp4
```

### Kurulum dosyasını üretme

1. `py -m pip install pyinstaller`
2. `paketle.bat` dosyasını çalıştır. Paket `dist\CanliTurkceAltyazi` klasöründe oluşur.
3. [Inno Setup 6](https://jrsoftware.org/isinfo.php) kuruluysa `ISCC.exe kurulum.iss` komutu `dist` klasöründe kurulum dosyasını üretir.

### Dosyalar

| Dosya | İçerik |
|---|---|
| `canli_ceviri.py` | Ana program: pencere, görüntü ve ses, Türkçe yazı katmanı, menü |
| `okuyucu.py` | Yazı tanıma ve gürültü süzgeci |
| `cevirmen.py` | Çeviri motorları (Google, Ollama) ve çeviri hafızası |
| `paketle.bat` | Uygulamayı PyInstaller ile paketler |
| `kurulum.iss` | Inno Setup kurulum betiği |
| `BENIOKU.txt` | Kurulumla birlikte gelen kısa kullanım bilgisi |

## Lisans ve notlar

Bu proje MIT lisansıyla yayınlanır; ayrıntı için `LICENSE` dosyasına bak.

Kurulum paketi Qt (PySide6, LGPL lisanslı) ve FFmpeg kitaplıklarını içerir.

Bu program herhangi bir oyun, konsol ya da çeviri hizmeti sağlayıcısıyla bağlantılı değildir. Adı geçen ürün adları sahiplerine aittir.
