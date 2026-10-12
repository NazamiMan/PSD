# Data Preparation

## 1. Siapkan citra

Unduh produk Sentinel-2 **L2A** dari Copernicus Browser, kemudian ekstrak ZIP secara lokal ke `data/sentinel2/`. Pertahankan struktur `.SAFE` dan subfolder `GRANULE/.../IMG_DATA`. Produk unduhan tidak perlu dikirim ke situs lain untuk ekstraksi.

Folder proyek saat ini berisi arsip bernama `S2A_MSIL1C_...` (Level-1C). Ekstraktor yang digunakan mengikuti pola penamaan dan alur Level-2A, sehingga jangan gunakan produk L1C tersebut untuk langkah di bawah. Pilih **Sentinel-2 MSI Level-2A** pada Copernicus Browser, unduh produk yang mencakup poligon, lalu ekstrak produknya.

Skrip mencari file berikut secara rekursif:

- `*_B02_10m.jp2`
- `*_B03_10m.jp2`
- `*_B04_10m.jp2`
- `*_B08_10m.jp2`
- `*_B11_20m.jp2`

Kumpulan band harus lengkap untuk produk/granula yang sama. Citra mesti mencakup poligon GeoJSON. Beberapa tile mungkin diperlukan untuk menutup seluruh label; jangan mengunduh semua tanggal atau hasil pencarian tanpa memastikan cakupan.

## 2. Ekstrak piksel dan hitung indeks

Jalankan dari root repository:

```powershell
python src\1-project\extract_sentinel_pixels.py `
  --geojson data\jawatimur.geojson `
  --band-dir data\sentinel2 `
  --out-dir data\csv\split_dataset `
  --test-size 0.2 `
  --random-state 42
```

Skrip menyelaraskan grid B11 20 m ke grid B02 10 m, mengubah geometri GeoJSON ke CRS raster, lalu mengambil fitur piksel di dalam poligon. Hasil berisi `ID_Poligon`, `kelas`, `status_split`, B02/B03/B04/B08/B11, NDVI, NDWI, dan NDBI.

Pembagian train/test dibuat per ID poligon, bukan per piksel. Dengan begitu, piksel dari satu poligon tidak tersebar di kedua split. Hasil disimpan sebagai `train_dataset.csv` dan `test_dataset.csv` di `data/csv/split_dataset/`.

## 3. Latih dan evaluasi

Setelah dua CSV berhasil dibuat:

```powershell
python src\1-project\uts\train_classifier.py
```

Skrip memvalidasi kolom dan pemisahan ID, melatih Random Forest, lalu menyimpan model, metrik per kelas, matriks konfusi, dan feature importance di `src/1-project/uts/artifacts/`.

## Pemeriksaan kualitas

- Pastikan semua kelas memiliki poligon train dan test.
- Periksa poligon tanpa piksel valid; penyebab umum adalah citra tidak menutupi lokasi, CRS/cakupan tidak cocok, atau piksel tidak valid.
- Tinjau awan dan kesesuaian tanggal citra.
- Gunakan hasil test sebagai evaluasi model, bukan sampel yang digunakan untuk pelatihan.
- Jangan menafsirkan poligon digitasi sebagai hasil prediksi raster.

Jika impor Rasterio gagal karena kebijakan Application Control Windows, minta administrator memeriksa kebijakan atau gunakan lingkungan komputasi yang memang diizinkan. Jangan menonaktifkan kontrol keamanan.
