# UTS: Klasifikasi Tutupan Lahan Jawa Timur

Folder ini menyiapkan alur tugas pengganti UTS: memahami tujuan bisnis, memeriksa label GeoJSON, mengekstrak fitur Sentinel-2, melatih model, dan memeriksa poligon di peta satelit.

## Isi folder

- `business_understanding.md` — tujuan, pengguna, dan ruang lingkup.
- `data_understanding.md` — sumber label, distribusi kelas, dan fitur Sentinel-2.
- `data_preparation.md` — cara menyiapkan citra dan menjalankan ekstraksi.
- `app.py` — peta Streamlit/Folium dengan basemap satelit dan filter kelas poligon.
- `train_classifier.py` — melatih dan mengevaluasi Random Forest dari CSV hasil ekstraksi.

## Data yang digunakan

- Label: `data/jawatimur.geojson` (348 poligon, 5 kelas).
- Citra: ekstrak produk Sentinel-2 L2A ke `data/sentinel2/`; diperlukan JP2 B02, B03, B04, B08, dan B11.
- CSV: `data/csv/split_dataset/train_dataset.csv` dan `test_dataset.csv`.

GeoJSON diambil dari folder `data/` repository agar tidak ada salinan label yang bisa berbeda dari sumber aslinya. Jangan mengubah file sumber untuk menjalankan aplikasi.

> Produk yang saat ini ada di `data/sentinel2/` bernama `S2A_MSIL1C_...`. Ekstraktor proyek ini disiapkan untuk JP2 Sentinel-2 **L2A** dengan nama seperti `*_B02_10m.jp2`. Unduh produk L2A sebelum menjalankan ekstraksi; ZIP L1C yang ada belum sesuai pola/nilai input ekstraktor ini.

## Menjalankan peta

Pastikan interpreter Python yang dipakai memiliki dependensi aplikasi (`streamlit` dan `folium`). Jalankan dari root repository:

```powershell
python -m streamlit run src\1-project\uts\app.py
```

Gunakan checkbox di sidebar untuk memilih kelas yang tampil; Layer Control pada peta juga dapat menyalakan atau menyembunyikan tiap kelas. Basemap satelit dan aset Leaflet memerlukan koneksi internet. Jalankan dengan `streamlit run`, bukan `python app.py`.

## Ekstraksi dan pelatihan

Setelah seluruh produk Sentinel-2 L2A yang mencakup poligon diekstrak, jalankan:

```powershell
python src\1-project\extract_sentinel_pixels.py `
  --geojson data\jawatimur.geojson `
  --band-dir data\sentinel2 `
  --out-dir data\csv\split_dataset `
  --test-size 0.2
```

Kemudian latih dan evaluasi model:

```powershell
python src\1-project\uts\train_classifier.py
```

Model, laporan metrik, matriks konfusi, dan feature importance ditulis ke `src/1-project/uts/artifacts/`. Aplikasi peta menampilkan poligon berlabel hasil digitasi; hasil klasifikasi raster baru dapat ditampilkan setelah proses prediksi raster ditambahkan dan citranya dapat dibaca oleh Rasterio.

Jalankan notebook [`klasifikasiLulcJatim.ipynb`](./klasifikasiLulcJatim.ipynb) untuk urutan audit label, ekstraksi, pelatihan, dan ringkasan evaluasi yang sama.

## Catatan lingkungan Windows

Ekstraksi JP2 membutuhkan Rasterio/GDAL. Jika Windows menampilkan pesan bahwa Application Control memblokir DLL Rasterio, jalankan ekstraksi di lingkungan Python yang diizinkan atau minta administrator memeriksa kebijakan tersebut. Aplikasi peta GeoJSON tidak membaca JP2, sehingga dapat diuji terpisah dari ekstraksi.
