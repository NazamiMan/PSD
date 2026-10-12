# Data Understanding

## GeoJSON label

Sumber label aktif adalah `data/jawatimur.geojson` pada root repository. File merupakan GeoJSON berisi poligon dan atribut kelas one-hot. Pemeriksaan data saat penyiapan folder ini mendapatkan 348 fitur dengan distribusi:

| Kelas | Poligon |
|---|---:|
| Built-up | 70 |
| Farm land | 70 |
| Water body | 70 |
| Forest | 68 |
| Mangrove | 70 |
| **Total** | **348** |

Peta pada `app.py` memakai geometri dan kelas dari file tersebut. Pastikan posisi dan label poligon sudah benar sebelum ekstraksi; kualitas model bergantung pada kualitas label.

## Citra Sentinel-2

Gunakan produk **Sentinel-2 Level-2A** dan band berikut:

| Band | Spektrum | Resolusi | Kegunaan utama |
|---|---|---:|---|
| B02 | Biru | 10 m | Komposit warna dan fitur perairan |
| B03 | Hijau | 10 m | Komponen NDWI |
| B04 | Merah | 10 m | Komponen NDVI |
| B08 | NIR | 10 m | Kondisi vegetasi dan NDVI |
| B11 | SWIR1 | 20 m | Kelembapan permukaan, NDBI, pemisahan kelas |

Produk harus mencakup lokasi poligon. Wilayah kajian yang luas dapat memerlukan beberapa tile/granula. Pilih tanggal yang berdekatan dengan awan sesedikit mungkin. Setiap file JP2 harus berasal dari band, produk, dan granula yang cocok.

## Fitur turunan

- `NDVI = (B08 - B04) / (B08 + B04)`
- `NDWI = (B03 - B08) / (B03 + B08)`
- `NDBI = (B11 - B08) / (B11 + B08)`

Nilai indeks yang penyebutnya nol atau tidak valid harus dikeluarkan dari sampel. Data hasil ekstraksi berisi satu baris per piksel valid; ukuran akhir bergantung pada citra dan poligon yang benar-benar tertutup data.
