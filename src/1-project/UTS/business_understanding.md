# Business Understanding

## Latar belakang

Informasi tutupan lahan membantu memahami persebaran kawasan terbangun, lahan pertanian, perairan, dan vegetasi di Jawa Timur. Digitasi poligon menyediakan contoh lokasi dan kelas untuk melatih serta mengevaluasi model klasifikasi berbasis citra Sentinel-2.

## Tujuan

Membangun alur yang dapat:

1. Mengubah label poligon hasil digitasi menjadi sampel piksel Sentinel-2 yang berfitur dan berlabel.
2. Melatih model untuk membedakan lima kelas tutupan lahan.
3. Menampilkan poligon label di atas basemap satelit dan memudahkan pemeriksaan visual per kelas.
4. Menyajikan metrik evaluasi dan kontribusi fitur agar hasil model dapat diperiksa, bukan hanya menghasilkan peta.

## Pengguna dan manfaat

Pengguna utama adalah mahasiswa/pengajar yang memeriksa hasil digitasi dan model. Alur ini dapat menjadi demonstrasi awal pemetaan dan penyaringan lokasi untuk pemeriksaan lanjutan; hasilnya tidak menggantikan survei lapangan, peta resmi, atau keputusan tata ruang.

## Kelas

- **Built-up** — bangunan dan permukaan terbangun.
- **Farm land** — lahan pertanian, termasuk sawah.
- **Water body** — laut, danau, sungai, dan perairan.
- **Forest** — hutan non-mangrove.
- **Mangrove** — vegetasi mangrove di wilayah pesisir.

## Kriteria keberhasilan

- GeoJSON dapat ditampilkan di atas basemap satelit dan kelas dapat difilter.
- Sampel train/test memuat seluruh fitur yang disepakati serta dipisah berdasarkan ID poligon untuk menghindari kebocoran antar piksel dari poligon yang sama.
- Evaluasi melaporkan metrik per kelas dan matriks konfusi.
- Semua hasil dibatasi oleh cakupan, kualitas, waktu akuisisi, dan tutupan awan citra yang tersedia.

## Batasan

Band B08, B11, dan indeks spektral dapat membantu pemisahan vegetasi, kelembapan, air, dan kawasan terbangun, tetapi tidak menjamin mangrove selalu terbedakan dengan benar. Validasi label, tanggal citra, tutupan awan, resolusi, dan kondisi pasang surut tetap penting. Peta label pada aplikasi adalah hasil digitasi, bukan prediksi model.
