import pandas as pd
import streamlit as st

from data_manager import load_master_data

st.title("📺 Monitoring Visual OOH Terpasang — Event")
st.caption("Daftar titik OOH yang saat ini memiliki brand/visual event aktif.")

try:
    df_master = load_master_data()
except Exception as exc:
    st.error(f"Gagal memuat data master OOH: {exc}")
    st.stop()

required_columns = ["Master Brand Event", "Versi event"]
missing_columns = [column for column in required_columns if column not in df_master.columns]
if missing_columns:
    st.error("Kolom data event tidak ditemukan: " + ", ".join(missing_columns))
    st.stop()

# Hanya tampilkan titik yang memiliki brand event aktif.
event_brand = df_master["Master Brand Event"].astype("string").str.strip()
event_mask = (
    event_brand.notna()
    & ~event_brand.str.lower().isin(["", "-", "nan", "none", "<na>"])
)
df_event = df_master.loc[event_mask].copy()

if df_event.empty:
    st.info("Belum ada visual event yang sedang terpasang.")
    st.stop()

filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    kota_values = sorted(df_event["Kota"].dropna().astype(str).unique().tolist()) if "Kota" in df_event else []
    selected_kota = st.selectbox("Filter Kota", ["Semua Kota"] + kota_values)
with filter_col2:
    vendor_values = sorted(df_event["Nama Vendor"].dropna().astype(str).unique().tolist()) if "Nama Vendor" in df_event else []
    selected_vendor = st.selectbox("Filter Vendor", ["Semua Vendor"] + vendor_values)
with filter_col3:
    brand_values = sorted(event_brand.loc[event_mask].dropna().astype(str).unique().tolist())
    selected_brand = st.selectbox("Filter Brand Event", ["Semua Brand"] + brand_values)

if selected_kota != "Semua Kota":
    df_event = df_event[df_event["Kota"].astype(str) == selected_kota]
if selected_vendor != "Semua Vendor":
    df_event = df_event[df_event["Nama Vendor"].astype(str) == selected_vendor]
if selected_brand != "Semua Brand":
    df_event = df_event[df_event["Master Brand Event"].astype(str).str.strip() == selected_brand]

st.metric("Jumlah Titik dengan Event Aktif", f"{len(df_event)} titik")

columns_to_show = [
    "Kota", "Zona", "Sektor", "ID OOH", "Nama Vendor", "Jenis OOH",
    "Ukuran", "Jumlah Muka", "FL / BL", "Lokasi",
    "Master Brand Event", "Versi event",
    "Periode Kontak Awal", "Periode Kontak Akhir", "Status Kontrak",
]
visible_columns = [column for column in columns_to_show if column in df_event.columns]
view = df_event[visible_columns].copy()
view.rename(
    columns={
        "Master Brand Event": "Brand Event Terpasang",
        "Versi event": "Versi Event Terpasang",
    },
    inplace=True,
)

st.dataframe(view, use_container_width=True, hide_index=True)

csv_bytes = view.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "📥 Unduh daftar event (CSV)",
    data=csv_bytes,
    file_name="monitoring_visual_event_ooh.csv",
    mime="text/csv",
)
