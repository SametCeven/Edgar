# Edgar


## Gereksinimler

- **Python 3.10 veya ustu** - [python.org/downloads](https://www.python.org/downloads/) adresinden indir.
  - Windows kurulumunda ilk ekrandaki **"Add Python to PATH"** kutusunu mutlaka isaretle.
  - Kontrol: PowerShell ac, sunu yaz:
    ```powershell
    python --version
    ```
    `Python 3.10.x` veya ustu gormelisin.
- **Git** - [git-scm.com/downloads](https://git-scm.com/downloads) adresinden indir (projeyi indirmek/klonlamak icin).

`git clone` komutu, **o an bulundugun klasorun icinde** `Edgar` adinda yeni bir klasor olusturur. Bu yuzden once projeyi koymak istedigin klasore gir, sonra klonla ve icine gir. Sonraki tum komutlar bu `Edgar` klasoru icinde calistirilir:

```powershell
cd C:\Users\Adin\Desktop      # bu klasore girersen proje Masaustune (Desktop) klonlanir; Adin = Windows kullanici adin
git clone https://github.com/SametCeven/Edgar.git
cd Edgar
```

---

## Kurulum (tek seferlik)

### 1. Sanal ortam (`.venv`) olustur

Sanal ortam, projenin paketlerini bilgisayarinin geri kalanindan ayri tutar.

```powershell
python -m venv .venv
```

Bu komut `Edgar` klasoru icinde `.venv` adinda bir klasor olusturur.

### 2. Sanal ortami aktif et

```powershell
.\.venv\Scripts\Activate.ps1
```

Basarili olursa satirin basinda `(.venv)` yazisini gorursun. **Her yeni PowerShell penceresi actiginda bu komutu tekrar calistirman gerekir.**

> "running scripts is disabled" hatasi alirsan, bir kerelik sunu calistir, sonra tekrar aktif et:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

### 3. Paketleri yukle

```powershell
pip install -r requirements.txt
pip install -e .
```

Ilk komut tum bagimliliklari (pandas, scikit-learn vb.) kurar. Ikinci komut projenin kendi kodunu (`edgar` paketi) `import` edilebilir hale getirir. Birkac dakika surebilir.

### 4. `.env` dosyasini olustur

Proje, SEC EDGAR'a kim oldugunu soylemek icin bir e-posta adresi ister. Bu dosya repoda **gelmez** (gizli tutulur), elle olusturman gerekir. Hazir ornekten kopyala:

```powershell
Copy-Item .env.example .env
```

Sonra `.env` dosyasini bir metin duzenleyici (or. Not Defteri, VS Code) ile ac ve `EDGAR_USER_AGENT` satirina kendi e-postani yaz:

```
LOG_LEVEL=DEBUG
EDGAR_USER_AGENT=adin@ornek.com
```

> `EDGAR_USER_AGENT` zorunludur; bos birakirsan program acilista hata verir. SEC, isteklerde gecerli bir e-posta gormek ister.

### 5. Russell 1000 Excel dosyasini yerine koy

Proje, sirket listesini bir Excel dosyasindan okur. Bu dosya repoda **gelmez** (boyutu yuzunden takip edilmiyor), bu yuzden elle koyman gerekir.

Dosyanin tam olarak su konumda ve su isimde olmasi gerekir:

```
data\russel_1000\russel_1000.xlsx
```

Yani `data` klasoru icinde `russel_1000` adinda bir klasor olustur ve indirdigin `russel_1000.xlsx` dosyasini oraya kopyala (Windows Gezgini ile normal kopyala-yapistir; PowerShell gerekmez).

> Notlar:
> - Klasor/dosya adinda **tek `l`** vardir: `russel_1000.xlsx`. Isim veya konum birebir eslesmezse `preprocess` adimi dosyayi bulamaz.
> - `.xls` degil, **`.xlsx`** kullan.

---

## Calistirma

Asagidaki komutlardan once sanal ortamin aktif oldugundan (`(.venv)` gorundugunden) emin ol.

### Tum pipeline'i bastan sona calistir

```powershell
python run.py pipeline
```

Adimlari sirayla calistirir: **preprocess -> fetch -> load -> transform -> train**. Ilk `fetch` calistirmasi EDGAR'dan ~2.000 istek yapar ve uzun surer (verileri diske onbellege alir; sonraki calistirmalar hizlidir).

### Sadece belirli adimlari calistir

Istedigin adimlari bayrak olarak ver. Sira her zaman sabittir (yazdigin siraya bakilmaz):

```powershell
python run.py pipeline --fetch              # sadece fetch
python run.py pipeline --fetch --load       # fetch + load
python run.py pipeline --transform --train  # transform + train
```

Adimlar:

| Adim | Ne yapar |
|---|---|
| `preprocess` | Russell 1000 Excel'ini okur, sirket listesini hazirlar |
| `fetch` | EDGAR API'den ham veriyi ceker, diske onbellege alir |
| `load` | Onbellekteki JSON'lari CSV'ye duzlestirir (`data/warehouse/raw/`) |
| `transform` | Veriyi temizler ve katmanlar (`dim -> int -> mart`) |
| `train` | 4 ML modelini egitir, sonuclari yazar (`data/warehouse/ml/`) |

---

## Ciktilar nerede?

- `data/warehouse/` - tum islenmis veriler (CSV), katman katman: `raw -> dim -> int -> mart -> ml`
- `logs/` - her calistirma icin bir log dosyasi (`run_<tarih>.log`)
- Power BI dosyasi bu CSV'leri (`mart` + `ml`) kaynak olarak okur.

---

## Sik karsilasilan sorunlar

- **`Missing required env var: EDGAR_USER_AGENT`** -> `.env` dosyasini olusturmadin ya da e-postayi yazmadin (Adim 4).
- **`(.venv)` gorunmuyor** -> sanal ortami aktif etmedin: `.\.venv\Scripts\Activate.ps1`.
- **`python` komutu taninmiyor** -> Python PATH'e ekli degil; "Add to PATH" isaretli olarak yeniden kur.
- **Russell dosyasi bulunamadi** -> dosya adi/konumu `data\russel_1000\russel_1000.xlsx` ile birebir ayni degil (Adim 5).

---

## Proje yapisi ve mimari

Klasor yapisi, pipeline detaylari ve veri akisi icin: [docs/architecture.md](docs/architecture.md).
