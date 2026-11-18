# Arsitektur Sistem Monitoring OOH

Aplikasi ini adalah sistem berbasis Streamlit untuk mengelola aset media **Out of Home (OOH)**, memantau kontrak, dan mencatat pergantian brand atau visual.

## Diagram arsitektur

```text
Pengguna
   │
   ▼
app.py — Antarmuka Streamlit
   ├── Dashboard, peta, grafik, dan tabel monitoring
   ├── Form tambah/edit/hapus data OOH
   ├── Penggantian brand/visual dan riwayat
   ├── Laporan kontrak dan ekspor Excel
   └── Sinkronisasi Google Sheets
          │
          ├── data_manager.py — Logika dan akses data
          │      ├── Membaca/menyimpan data Excel
          │      ├── Menghitung metrik dan status kontrak
          │      └── Mengelola riwayat pergantian dan rollback
          │
          ├── data/*.xlsx — Penyimpanan lokal
          │      ├── Master OOH
          │      ├── Riwayat pergantian
          │      └── Master vendor, visual, dan pejabat
          │
          ├── Google Apps Script — Backup dan pemulihan data
          │      └── Terhubung melalui HTTP POST
          │
          └── File GeoJSON — Batas wilayah untuk peta
```

## Komponen

- **`app.py`** — Lapisan antarmuka dan alur aplikasi. Menyajikan dashboard, pengelolaan OOH, pergantian brand/visual, laporan kontrak, pengaturan master, monitoring event, dan daftar materi promosi.
- **`data_manager.py`** — Lapisan pengelolaan data. Membaca dan menyimpan berkas Excel, menghitung durasi serta status kontrak, mencatat pergantian, dan memuat master materi promosi.
- **`data/*.xlsx`** — Penyimpanan lokal untuk master titik OOH, riwayat pergantian, vendor/visual/pejabat, serta daftar materi promosi yang difilter.
- **Google Apps Script / Google Sheets** — Integrasi eksternal untuk membackup dan memulihkan data melalui permintaan HTTP POST dari aplikasi.
- **Berkas GeoJSON** — Sumber batas kecamatan yang dipakai untuk visualisasi peta.

## Alur data

1. Pengguna berinteraksi dengan fitur melalui antarmuka Streamlit di `app.py`.
2. Untuk membaca atau mengubah data lokal, aplikasi memanggil fungsi di `data_manager.py`.
3. Data master dan riwayat disimpan dalam berkas Excel di direktori `data/`; metrik kontrak dihitung saat data dimuat.
4. Daftar materi promosi hanya memuat material Vinyl Billboard, Vinyl Baliho, Vinyl PJU, dan Vinyl Midis; file Excel dapat diunggah untuk mengganti daftar, filter stok tersedia, dan pilihan brand/versi pada penggantian visual disaring sesuai jenis serta ukuran titik OOH.
5. Dashboard menggunakan data tersebut untuk menyajikan ringkasan, grafik, tabel, dan peta. Peta memerlukan berkas GeoJSON.
6. Pengguna dapat memicu backup ke atau pemulihan dari Google Sheets melalui Google Apps Script.

## Teknologi utama

- Python dan Streamlit
- Pandas dan berkas Excel (`openpyxl`)
- Plotly dan Matplotlib untuk visualisasi
- GeoJSON untuk data batas peta
- `requests` untuk integrasi Google Apps Script
