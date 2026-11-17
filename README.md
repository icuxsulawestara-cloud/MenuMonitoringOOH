# Arsitektur Sistem Monitoring OOH

Aplikasi ini adalah sistem berbasis Streamlit untuk mengelola aset media **Out of Home (OOH)**, memantau kontrak, dan mencatat pergantian brand atau visual.

## Diagram arsitektur

```text
┌──────────────┐
│   Pengguna   │
└──────┬───────┘
       │ menggunakan aplikasi
       ▼
┌──────────────────────────────────────────┐
│ app.py — Antarmuka Streamlit             │
│                                          │
│ • Dashboard, grafik, peta, dan monitoring│
│ • Form master data OOH                   │
│ • Pergantian brand/visual dan riwayat    │
│ • Laporan kontrak dan ekspor Excel       │
│ • Kontrol backup/load Google Sheets      │
└───────────┬──────────────────┬───────────┘
            │                  │
            ▼                  ▼
┌─────────────────────┐  ┌────────────────────────┐
│ data_manager.py     │  │ Google Apps Script     │
│                     │  │ melalui HTTP POST      │
│ • Baca/tulis Excel  │  │ Backup dan pemulihan   │
│ • Hitung kontrak    │  │ data Google Sheets     │
│ • Kelola riwayat    │  └────────────────────────┘
│ • Rollback perubahan│
└──────────┬──────────┘
           ▼
┌──────────────────────────┐   ┌───────────────────┐
│ data/*.xlsx              │   │ File GeoJSON      │
│ Penyimpanan lokal        │   │ Batas wilayah peta│
│ • Master OOH             │   └───────────────────┘
│ • Riwayat pergantian     │
│ • Master vendor/visual/  │
│   pejabat                │
└──────────────────────────┘
```

## Komponen

- **`app.py`** — Lapisan antarmuka dan alur aplikasi. Menyajikan lima menu: dashboard, pengelolaan master OOH, pergantian brand/visual, laporan kontrak, dan pengaturan master.
- **`data_manager.py`** — Lapisan pengelolaan data. Membaca dan menyimpan berkas Excel, menghitung durasi serta status kontrak, mencatat pergantian, dan melakukan rollback riwayat.
- **`data/*.xlsx`** — Penyimpanan lokal untuk master titik OOH, riwayat pergantian, serta data vendor, visual, dan pejabat.
- **Google Apps Script / Google Sheets** — Integrasi eksternal untuk membackup dan memulihkan data melalui permintaan HTTP POST dari aplikasi.
- **Berkas GeoJSON** — Sumber batas kecamatan yang dipakai untuk visualisasi peta.

## Alur data

1. Pengguna berinteraksi dengan fitur melalui antarmuka Streamlit di `app.py`.
2. Untuk membaca atau mengubah data lokal, aplikasi memanggil fungsi di `data_manager.py`.
3. Data master dan riwayat disimpan dalam berkas Excel di direktori `data/`; metrik kontrak dihitung saat data dimuat.
4. Dashboard menggunakan data tersebut untuk menyajikan ringkasan, grafik, tabel, dan peta. Peta memerlukan berkas GeoJSON.
5. Pengguna dapat memicu backup ke atau pemulihan dari Google Sheets melalui Google Apps Script.

## Teknologi utama

- Python dan Streamlit
- Pandas dan berkas Excel (`openpyxl`)
- Plotly dan Matplotlib untuk visualisasi
- GeoJSON untuk data batas peta
- `requests` untuk integrasi Google Apps Script
