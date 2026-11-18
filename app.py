import io
import json
import math
import os
import urllib.parse
from datetime import date
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import requests

from data_manager import (
    COLUMNS_MASTER,
    load_extra_masters,
    load_log_data,
    load_master_data,
    load_promo_materials,
    now_wib,
    parse_promo_material_upload,
    rollback_log_entry,
    save_extra_masters,
    save_log_data,
    save_master_data,
    save_promo_materials,
    get_effective_brand_version,
    enrich_contract_metrics,
    append_log_pergantian,
)

st.set_page_config(
    page_title="Sistem Kontrol & Monitoring OOH",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #FAF7F2; }
    div[data-testid="metric-container"] {
        background-color: #FFFFFF;
        border: 1px solid #E6DFD3;
        padding: 14px 18px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .warning-banner {
        background-color: #FFF3CD;
        border-left: 5px solid #D97706;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 16px;
        color: #78350F;
    }
    .critical-banner {
        background-color: #FEE2E2;
        border-left: 5px solid #DC2626;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 16px;
        color: #7F1D1D;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbwYbKoYHZQmOjbK9nx2nviWu0G1rXeqxg3NZf0j2KCUISZfp6SEY3iEPW0mwy1WO0A/exec"

def clean_for_json(obj):
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif pd.isna(obj):
        return None
    return obj

def backup_to_google_sheets():
    try:
        if not WEB_APP_URL or "MASUKKAN_URL" in WEB_APP_URL:
            return False, "URL Web App Google Apps Script belum diatur di dalam kode (`WEB_APP_URL`)!"

        df_master = load_master_data()
        master_data = []
        if not df_master.empty:
            master_data = [COLUMNS_MASTER] + df_master[COLUMNS_MASTER].astype(str).values.tolist()

        df_log = load_log_data()
        log_data = []
        if not df_log.empty:
            log_data = [df_log.columns.tolist()] + df_log.astype(str).values.tolist()

        df_v, df_vis, df_p = load_extra_masters()
        vendor_data = [df_v.columns.tolist()] + df_v.astype(str).values.tolist() if not df_v.empty else []
        visual_data = [df_vis.columns.tolist()] + df_vis.astype(str).values.tolist() if not df_vis.empty else []
        pejabat_data = [df_p.columns.tolist()] + df_p.astype(str).values.tolist() if not df_p.empty else []

        payload = {
            "action": "backup",
            "master_ooh": master_data,
            "riwayat_pergantian": log_data,
            "master_vendor": vendor_data,
            "master_visual": visual_data,
            "master_pejabat": pejabat_data
        }

        clean_payload = clean_for_json(payload)
        response = requests.post(WEB_APP_URL, json=clean_payload, timeout=30)

        if response.text.strip().startswith("<!DOCTYPE html>") or "<html" in response.text.lower():
            return False, "Gagal: Google Apps Script mengembalikan halaman HTML (Pastikan akses Web App diset ke 'Anyone')."

        try:
            result = response.json()
        except Exception:
            return False, f"Gagal membaca JSON. Respons server: {response.text[:200]}"

        if result.get("status") == "success":
            return True, "Data berhasil dibackup dan ditimpa (overwrite) ke Google Sheet!"
        else:
            return False, result.get("message", "Gagal backup oleh Apps Script.")

    except requests.exceptions.Timeout:
        return False, "Error: Koneksi timeout ke Google Apps Script (proses terlalu lama)."
    except Exception as e:
        return False, f"Error koneksi: {e}"

def load_from_google_sheets():
    try:
        if not WEB_APP_URL or "MASUKKAN_URL" in WEB_APP_URL:
            return False, "URL Web App Google Apps Script belum diatur di dalam kode (`WEB_APP_URL`)!"

        payload = {"action": "load"}
        response = requests.post(WEB_APP_URL, json=payload, timeout=30)

        if response.text.strip().startswith("<!DOCTYPE html>") or "<html" in response.text.lower():
            return False, "Gagal: Google Apps Script mengembalikan halaman HTML (Pastikan akses Web App diset ke 'Anyone')."

        try:
            result = response.json()
        except Exception:
            return False, f"Gagal membaca JSON. Respons server: {response.text[:200]}"

        if result.get("status") == "success":
            db_data = result.get("data", {})

            master_vals = db_data.get("master_ooh", [])
            if len(master_vals) > 1:
                df_master_loaded = pd.DataFrame(master_vals[1:], columns=master_vals[0])
                df_master_loaded.replace("", None, inplace=True)
                save_master_data(df_master_loaded)

            log_vals = db_data.get("riwayat_pergantian", [])
            if len(log_vals) > 1:
                df_log_loaded = pd.DataFrame(log_vals[1:], columns=log_vals[0])
                df_log_loaded.replace("", None, inplace=True)
                save_log_data(df_log_loaded)

            df_v_load = pd.DataFrame(db_data.get("master_vendor", [["Nama Vendor", "Email Vendor"]])[1:],
                                      columns=db_data.get("master_vendor", [["Nama Vendor", "Email Vendor"]])[0]) if len(db_data.get("master_vendor", [])) > 1 else pd.DataFrame(columns=["Nama Vendor", "Email Vendor"])
            
            # Sesuaikan kunci dictionary payload dari Apps Script
            df_vis_load = pd.DataFrame(db_data.get("master_visual_ooh", db_data.get("master_visual", [["Master Brand", "Versi / Visual"]]))[1:],
                                        columns=db_data.get("master_visual_ooh", db_data.get("master_visual", [["Master Brand", "Versi / Visual"]]))[0]) if len(db_data.get("master_visual_ooh", db_data.get("master_visual", []))) > 1 else pd.DataFrame(columns=["Master Brand", "Versi / Visual"])
            
            df_p_load = pd.DataFrame(db_data.get("master_email_pejabat", db_data.get("master_pejabat", [["CC Email"]]))[1:],
                                      columns=db_data.get("master_email_pejabat", db_data.get("master_pejabat", [["CC Email"]]))[0]) if len(db_data.get("master_email_pejabat", db_data.get("master_pejabat", []))) > 1 else pd.DataFrame(columns=["CC Email"])

            save_extra_masters(df_v_load, df_vis_load, df_p_load)

            return True, "Data berhasil ditarik dan dipulihkan dari Google Sheet!"
        else:
            return False, result.get("message", "Gagal memuat data.")

    except requests.exceptions.Timeout:
        return False, "Error: Koneksi timeout ke Google Apps Script (proses terlalu lama)."
    except Exception as e:
        return False, f"Error koneksi: {e}"

def clean_str(val, default=""):
    if pd.isna(val) or str(val).strip().lower() in ["nan", "none", ""]:
        return default
    return str(val).strip()

def format_rp(val):
    if pd.isna(val):
        return "Rp 0"
    return f"Rp {val:,.0f}".replace(",", ".")

def norm_kecamatan_key(val: str) -> str:
    if pd.isna(val):
        return ""
    return "".join(str(val).lower().split())

@st.cache_data
def load_combined_geojson():
    geojson_files = [
        ("Gresik", "Map-Gresik.geojson"),
        ("Surabaya", "Map-Surabaya Barat.geojson"),
    ]
    combined_features = []
    meta_rows = []

    for kota_name, filepath in geojson_files:
        if not os.path.exists(filepath):
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            gj = json.load(f)
        for feat in gj.get("features", []):
            props = feat.get("properties", {})
            nm_kec = str(props.get("nm_kecamatan", "")).strip()
            norm_key = norm_kecamatan_key(nm_kec)
            feature_id = f"{kota_name}|{norm_key}"

            lons, lats = [], []
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])

            def extract_coords(c_list):
                if not c_list:
                    return
                if isinstance(c_list[0], (int, float)):
                    lons.append(c_list[0])
                    lats.append(c_list[1])
                else:
                    for sub in c_list:
                        extract_coords(sub)

            extract_coords(coords)
            center_lat = sum(lats) / len(lats) if lats else -7.25
            center_lon = sum(lons) / len(lons) if lons else 112.68

            new_feat = {
                "type": "Feature",
                "id": feature_id,
                "properties": {
                    **props,
                    "kota": kota_name,
                    "nm_kecamatan": nm_kec,
                    "norm_key": norm_key,
                    "feature_id": feature_id,
                },
                "geometry": geom,
            }
            combined_features.append(new_feat)
            meta_rows.append(
                {
                    "feature_id": feature_id,
                    "Kota": kota_name,
                    "Kecamatan": nm_kec,
                    "norm_key": norm_key,
                    "center_lat": center_lat,
                    "center_lon": center_lon,
                }
            )

    combined_gj = {"type": "FeatureCollection", "features": combined_features}
    df_meta = pd.DataFrame(meta_rows)
    return combined_gj, df_meta

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if df.empty:
            pd.DataFrame(columns=df.columns if len(df.columns) > 0 else ["Info"]).to_excel(
                writer, index=False, sheet_name="Report OOH"
            )
        else:
            df.to_excel(writer, index=False, sheet_name="Report OOH")
        writer.book.active.sheet_state = "visible"
    return output.getvalue()

def get_brand_style(brand_name: str):
    b = str(brand_name).upper().strip()
    if "BLACK" in b or "D WRAPS" in b or ("DJARUM" in b and "76" not in b):
        return "#000000", "#A3E635"
    elif "LA ICE" in b or "LA BOLD" in b:
        return "#002395", "#FFFFFF"
    elif "76" in b or "APEL" in b:
        return "#F87171", "#111827"
    elif "SUPER" in b:
        return "#991B1B", "#FFFFFF"
    elif b in ["-", "", "NONE", "NAN"]:
        return "#FFFFFF", "#111827"
    return "#1F2937", "#F9FAFB"

def generate_ooh_replacement_png(
    df_table: pd.DataFrame,
    info_pasang: str = "-",
    info_bongkar: str = "-",
    catatan_pasang: str = "Penggantian Versi OOH",
    catatan_bongkar: str = "Materi Lama / Lepasan > Harap segera dikembalikan ke Gudang DSO Surabaya Barat (Pak Amin)",
) -> bytes:
    num_rows = len(df_table)

    col_max_lengths = []
    for col in df_table.columns:
        max_len = max([len(str(col))] + [len(str(val)) for val in df_table[col].values])
        col_max_lengths.append(max(max_len, 4))

    total_len = sum(col_max_lengths)
    col_widths = [length / total_len for length in col_max_lengths]

    fig_width = max(25, len(df_table.columns) * 2.2)
    row_height = 0.45
    fig_height = max(3.5, (num_rows + 4) * row_height)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis("off")

    y_top = 0.98
    h_info = 0.11 if num_rows <= 4 else 0.075

    w_col1_2 = col_widths[0] + col_widths[1]
    w_col3_4 = col_widths[2] + col_widths[3] if len(col_widths) > 3 else 0.1
    w_rest = 1.0 - (w_col1_2 + w_col3_4)

    y_r1 = y_top - h_info
    ax.add_patch(patches.Rectangle((0, y_r1), w_col1_2, h_info, facecolor="#FFFFFF", edgecolor="#000000", lw=1))
    ax.text(w_col1_2 / 2, y_r1 + h_info / 2, "Info Pasang :", ha="center", va="center", fontsize=9.5, weight="bold")

    ax.add_patch(patches.Rectangle((w_col1_2, y_r1), w_col3_4, h_info, facecolor="#FEF3C7", edgecolor="#000000", lw=1))
    ax.text(w_col1_2 + w_col3_4 / 2, y_r1 + h_info / 2, info_pasang, ha="center", va="center", fontsize=9.5, weight="bold")

    ax.add_patch(patches.Rectangle((w_col1_2 + w_col3_4, y_r1), w_rest, h_info, facecolor="#FFFFFF", edgecolor="#000000", lw=1))
    ax.text(w_col1_2 + w_col3_4 + 0.008, y_r1 + h_info / 2, catatan_pasang, ha="left", va="center", fontsize=9.5, weight="bold")

    y_r2 = y_r1 - h_info
    ax.add_patch(patches.Rectangle((0, y_r2), w_col1_2, h_info, facecolor="#FFFFFF", edgecolor="#000000", lw=1))
    ax.text(w_col1_2 / 2, y_r2 + h_info / 2, "Info Bongkar :", ha="center", va="center", fontsize=9.5, weight="bold")

    ax.add_patch(patches.Rectangle((w_col1_2, y_r2), w_col3_4, h_info, facecolor="#FEF3C7", edgecolor="#000000", lw=1))
    ax.text(w_col1_2 + w_col3_4 / 2, y_r2 + h_info / 2, info_bongkar, ha="center", va="center", fontsize=9.5, weight="bold")

    ax.add_patch(patches.Rectangle((w_col1_2 + w_col3_4, y_r2), w_rest, h_info, facecolor="#FFFFFF", edgecolor="#000000", lw=1))
    ax.text(w_col1_2 + w_col3_4 + 0.008, y_r2 + h_info / 2, catatan_bongkar, ha="left", va="center", fontsize=9.5, weight="bold", color="#DC2626")

    table_bbox = [0.0, 0.02, 1.0, y_r2 - 0.025]
    table = ax.table(cellText=df_table.values, colLabels=df_table.columns, loc="center", bbox=table_bbox)
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)

    for (row, col), cell in table.get_celld().items():
        cell.set_width(col_widths[col])
        cell.set_edgecolor("#000000")
        cell.set_linewidth(0.8)

        if row == 0:
            cell.set_height(0.14)
            if col <= 9:
                cell.set_facecolor("#D9D9D9")
                cell.set_text_props(color="#000000", weight="bold", ha="center", va="center")
            elif col in [10, 11]:
                cell.set_facecolor("#FFFF00")
                cell.set_text_props(color="#000000", weight="bold", ha="center", va="center")
            else:
                cell.set_facecolor("#00FF88")
                cell.set_text_props(color="#000000", weight="bold", ha="center", va="center")
        else:
            val_str = str(df_table.iloc[row - 1, col])
            if col in [9, 11, 13]:
                cell.get_text().set_ha("left")
                cell.PAD = 0.04
            else:
                cell.get_text().set_ha("center")

            if col in [10, 12]:
                bg_color, txt_color = get_brand_style(val_str)
                cell.set_facecolor(bg_color)
                cell.set_text_props(color=txt_color, weight="bold")
            else:
                cell.set_facecolor("#FFFFFF")
                if col <= 8:
                    cell.set_text_props(color="#000000", weight="bold")
                else:
                    cell.set_text_props(color="#000000", weight="normal")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.15, dpi=300)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

df = load_master_data()
df_vendor_master, df_visual_master, df_pejabat_master = load_extra_masters()
df_promo_materials = load_promo_materials()

brand_choices = []
if not df_visual_master.empty:
    for col in df_visual_master.columns:
        if "brand" in col.lower():
            brand_choices = sorted([str(x).strip() for x in df_visual_master[col].dropna().unique().tolist() if str(x).strip() != "" and str(x).lower() != "nan"])
            break
    if not brand_choices and len(df_visual_master.columns) > 0:
        brand_choices = sorted([str(x).strip() for x in df_visual_master.iloc[:, 0].dropna().unique().tolist() if str(x).strip() != "" and str(x).lower() != "nan"])

if not brand_choices:
    brand_choices = ["-"]

promo_brand_choices = (
    df_promo_materials["Brand"]
    .dropna()
    .astype(str)
    .str.strip()
    .loc[lambda values: values.ne("")]
    .unique()
    .tolist()
)
replacement_brand_choices = sorted(set(brand_choices + promo_brand_choices))

# ==============================================================================
# SIDEBAR: KONTROL PANEL
# ==============================================================================
st.sidebar.title("Kontrol OOH")
st.sidebar.caption(f"Waktu Server: {now_wib().strftime('%d-%m-%Y %H:%M')} WIB")

menu = st.sidebar.radio(
    "Pilih Menu:",
    [
        "1. Dashboard & Monitoring OOH",
        "2. Master Data OOH (Tambah / Edit)",
        "3. Penggantian Brand & Visual",
        "4. Report Kontrak & Warning",
        "5. Pengaturan Master (Vendor, Visual & Pejabat)",
        "6. Monitoring Visual OOH (Event)",
        "7. List Materi Promosi",
    ],
)

st.sidebar.divider()
st.sidebar.subheader("Filter Global (Sidebar)")
kota_list = ["Semua Kota"] + sorted(df["Kota"].dropna().unique().tolist())
selected_kota = st.sidebar.selectbox("Kota", kota_list)

df_filtered = df.copy()
if "Status Kontrak" not in df_filtered.columns:
    df_filtered = enrich_contract_metrics(df_filtered)

if selected_kota != "Semua Kota":
    df_filtered = df_filtered[df_filtered["Kota"] == selected_kota]

zona_list = ["Semua Zona"] + sorted(df_filtered["Zona"].dropna().unique().tolist())
selected_zona = st.sidebar.selectbox("Zona", zona_list)
if selected_zona != "Semua Zona":
    df_filtered = df_filtered[df_filtered["Zona"] == selected_zona]
    
# --- BACKUP & LOAD GOOGLE SHEETS ---
st.sidebar.divider()
st.sidebar.subheader("☁️ Backup & Load Google Sheet")

with st.sidebar.expander("Pengaturan & Sinkronisasi Sheet", expanded=False):
    st.caption("✅ Menggunakan koneksi Web App Google Apps Script.")

    col_gs1, col_gs2 = st.columns(2)
    with col_gs1:
        btn_backup_gs = st.button("⬆️ Backup", use_container_width=True)
    with col_gs2:
        btn_load_gs = st.button("⬇️ Load", use_container_width=True)

    if btn_backup_gs:
        try:
            with st.spinner("Mem-backup ke Google Sheet..."):
                success, msg = backup_to_google_sheets()
                if success:
                    st.success("✅ " + msg)
                else:
                    st.error("❌ " + msg)
        except Exception as e:
            st.error(f"Gagal backup: {e}")

    if btn_load_gs:
        try:
            with st.spinner("Memuat dari Google Sheet..."):
                success, msg = load_from_google_sheets()
                if success:
                    st.success("✅ " + msg)
                    st.rerun()
                else:
                    st.error("❌ " + msg)
        except Exception as e:
            st.error(f"Gagal load: {e}")

# ==============================================================================
# MENU 1: DASHBOARD & MONITORING OOH
# ==============================================================================
if menu == "1. Dashboard & Monitoring OOH":
    st.title("Dashboard & Monitoring Media OOH")

    if "Status Kontrak" not in df_filtered.columns:
        df_filtered = enrich_contract_metrics(df_filtered)

    jml_expired = (df_filtered["Status Kontrak"] == "Expired").sum()
    jml_kritis = (df_filtered["Status Kontrak"] == "Kritis (<= 30 Hari)").sum()
    jml_warning = (df_filtered["Status Kontrak"] == "Warning (31-90 Hari)").sum()

    if jml_expired > 0 or jml_kritis > 0:
        st.markdown(f"<div class='critical-banner'><strong>PERHATIAN:</strong> Terdapat <b>{jml_expired} titik Expired</b> dan <b>{jml_kritis} titik Kritis (≤ 30 hari)</b>.</div>", unsafe_allow_html=True)
    if jml_warning > 0:
        st.markdown(f"<div class='warning-banner'><strong>REMINDER:</strong> Terdapat <b>{jml_warning} titik OOH</b> akan berakhir dalam 31–90 hari.</div>", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Titik OOH", f"{len(df_filtered)} Titik")
    c2.metric(
        "Total Jumlah Muka OOH",
        f"{pd.to_numeric(df_filtered['Total Muka'], errors='coerce').fillna(0).sum():,.0f} Muka",
    )
    c3.metric("Total Nominal Kontrak", format_rp(df_filtered["Nominal Kontrak"].sum()))
    c4.metric("Total Kontrak / Tahun", format_rp(df_filtered["Nominal Tahunan"].sum()))
    c5.metric("Perlu Renewal (≤ 90 Hari)", f"{jml_kritis + jml_warning} Titik")
    st.divider()

    st.subheader("Distribusi Jumlah Muka OOH berdasarkan Mother Brand")

    brand_faces = pd.concat(
        [
            df_filtered["Mother Brand Muka 1"],
            df_filtered["Mother Brand Muka 2"],
        ],
        ignore_index=True,
    )

    brand_faces = brand_faces.dropna().astype(str).str.strip()
    brand_faces = brand_faces[~brand_faces.str.lower().isin(["", "-", "nan", "none", "all brand"])]

    if brand_faces.empty:
        st.info("Belum ada data Mother Brand Muka 1 atau Muka 2.")
    else:
        brand_face_counts = brand_faces.value_counts().rename_axis("Brand").reset_index(name="Total Muka")
        fig_brand_faces = px.pie(
            brand_face_counts,
            names="Brand",
            values="Total Muka",
            hole=0.45,
            title="Distribusi Total Muka OOH per Mother Brand (Muka 1 + Muka 2)",
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        fig_brand_faces.update_traces(textinfo="percent", textposition="inside", textfont_size=11)
        fig_brand_faces.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=380,
            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig_brand_faces, use_container_width=True)

    # PETA SEBARAN MEDIA OOH & KECAMATAN
    st.subheader("🗺️ Peta Sebaran Media OOH & Wilayah Kecamatan (Gresik & Surabaya)")
    show_maps_ooh = st.toggle("Show Maps OOH (Aktifkan untuk memuat peta)", value=False)

    if show_maps_ooh:
        combined_gj, df_geo_meta = load_combined_geojson()

        if df_geo_meta.empty:
            st.warning("⚠️ File `Map-Gresik.geojson` atau `Map-Surabaya Barat.geojson` tidak ditemukan di direktori aplikasi.")
        else:
            col_map1, col_map2 = st.columns([1, 1])
            with col_map1:
                map_kota_opts = ["Semua Kota"] + sorted(df_geo_meta["Kota"].unique().tolist())
                default_map_kota_idx = map_kota_opts.index(selected_kota) if selected_kota in map_kota_opts else 0
                map_kota = st.selectbox("Filter Kota (Peta)", map_kota_opts, index=default_map_kota_idx, key="map_filter_kota")

            df_meta_sub = df_geo_meta if map_kota == "Semua Kota" else df_geo_meta[df_geo_meta["Kota"] == map_kota]

            with col_map2:
                map_kec_opts = ["Semua Kecamatan"] + sorted(df_meta_sub["Kecamatan"].unique().tolist())
                map_kec = st.selectbox("Filter Kecamatan (Peta)", map_kec_opts, key="map_filter_kec")

            df_map_pts = df_filtered.copy()
            df_map_pts["norm_key"] = df_map_pts["Sektor"].apply(norm_kecamatan_key)
            df_map_pts["Kota_Clean"] = df_map_pts["Kota"].astype(str).str.strip()

            if map_kota != "Semua Kota":
                df_map_pts = df_map_pts[df_map_pts["Kota_Clean"].str.lower() == map_kota.lower()]
            if map_kec != "Semua Kecamatan":
                sel_norm = norm_kecamatan_key(map_kec)
                df_map_pts = df_map_pts[df_map_pts["norm_key"] == sel_norm]

            valid_coords = df_map_pts.dropna(subset=["Latitude", "Longitude"]).copy()
            valid_coords = valid_coords[(valid_coords["Latitude"] != 0) & (valid_coords["Longitude"] != 0)]

            df_poly = df_meta_sub.copy()
            df_poly["Jumlah Titik"] = 0
            df_poly["Status_Wilayah"] = "Kosong"

            point_counts = df_map_pts.groupby("norm_key").size().to_dict()
            for idx, row in df_poly.iterrows():
                key = str(row["norm_key"])
                jml = int(point_counts.get(key, 0))
                df_poly.at[idx, "Jumlah Titik"] = jml
                if map_kec != "Semua Kecamatan" and str(row["Kecamatan"]).strip() == str(map_kec).strip():
                    df_poly.at[idx, "Status_Wilayah"] = "Kecamatan Terpilih"
                elif jml > 0:
                    df_poly.at[idx, "Status_Wilayah"] = "Ada Titik OOH"
                else:
                    df_poly.at[idx, "Status_Wilayah"] = "Kosong"

            if map_kec != "Semua Kecamatan" and not df_poly.empty:
                center_lat = float(df_poly[df_poly["Kecamatan"] == map_kec]["center_lat"].iloc[0])
                center_lon = float(df_poly[df_poly["Kecamatan"] == map_kec]["center_lon"].iloc[0])
                zoom_lvl = 12.0
            elif not valid_coords.empty:
                center_lat = float(valid_coords["Latitude"].mean())
                center_lon = float(valid_coords["Longitude"].mean())
                zoom_lvl = 10.5 if map_kota != "Semua Kota" else 9.5
            elif not df_poly.empty:
                center_lat = float(df_poly["center_lat"].mean())
                center_lon = float(df_poly["center_lon"].mean())
                zoom_lvl = 10.0
            else:
                center_lat, center_lon, zoom_lvl = -7.23, 112.66, 9.5

            st.caption(f"📍 Menampilkan **{len(valid_coords)} titik OOH** pada wilayah terpilih.")

            fig_map = px.choropleth_map(
                df_poly,
                geojson=combined_gj,
                locations="feature_id",
                featureidkey="id",
                color="Status_Wilayah",
                color_discrete_map={
                    "Kosong": "rgba(59, 130, 246, 0.10)",
                    "Ada Titik OOH": "rgba(16, 185, 129, 0.28)",
                    "Kecamatan Terpilih": "rgba(245, 158, 11, 0.42)",
                },
                hover_data=["Kota", "Kecamatan", "Jumlah Titik"],
                map_style="carto-positron",
                zoom=zoom_lvl,
                center={"lat": center_lat, "lon": center_lon},
                opacity=0.85,
            )

            if not valid_coords.empty:
                eff_brands_map = []
                eff_vers_map = []
                for _, r in valid_coords.iterrows():
                   eff = get_effective_brand_version(r)
                   eff_brands_map.append(eff["Brand"])
                   eff_vers_map.append(eff["Version"])

                valid_coords = valid_coords.copy()
                valid_coords["Brand_Aktif"] = eff_brands_map
                valid_coords["Versi_Aktif"] = eff_vers_map

                fig_scatter = px.scatter_map(
                    valid_coords,
                    lat="Latitude",
                    lon="Longitude",
                    custom_data=[
                        "ID OOH", "Nama Vendor", "Jenis OOH", "Ukuran",
                        "Kota", "Sektor", "Lokasi", "Brand_Aktif",
                        "Versi_Aktif", "Status Kontrak",
                    ],
                    zoom=zoom_lvl,
                    center={"lat": center_lat, "lon": center_lon},
                )
                fig_scatter.update_traces(
                    marker=dict(size=11, color="#DC2626", opacity=0.95),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b> | %{customdata[2]} (%{customdata[3]})<br>"
                        "Vendor: <b>%{customdata[1]}</b><br>"
                        "Wilayah: %{customdata[4]} - Kec. %{customdata[5]}<br>"
                        "Lokasi: %{customdata[6]}<br>"
                        "Brand Terpasang: <b>%{customdata[7]}</b> (%{customdata[8]})<br>"
                        "Status: %{customdata[9]}"
                        "<extra></extra>"
                    ),
                )
                for trace in fig_scatter.data:
                    fig_map.add_trace(trace)

                fig_map.update_layout(
                    margin={"r": 0, "t": 0, "l": 0, "b": 0},
                    height=520,
                    legend=dict(yanchor="top", y=0.98, xanchor="left", x=0.01, bgcolor="rgba(255, 255, 255, 0.88)"),
                )
            st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.info("🔒 Peta disembunyikan untuk menjaga performa agar aplikasi ringan saat dibuka. Geser toggle di atas ke posisi aktif (**Show Maps OOH**) jika ingin menampilkan peta.")

    st.divider()

    effective_brands = []
    for _, r in df_filtered.iterrows():
        eff = get_effective_brand_version(r)
        if eff["Brand"] and str(eff["Brand"]).strip().lower() not in ["nan", "none", "-", "all brand"]:
            effective_brands.append(str(eff["Brand"]).strip())

    s_brands = pd.Series(effective_brands)
    brand_combined_count = s_brands.value_counts().reset_index() if not s_brands.empty else pd.DataFrame(columns=["Brand", "Jumlah Titik"])
    if not brand_combined_count.empty:
        brand_combined_count.columns = ["Brand", "Jumlah Titik"]

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("Distribusi Brand Terpasang (Aktif / Event)")
        if not brand_combined_count.empty:
            fig_brand_donut = px.pie(brand_combined_count, names="Brand", values="Jumlah Titik", hole=0.5, color_discrete_sequence=px.colors.qualitative.Safe)
            fig_brand_donut.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=340)
            st.plotly_chart(fig_brand_donut, use_container_width=True)
        else:
            st.info("Belum ada data brand.")

    with col_chart2:
        st.subheader("Komposisi Biaya Tahunan per Jenis OOH")
        if not df_filtered.empty:
            jenis_agg = df_filtered.groupby("Jenis OOH", dropna=False).agg(Jumlah=("ID OOH", "count"), Biaya_Tahunan=("Nominal Tahunan", "sum")).reset_index()
            fig_jenis = px.pie(jenis_agg, names="Jenis OOH", values="Biaya_Tahunan", hole=0.45, color_discrete_sequence=px.colors.qualitative.Antique)
            fig_jenis.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=340)
            st.plotly_chart(fig_jenis, use_container_width=True)

    st.divider()
    st.subheader("Tabel Monitoring Penayangan OOH & Edit Manual")

    with st.expander("🔍 Filter Lanjutan Tabel Monitoring", expanded=True):
        f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns(5)
        with f_col1:
            opts_kota = ["Semua"] + sorted(df_filtered["Kota"].dropna().unique().tolist())
            filt_kota = st.selectbox("Filter Kota", opts_kota)
        with f_col2:
            opts_zona = ["Semua"] + sorted(df_filtered["Zona"].dropna().unique().tolist())
            filt_zona = st.selectbox("Filter Zona", opts_zona)
        with f_col3:
            opts_sektor = ["Semua"] + sorted(df_filtered["Sektor"].dropna().unique().tolist())
            filt_sektor = st.selectbox("Filter Sektor", opts_sektor)
        with f_col4:
            opts_vendor = ["Semua"] + sorted(df_filtered["Nama Vendor"].dropna().unique().tolist())
            filt_vendor = st.selectbox("Filter Nama Vendor", opts_vendor)
        with f_col5:
            opts_jenis = ["Semua"] + sorted(df_filtered["Jenis OOH"].dropna().unique().tolist())
            filt_jenis = st.selectbox("Filter Jenis OOH", opts_jenis)

    df_monitor = df_filtered.copy()
    if filt_kota != "Semua":
        df_monitor = df_monitor[df_monitor["Kota"] == filt_kota]
    if filt_zona != "Semua":
        df_monitor = df_monitor[df_monitor["Zona"] == filt_zona]
    if filt_sektor != "Semua":
        df_monitor = df_monitor[df_monitor["Sektor"] == filt_sektor]
    if filt_vendor != "Semua":
        df_monitor = df_monitor[df_monitor["Nama Vendor"] == filt_vendor]
    if filt_jenis != "Semua":
        df_monitor = df_monitor[df_monitor["Jenis OOH"] == filt_jenis]

    st.info("💡 Tabel ini sinkron dua arah dengan **Riwayat Pergantian Brand, Visual & Event**. Anda dapat melakukan **Edit Manual** langsung pada sel tabel di bawah.")

    edited_monitor_df = st.data_editor(
        df_monitor,
        use_container_width=True,
        hide_index=True,
        key="monitor_data_editor"
    )

    if st.button("💾 Simpan Perubahan Tabel", type="primary"):
        df_master_full = df.copy()
        for idx, row in edited_monitor_df.iterrows():
            if idx in df_master_full.index:
                for col in edited_monitor_df.columns:
                    if col in df_master_full.columns:
                        df_master_full.at[idx, col] = row[col]

        save_master_data(df_master_full)
        st.success("✅ Perubahan pada Tabel Monitoring berhasil disimpan ke Master Data!")
        st.rerun()

# ==============================================================================
# MENU 2: MASTER DATA OOH (TAMBAH / EDIT)
# ==============================================================================
elif menu == "2. Master Data OOH (Tambah / Edit)":
    st.title("Manajemen Master Data OOH")
    tab_tambah, tab_kelola = st.tabs(["Tambah Titik OOH Baru", "Edit / Hapus Data Master"])

    vendor_opts = df_vendor_master["Nama Vendor"].dropna().astype(str).tolist() if not df_vendor_master.empty else []
    if not vendor_opts:
        vendor_opts = ["Lainnya"]
    jenis_ooh_opts = ["Billboard", "Baliho", "Midis", "PJU", "LED", "Neon Box", "Lainnya"]
    fl_bl_opts = ["BL", "FL", "-"]

    with tab_tambah:
        with st.form("form_tambah_ooh", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                id_ooh = st.text_input("ID OOH *")
                nama_vendor = st.selectbox("Nama Vendor *", vendor_opts)
                kota = st.text_input("Kota *")
                zona = st.text_input("Zona *")
                sektor = st.text_input("Sektor *")
                jenis_ooh = st.selectbox("Jenis OOH *", jenis_ooh_opts)
            with col2:
                ukuran = st.text_input("Ukuran *")
                jumlah_muka = st.number_input("Jumlah Muka *", min_value=1, max_value=10, value=1)
                fl_bl = st.selectbox("FL / BL", fl_bl_opts)
                lokasi = st.text_area("Alamat / Lokasi Titik *")
                longitude = st.number_input("Longitude", value=0.0, format="%.6f")
                latitude = st.number_input("Latitude", value=0.0, format="%.6f")
            with col3:
                tgl_awal = st.date_input("Periode Kontrak Awal *", value=date(2026, 1, 1))
                tgl_akhir = st.date_input("Periode Kontrak Akhir *", value=date(2026, 12, 31))
                nominal_kontrak = st.number_input("Nominal Kontrak Total (Rp) *", min_value=0.0, step=1000000.0, value=100000000.0)

                brand_m1 = st.selectbox("Master Brand Muka 1 *", brand_choices)
                versi_m1 = st.text_input("Versi Muka 1")
                brand_m2 = st.selectbox("Master Brand Muka 2", ["-"] + brand_choices)
                versi_m2 = st.text_input("Versi Muka 2")
                brand_event = st.selectbox("Master Brand Event", ["-"] + brand_choices)
                versi_event = st.text_input("Versi event")

            submitted = st.form_submit_button("Simpan ke Master Data OOH", type="primary")
            if submitted:
                if not id_ooh.strip() or not kota.strip() or not lokasi.strip():
                    st.error("ID OOH, Kota, dan Lokasi wajib diisi.")
                else:
                    new_row = {
                        "No": len(df) + 1, "Kota": kota.strip(), "Zona": zona.strip(), "Sektor": sektor.strip(),
                        "ID OOH": id_ooh.strip(), "Nama Vendor": nama_vendor, "Jenis OOH": jenis_ooh,
                        "Ukuran": ukuran.strip(), "Jumlah Muka": int(jumlah_muka), "FL / BL": None if fl_bl == "-" else fl_bl,
                        "Lokasi": lokasi.strip(), "Periode Kontak Awal": pd.Timestamp(tgl_awal), "Periode Kontak Akhir": pd.Timestamp(tgl_akhir),
                        "Nominal Kontrak": float(nominal_kontrak), "Longitude": None if longitude == 0.0 else longitude, "Latitude": None if latitude == 0.0 else latitude,
                        "Master Brand Muka 1": brand_m1, "Master Brand Muka 2": None if brand_m2 == "-" else brand_m2,
                        "Versi Muka 1": versi_m1.strip() if versi_m1.strip() else None, "Versi Muka 2": versi_m2.strip() if versi_m2.strip() else None,
                        "Master Brand Event": None if brand_event == "-" else brand_event, "Versi event": versi_event.strip() if versi_event.strip() else None
                    }
                    save_master_data(pd.concat([df[COLUMNS_MASTER], pd.DataFrame([new_row])], ignore_index=True))
                    st.success("Titik OOH berhasil ditambahkan!")
                    st.rerun()

    with tab_kelola:
        if df.empty:
            st.info("Belum ada data master OOH.")
        else:
            df["Edit_Label"] = (
                df["ID OOH"].astype(str) + " | " + df["Nama Vendor"].fillna("-")
                + " | " + df["Kota"].fillna("-") + " - " + df["Lokasi"].fillna("-")
            )
            selected_edit_label = st.selectbox("Pilih Titik OOH yang Akan Diedit / Dihapus:", df["Edit_Label"].tolist())
            edit_idx = df[df["Edit_Label"] == selected_edit_label].index[0]
            row_edit = df.loc[edit_idx]

            with st.form("form_edit_master_ooh"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    e_id_ooh = st.text_input("ID OOH *", value=clean_str(row_edit["ID OOH"]))
                    cur_vendor = clean_str(row_edit["Nama Vendor"])
                    e_vendor_opts = vendor_opts if cur_vendor in vendor_opts or not cur_vendor else [cur_vendor] + vendor_opts
                    e_vendor_idx = e_vendor_opts.index(cur_vendor) if cur_vendor in e_vendor_opts else 0
                    e_nama_vendor = st.selectbox("Nama Vendor *", e_vendor_opts, index=e_vendor_idx)

                    e_kota = st.text_input("Kota *", value=clean_str(row_edit["Kota"]))
                    e_zona = st.text_input("Zona *", value=clean_str(row_edit["Zona"]))
                    e_sektor = st.text_input("Sektor *", value=clean_str(row_edit["Sektor"]))

                    cur_jenis = clean_str(row_edit["Jenis OOH"], "Billboard")
                    e_jenis_opts = jenis_ooh_opts if cur_jenis in jenis_ooh_opts else [cur_jenis] + jenis_ooh_opts
                    e_jenis_idx = e_jenis_opts.index(cur_jenis) if cur_jenis in e_jenis_opts else 0
                    e_jenis_ooh = st.selectbox("Jenis OOH *", e_jenis_opts, index=e_jenis_idx)

                with col2:
                    e_ukuran = st.text_input("Ukuran *", value=clean_str(row_edit["Ukuran"]))
                    e_jumlah_muka = st.number_input("Jumlah Muka *", min_value=1, max_value=10, value=int(row_edit["Jumlah Muka"]) if pd.notna(row_edit["Jumlah Muka"]) else 1)

                    cur_fl_bl = clean_str(row_edit["FL / BL"], "-")
                    e_fl_idx = fl_bl_opts.index(cur_fl_bl) if cur_fl_bl in fl_bl_opts else 2
                    e_fl_bl = st.selectbox("FL / BL", fl_bl_opts, index=e_fl_idx)

                    e_lokasi = st.text_area("Alamat / Lokasi Titik *", value=clean_str(row_edit["Lokasi"]))
                    e_longitude = st.number_input("Longitude", value=float(row_edit["Longitude"]) if pd.notna(row_edit["Longitude"]) else 0.0, format="%.6f")
                    e_latitude = st.number_input("Latitude", value=float(row_edit["Latitude"]) if pd.notna(row_edit["Latitude"]) else 0.0, format="%.6f")

                with col3:
                    val_tgl_awal = row_edit["Periode Kontak Awal"].date() if pd.notna(row_edit["Periode Kontak Awal"]) else date(2026, 1, 1)
                    val_tgl_akhir = row_edit["Periode Kontak Akhir"].date() if pd.notna(row_edit["Periode Kontak Akhir"]) else date(2026, 12, 31)
                    e_tgl_awal = st.date_input("Periode Kontrak Awal *", value=val_tgl_awal)
                    e_tgl_akhir = st.date_input("Periode Kontrak Akhir *", value=val_tgl_akhir)
                    e_nominal_kontrak = st.number_input("Nominal Kontrak Total (Rp) *", min_value=0.0, step=1000000.0, value=float(row_edit["Nominal Kontrak"]) if pd.notna(row_edit["Nominal Kontrak"]) else 0.0)

                    cur_bm1 = clean_str(row_edit["Master Brand Muka 1"])
                    e_bm1_opts = brand_choices if cur_bm1 in brand_choices or not cur_bm1 else [cur_bm1] + brand_choices
                    e_bm1_idx = e_bm1_opts.index(cur_bm1) if cur_bm1 in e_bm1_opts else 0
                    e_brand_m1 = st.selectbox("Master Brand Muka 1 *", e_bm1_opts, index=e_bm1_idx)
                    e_versi_m1 = st.text_input("Versi Muka 1", value=clean_str(row_edit["Versi Muka 1"]))

                    m2_all_opts = ["-"] + brand_choices
                    cur_bm2 = clean_str(row_edit["Master Brand Muka 2"], "-")
                    if cur_bm2 not in m2_all_opts:
                        m2_all_opts = ["-", cur_bm2] + brand_choices
                    e_bm2_idx = m2_all_opts.index(cur_bm2) if cur_bm2 in m2_all_opts else 0
                    e_brand_m2 = st.selectbox("Master Brand Muka 2", m2_all_opts, index=e_bm2_idx)
                    e_versi_m2 = st.text_input("Versi Muka 2", value=clean_str(row_edit["Versi Muka 2"]))

                    ev_all_opts = ["-"] + brand_choices
                    cur_bev = clean_str(row_edit["Master Brand Event"], "-")
                    if cur_bev not in ev_all_opts:
                        ev_all_opts = ["-", cur_bev] + brand_choices
                    e_bev_idx = ev_all_opts.index(cur_bev) if cur_bev in ev_all_opts else 0
                    e_brand_event = st.selectbox("Master Brand Event", ev_all_opts, index=e_bev_idx)
                    e_versi_event = st.text_input("Versi event", value=clean_str(row_edit["Versi event"]))

                col_btn1, col_btn2 = st.columns([3, 1])
                with col_btn1:
                    btn_save_edit = st.form_submit_button("💾 Simpan Perubahan Master OOH", type="primary", use_container_width=True)
                with col_btn2:
                    btn_delete_row = st.form_submit_button("🗑️ Hapus Titik OOH Ini", use_container_width=True)

                if btn_save_edit:
                    if not e_id_ooh.strip() or not e_kota.strip() or not e_lokasi.strip():
                        st.error("ID OOH, Kota, dan Lokasi wajib diisi.")
                    else:
                        df_save = df[COLUMNS_MASTER].copy()
                        text_cols = [
                            "Kota", "Zona", "Sektor", "ID OOH", "Nama Vendor", "Jenis OOH",
                            "Ukuran", "FL / BL", "Lokasi", "Master Brand Muka 1", "Master Brand Muka 2",
                            "Versi Muka 1", "Versi Muka 2", "Master Brand Event", "Versi event"
                        ]
                        for c in text_cols:
                            if c in df_save.columns:
                                df_save[c] = df_save[c].astype("object")

                        df_save.at[edit_idx, "ID OOH"] = e_id_ooh.strip()
                        df_save.at[edit_idx, "Nama Vendor"] = e_nama_vendor
                        df_save.at[edit_idx, "Kota"] = e_kota.strip()
                        df_save.at[edit_idx, "Zona"] = e_zona.strip()
                        df_save.at[edit_idx, "Sektor"] = e_sektor.strip()
                        df_save.at[edit_idx, "Jenis OOH"] = e_jenis_ooh
                        df_save.at[edit_idx, "Ukuran"] = e_ukuran.strip()
                        df_save.at[edit_idx, "Jumlah Muka"] = int(e_jumlah_muka)
                        df_save.at[edit_idx, "FL / BL"] = None if e_fl_bl == "-" else e_fl_bl
                        df_save.at[edit_idx, "Lokasi"] = e_lokasi.strip()
                        df_save.at[edit_idx, "Longitude"] = None if e_longitude == 0.0 else e_longitude
                        df_save.at[edit_idx, "Latitude"] = None if e_latitude == 0.0 else e_latitude
                        df_save.at[edit_idx, "Periode Kontak Awal"] = pd.Timestamp(e_tgl_awal)
                        df_save.at[edit_idx, "Periode Kontak Akhir"] = pd.Timestamp(e_tgl_akhir)
                        df_save.at[edit_idx, "Nominal Kontrak"] = float(e_nominal_kontrak)
                        df_save.at[edit_idx, "Master Brand Muka 1"] = e_brand_m1
                        df_save.at[edit_idx, "Versi Muka 1"] = e_versi_m1.strip() if e_versi_m1.strip() else None
                        df_save.at[edit_idx, "Master Brand Muka 2"] = None if e_brand_m2 == "-" else e_brand_m2
                        df_save.at[edit_idx, "Versi Muka 2"] = e_versi_m2.strip() if e_versi_m2.strip() else None
                        df_save.at[edit_idx, "Master Brand Event"] = None if e_brand_event == "-" else e_brand_event
                        df_save.at[edit_idx, "Versi event"] = e_versi_event.strip() if e_versi_event.strip() else None

                        save_master_data(df_save)
                        st.session_state["email_batch_cleared"] = False
                        st.session_state["notif_ganti_sukses"] = f"✅ Master Data OOH ID {e_id_ooh} berhasil diperbarui!"
                        st.rerun()

                if btn_delete_row:
                    df_after_del = df[COLUMNS_MASTER].drop(index=edit_idx).reset_index(drop=True)
                    save_master_data(df_after_del)
                    st.warning(f"Titik OOH ID {row_edit['ID OOH']} telah dihapus dari Master Data!")
                    st.rerun()

# ==============================================================================
# MENU 3: PENGGANTIAN BRAND & VISUAL
# ==============================================================================
elif menu == "3. Penggantian Brand & Visual":
    st.title("Menu Penggantian Brand & Visual (Materi)")

    if "notif_ganti_sukses" in st.session_state:
        st.success(st.session_state.pop("notif_ganti_sukses"))

    if df.empty:
        st.warning("Belum ada data master OOH.")
    else:
        col_f_kota1, col_f_kota2 = st.columns([1, 2])
        with col_f_kota1:
            list_kota_ganti = ["Semua Kota"] + sorted(df["Kota"].dropna().unique().tolist())
            selected_kota_ganti = st.selectbox("🏙️ Filter Kota untuk Titik OOH:", list_kota_ganti)

        df_ganti_filtered = df.copy()
        if selected_kota_ganti != "Semua Kota":
            df_ganti_filtered = df_ganti_filtered[df_ganti_filtered["Kota"] == selected_kota_ganti]

        if df_ganti_filtered.empty:
            st.warning(f"Tidak ada data OOH untuk Kota '{selected_kota_ganti}'.")
        else:
            df_ganti_filtered["Label_Pilih"] = (
                df_ganti_filtered["ID OOH"].astype(str) 
                + " | Vendor: " + df_ganti_filtered["Nama Vendor"].fillna("-") 
                + " | " + df_ganti_filtered["Kota"] 
                + " - " + df_ganti_filtered["Lokasi"] 
                + " (" + df_ganti_filtered["Jenis OOH"] 
                + " | Ukuran: " + df_ganti_filtered["Ukuran"].fillna("-") + ")"
            )
            
            with col_f_kota2:
                selected_label = st.selectbox("Pilih Titik OOH yang Akan Diganti Materi:", df_ganti_filtered["Label_Pilih"].tolist())
            
            idx = df[df["ID OOH"].astype(str) == str(df_ganti_filtered[df_ganti_filtered["Label_Pilih"] == selected_label]["ID OOH"].iloc[0])].index[0]
            row = df.loc[idx]

            eff_current = get_effective_brand_version(row)
            m1_brand_now = clean_str(eff_current["Brand"], "-")
            m1_versi_now = clean_str(eff_current["Version"], "-")
            m2_brand_now = clean_str(row["Master Brand Muka 2"], "-")
            m2_versi_now = clean_str(row["Versi Muka 2"], "-")
            event_brand_now = clean_str(row.get("Master Brand Event"), "-")
            event_versi_now = clean_str(row.get("Versi event"), "-")

            st.info(
                f"**Nama Vendor:** {clean_str(row['Nama Vendor'], '-')} | "
                f"**Detail Titik:** {row['Jenis OOH']} ({row['Ukuran']}) | **Jumlah Muka:** {row['Jumlah Muka']} | "
                f"**Brand Aktif Saat Ini:** {m1_brand_now} ({m1_versi_now})"
            )

            jenis_pergantian = st.radio(
                "Pilih Jenis Penggantian Visual:",
                [
                    "1. Penggantian Reguler",
                    "2. Event & Penyelesaian",
                    "3. Penggantian Massal",
                ],
                horizontal=True
            )

            promo_brand_keys = {}
            promo_version_keys = {}
            if (
                "1. Penggantian Reguler" in jenis_pergantian
                or "3. Penggantian Massal" in jenis_pergantian
            ):
                promo_mode_key = "regular" if "1. Penggantian Reguler" in jenis_pergantian else "massal"
                face_defaults = {
                    "m1": (
                        m1_brand_now if promo_mode_key == "regular" else replacement_brand_choices[0],
                        m1_versi_now if promo_mode_key == "regular" and m1_versi_now != "-" else "",
                    ),
                    "m2": (
                        m2_brand_now if promo_mode_key == "regular" else "-",
                        m2_versi_now if promo_mode_key == "regular" and m2_versi_now != "-" else "",
                    ),
                }

                def format_promo_material_option(material_index):
                    if material_index is None:
                        return "Tidak menggunakan materi promosi"
                    material = df_promo_materials.iloc[material_index]
                    return (
                        f"{material['Material']} | {material['Brand']} | "
                        f"{material['Version']} | Stok: {material['Total']} {material['UOM']}"
                    )

                def apply_promo_material_selection(
                    selection_key,
                    brand_key,
                    version_key,
                    default_brand,
                    default_version,
                ):
                    material_index = st.session_state[selection_key]
                    if material_index is None:
                        st.session_state[brand_key] = default_brand
                        st.session_state[version_key] = default_version
                        return

                    material = df_promo_materials.iloc[material_index]
                    st.session_state[brand_key] = clean_str(material["Brand"], default_brand)
                    st.session_state[version_key] = clean_str(material["Version"], "")

                promo_columns = st.columns(2)
                for face, face_label, container in zip(
                    ("m1", "m2"),
                    ("Muka 1", "Muka 2"),
                    promo_columns,
                ):
                    default_brand, default_version = face_defaults[face]
                    selection_key = f"promo_material_{promo_mode_key}_{face}_{row['ID OOH']}"
                    brand_key = f"promo_brand_{promo_mode_key}_{face}_{row['ID OOH']}"
                    version_key = f"promo_version_{promo_mode_key}_{face}_{row['ID OOH']}"
                    promo_brand_keys[face] = brand_key
                    promo_version_keys[face] = version_key

                    if brand_key not in st.session_state:
                        st.session_state[brand_key] = default_brand
                    if version_key not in st.session_state:
                        st.session_state[version_key] = default_version

                    with container:
                        st.selectbox(
                            f"Isi Brand dan Versi {face_label} dari Materi Promosi (opsional)",
                            options=[None] + list(range(len(df_promo_materials))),
                            format_func=format_promo_material_option,
                            key=selection_key,
                            on_change=apply_promo_material_selection,
                            args=(
                                selection_key,
                                brand_key,
                                version_key,
                                default_brand,
                                default_version,
                            ),
                        )

            with st.form("form_ganti_visual"):
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    tgl_rencana_order = st.date_input("Tanggal Rencana Order (Opsional)", value=date.today())
                with col_t2:
                    tgl_rencana_ganti = st.date_input("Tanggal Rencana Ganti (Opsional)", value=date.today())

                st.divider()

                if "1. Penggantian Reguler" in jenis_pergantian:
                    st.markdown("#### Form Penggantian Master Brand / Visual Reguler (Muka 1 & Muka 2)")
                    
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        st.markdown("##### 📌 Muka 1")
                        st.text_input("Master Brand Muka 1 Lama (Saat Ini)", value=m1_brand_now, disabled=True)
                        m1_brand_options = sorted(set(replacement_brand_choices + [m1_brand_now]))
                        if st.session_state[promo_brand_keys["m1"]] not in m1_brand_options:
                            st.session_state[promo_brand_keys["m1"]] = m1_brand_now
                        new_brand_1 = st.selectbox(
                            "Master Brand Muka 1 Baru",
                            m1_brand_options,
                            key=promo_brand_keys["m1"],
                        )
                        
                        st.text_input("Versi / Visual Muka 1 Lama (Saat Ini)", value=m1_versi_now, disabled=True)
                        new_versi_1 = st.text_input(
                            "Versi / Visual Muka 1 Baru",
                            key=promo_version_keys["m1"],
                        )

                    with col_m2:
                        st.markdown("##### 📌 Muka 2")
                        st.text_input("Master Brand Muka 2 Lama (Saat Ini)", value=m2_brand_now, disabled=True)
                        m2_choices = sorted(set(["-"] + replacement_brand_choices + [m2_brand_now]))
                        if st.session_state[promo_brand_keys["m2"]] not in m2_choices:
                            st.session_state[promo_brand_keys["m2"]] = m2_brand_now
                        new_brand_2 = st.selectbox(
                            "Master Brand Muka 2 Baru",
                            m2_choices,
                            key=promo_brand_keys["m2"],
                        )
                        
                        st.text_input("Versi / Visual Muka 2 Lama (Saat Ini)", value=m2_versi_now, disabled=True)
                        new_versi_2 = st.text_input(
                            "Versi / Visual Muka 2 Baru",
                            key=promo_version_keys["m2"],
                        )
                    
                    mode_record = "Reguler"

                elif "2. Event & Penyelesaian" in jenis_pergantian:
                    jenis_event = st.radio(
                        "Pilih Tindakan Event:",
                        [
                            "Pasang / Ganti Brand Event",
                            "Selesaikan Event",
                        ],
                        horizontal=True,
                        key="jenis_tindakan_event"
                    )

                    if jenis_event == "Pasang / Ganti Brand Event":
                        st.markdown("#### Pasang atau Ganti Brand Event (Temporary)")

                        st.markdown("##### 📌 Muka 1 (Event)")
                        st.text_input("Master Brand Muka 1 Lama (Saat Ini)", value=m1_brand_now, disabled=True, key="ev_m1_lama")
                        new_brand_1 = st.text_input("Master Brand Muka 1 Event Baru", value="", placeholder="Ketik nama brand event baru...", key="ev_b1_baru")

                        st.text_input("Versi Muka 1 Lama (Saat Ini)", value=m1_versi_now, disabled=True, key="ev_v1_lama")
                        new_versi_1 = st.text_input("Versi Muka 1 Event Baru", value="", placeholder="Ketik versi event baru...", key="ev_v1_baru")

                        new_brand_2 = "-"
                        new_versi_2 = "-"
                        mode_record = "Event"
                    else:
                        st.markdown("#### Selesaikan Event dan Kembali ke Visual Reguler")
                        st.info(
                            f"Event yang sedang terpasang: **{event_brand_now}** "
                            f"— Versi: **{event_versi_now}**"
                        )
                        st.caption(
                            "Brand dan versi reguler di bawah diambil dari data reguler "
                            "yang tersimpan sebelum event."
                        )

                        default_reg_brand = clean_str(row.get("Master Brand Muka 1"), "-")
                        default_reg_versi = clean_str(row.get("Versi Muka 1"), "-")

                        st.markdown("##### 📌 Muka 1 (Kembali ke Reguler)")

                        new_brand_1 = st.text_input(
                            "Master Brand Reguler Baru (Pengganti Event)",
                            value=default_reg_brand if default_reg_brand != "-" else "",
                            placeholder="Ketik master brand reguler..."
                        )

                        new_versi_1 = st.text_input(
                            "Versi / Visual Reguler Baru",
                            value=default_reg_versi if default_reg_versi != "-" else "",
                            placeholder="Ketik versi reguler..."
                        )

                        new_brand_2 = "-"
                        new_versi_2 = "-"
                        mode_record = "Selesai Event"
                    
                else:
                    st.markdown("#### Form Penggantian Visual Massal (Semua Titik Terpilih)")
                    selected_targets = st.multiselect(
                        "Pilih beberapa titik OOH yang ingin diganti secara massal:",
                        df_ganti_filtered["Label_Pilih"].tolist(),
                        default=[selected_label],
                        key="bulk_visual_targets"
                    )
                    if not selected_targets:
                        st.warning("Pilih minimal satu titik OOH.")
                    col_mass_1, col_mass_2 = st.columns(2)
                    with col_mass_1:
                        mass_brand_options = sorted(set(replacement_brand_choices + [m1_brand_now]))
                        if st.session_state[promo_brand_keys["m1"]] not in mass_brand_options:
                            st.session_state[promo_brand_keys["m1"]] = replacement_brand_choices[0]
                        mass_brand_1 = st.selectbox(
                            "Master Brand Muka 1 Baru",
                            mass_brand_options,
                            key=promo_brand_keys["m1"],
                        )
                        mass_versi_1 = st.text_input(
                            "Versi / Visual Muka 1 Baru",
                            key=promo_version_keys["m1"],
                        )
                    with col_mass_2:
                        mass_brand_options_2 = sorted(set(["-"] + replacement_brand_choices + [m2_brand_now]))
                        if st.session_state[promo_brand_keys["m2"]] not in mass_brand_options_2:
                            st.session_state[promo_brand_keys["m2"]] = "-"
                        mass_brand_2 = st.selectbox(
                            "Master Brand Muka 2 Baru",
                            mass_brand_options_2,
                            key=promo_brand_keys["m2"],
                        )
                        mass_versi_2 = st.text_input(
                            "Versi / Visual Muka 2 Baru",
                            key=promo_version_keys["m2"],
                        )
                    mass_note = st.text_input("Catatan / Vendor / PIC", value="Penggantian masal visual")
                    mass_confirm = st.checkbox("Saya yakin ingin mengganti semua titik terpilih dengan nilai yang sama.")
                    new_brand_1 = mass_brand_1
                    new_versi_1 = mass_versi_1
                    new_brand_2 = mass_brand_2
                    new_versi_2 = mass_versi_2
                    mode_record = "Massal"

                st.divider()
                keterangan = st.text_input("Catatan / Vendor / PIC Pemasangan", placeholder="Contoh: Persiapan event / ganti materi reguler baru")

                btn_update = st.form_submit_button("Simpan Pergantian Brand, Visual & Event", type="primary")
                if btn_update:
                    df_save = df[COLUMNS_MASTER].copy()
                    text_cols_to_fix = [
                        "Master Brand Muka 1", "Master Brand Muka 2", 
                        "Versi Muka 1", "Versi Muka 2", 
                        "Master Brand Event", "Versi event"
                    ]
                    for col in text_cols_to_fix:
                        if col in df_save.columns:
                            df_save[col] = df_save[col].astype("object")

                    if mode_record == "Massal":
                        if not selected_targets:
                            st.error("Silakan pilih minimal satu titik untuk pergantian massal.")
                        elif not mass_confirm:
                            st.error("Centang konfirmasi sebelum menyimpan pergantian massal.")
                        else:
                            target_indexes = [df[df["ID OOH"].astype(str) == str(df_ganti_filtered[df_ganti_filtered["Label_Pilih"] == t]["ID OOH"].iloc[0])].index[0] for t in selected_targets]
                            for target_idx in target_indexes:
                                df_save.at[target_idx, "Master Brand Muka 1"] = None if new_brand_1 == "-" else new_brand_1
                                df_save.at[target_idx, "Versi Muka 1"] = new_versi_1.strip() if new_versi_1.strip() else None
                                df_save.at[target_idx, "Master Brand Muka 2"] = None if new_brand_2 == "-" else new_brand_2
                                df_save.at[target_idx, "Versi Muka 2"] = new_versi_2.strip() if new_versi_2.strip() else None
                                df_save.at[target_idx, "Master Brand Event"] = None
                                df_save.at[target_idx, "Versi event"] = None
                                row_target = df.loc[target_idx]
                                log_entry = {
                                    "Tanggal Update": now_wib().strftime("%d-%m-%Y %H:%M"),
                                    "ID OOH": row_target["ID OOH"],
                                    "Kota": row_target["Kota"],
                                    "Lokasi": row_target["Lokasi"],
                                    "Nama Vendor": row_target["Nama Vendor"],
                                    "Tgl Rencana Order": tgl_rencana_order.strftime("%d-%m-%Y"),
                                    "Tgl Rencana Ganti": tgl_rencana_ganti.strftime("%d-%m-%Y"),
                                    "Brand Muka 1 Lama": clean_str(row_target["Master Brand Muka 1"], None),
                                    "Brand Muka 1 Baru": None if new_brand_1 == "-" else new_brand_1,
                                    "Versi Muka 1 Lama": clean_str(row_target["Versi Muka 1"], None),
                                    "Versi Muka 1 Baru": new_versi_1.strip() if new_versi_1.strip() else None,
                                    "Brand Muka 2 Lama": clean_str(row_target["Master Brand Muka 2"], None),
                                    "Brand Muka 2 Baru": None if new_brand_2 == "-" else new_brand_2,
                                    "Versi Muka 2 Lama": clean_str(row_target["Versi Muka 2"], None),
                                    "Versi Muka 2 Baru": new_versi_2.strip() if new_versi_2.strip() else None,
                                    "Brand Event Lama": None,
                                    "Brand Event Baru": None,
                                    "Versi Event Lama": None,
                                    "Versi Event Baru": None,
                                    "Keterangan / PIC": f"[Massal] {mass_note.strip()}",
                                }
                                append_log_pergantian(log_entry)
                            save_master_data(df_save)
                            st.session_state["email_batch_cleared"] = False
                            st.session_state["notif_ganti_sukses"] = f"✅ Pergantian massal visual berhasil diterapkan ke {len(target_indexes)} titik OOH."
                            st.rerun()
                    else:
                        if mode_record == "Reguler":
                            df_save.at[idx, "Master Brand Muka 1"] = None if new_brand_1 == "-" else new_brand_1
                            df_save.at[idx, "Versi Muka 1"] = new_versi_1.strip() if new_versi_1.strip() else None
                            df_save.at[idx, "Master Brand Muka 2"] = None if new_brand_2 == "-" else new_brand_2
                            df_save.at[idx, "Versi Muka 2"] = new_versi_2.strip() if new_versi_2.strip() else None
                            df_save.at[idx, "Master Brand Event"] = None
                            df_save.at[idx, "Versi event"] = None
                            
                            log_entry = {
                                "Tanggal Update": now_wib().strftime("%d-%m-%Y %H:%M"),
                                "ID OOH": row["ID OOH"], "Kota": row["Kota"], "Lokasi": row["Lokasi"], "Nama Vendor": row["Nama Vendor"],
                                "Tgl Rencana Order": tgl_rencana_order.strftime("%d-%m-%Y"), "Tgl Rencana Ganti": tgl_rencana_ganti.strftime("%d-%m-%Y"),
                                "Brand Muka 1 Lama": m1_brand_now if m1_brand_now != "-" else None,
                                "Brand Muka 1 Baru": None if new_brand_1 == "-" else new_brand_1,
                                "Versi Muka 1 Lama": m1_versi_now if m1_versi_now != "-" else None,
                                "Versi Muka 1 Baru": new_versi_1.strip() if new_versi_1.strip() else None,
                                "Brand Muka 2 Lama": m2_brand_now if m2_brand_now != "-" else None,
                                "Brand Muka 2 Baru": None if new_brand_2 == "-" else new_brand_2,
                                "Versi Muka 2 Lama": m2_versi_now if m2_versi_now != "-" else None,
                                "Versi Muka 2 Baru": new_versi_2.strip() if new_versi_2.strip() else None,
                                "Brand Event Lama": None, "Brand Event Baru": None, "Versi Event Lama": None, "Versi Event Baru": None,
                                "Keterangan / PIC": f"[Reguler] {keterangan.strip()}",
                            }
                        elif mode_record == "Event":
                            reg_brand_lama = clean_str(row.get("Master Brand Muka 1"), "-")
                            reg_versi_lama = clean_str(row.get("Versi Muka 1"), "-")

                            df_save.at[idx, "Master Brand Event"] = None if not new_brand_1.strip() else new_brand_1.strip()
                            df_save.at[idx, "Versi event"] = new_versi_1.strip() if new_versi_1.strip() else None
                            
                            log_entry = {
                                "Tanggal Update": now_wib().strftime("%d-%m-%Y %H:%M"),
                                "ID OOH": row["ID OOH"], "Kota": row["Kota"], "Lokasi": row["Lokasi"], "Nama Vendor": row["Nama Vendor"],
                                "Tgl Rencana Order": tgl_rencana_order.strftime("%d-%m-%Y"), "Tgl Rencana Ganti": tgl_rencana_ganti.strftime("%d-%m-%Y"),
                                "Brand Muka 1 Lama": reg_brand_lama if reg_brand_lama != "-" else None, 
                                "Brand Muka 1 Baru": None,
                                "Versi Muka 1 Lama": reg_versi_lama if reg_versi_lama != "-" else None, 
                                "Versi Muka 1 Baru": None,
                                "Brand Muka 2 Lama": None, "Brand Muka 2 Baru": None, "Versi Muka 2 Lama": None, "Versi Muka 2 Baru": None,
                                "Brand Event Lama": event_brand_now if event_brand_now != "-" else None,
                                "Brand Event Baru": None if not new_brand_1.strip() else new_brand_1.strip(),
                                "Versi Event Lama": event_versi_now if event_versi_now != "-" else None,
                                "Versi Event Baru": new_versi_1.strip() if new_versi_1.strip() else None,
                                "Keterangan / PIC": f"[Event] {keterangan.strip()}",
                            }
                        else:  # Selesai Event ke Reguler
                            df_save.at[idx, "Master Brand Event"] = None
                            df_save.at[idx, "Versi event"] = None
                            df_save.at[idx, "Master Brand Muka 1"] = None if new_brand_1 == "-" else new_brand_1
                            df_save.at[idx, "Versi Muka 1"] = new_versi_1.strip() if new_versi_1.strip() else None
                            
                            log_entry = {
                                "Tanggal Update": now_wib().strftime("%d-%m-%Y %H:%M"),
                                "ID OOH": row["ID OOH"], "Kota": row["Kota"], "Lokasi": row["Lokasi"], "Nama Vendor": row["Nama Vendor"],
                                "Tgl Rencana Order": tgl_rencana_order.strftime("%d-%m-%Y"), "Tgl Rencana Ganti": tgl_rencana_ganti.strftime("%d-%m-%Y"),
                                "Brand Muka 1 Lama": None,
                                "Brand Muka 1 Baru": None if new_brand_1 == "-" else new_brand_1,
                                "Versi Muka 1 Lama": None,
                                "Versi Muka 1 Baru": new_versi_1.strip() if new_versi_1.strip() else None,
                                "Brand Muka 2 Lama": None, "Brand Muka 2 Baru": None, "Versi Muka 2 Lama": None, "Versi Muka 2 Baru": None,
                                "Brand Event Lama": event_brand_now if event_brand_now != "-" else None,
                                "Brand Event Baru": None,
                                "Versi Event Lama": event_versi_now if event_versi_now != "-" else None,
                                "Versi Event Baru": None,
                                "Keterangan / PIC": f"[Selesai Event] {keterangan.strip()}",
                            }

                        save_master_data(df_save)
                        append_log_pergantian(log_entry)
                        st.session_state["email_batch_cleared"] = False
                        st.session_state["notif_ganti_sukses"] = f"✅ Pergantian material OOH ID {row['ID OOH']} ({mode_record}) berhasil dicatat & Tabel Monitoring Penayangan OOH telah diperbarui!"
                        st.rerun()

        st.divider()
        st.subheader("📧 Data Penggantian Visual OOH (Siap Kirim ke Vendor via Email)")

        if "email_batch_cleared" not in st.session_state:
            st.session_state["email_batch_cleared"] = False

        df_log_history = load_log_data()
        if "ID OOH" in df_log_history.columns:
            history_ids = df_log_history["ID OOH"].astype("string").str.strip()
            df_log_history = df_log_history[
                history_ids.notna()
                & ~history_ids.str.lower().isin(["", "nan", "none", "<na>"])
            ].copy()

        df_log_source = df_log_history.copy()
        if st.session_state.get("email_batch_cleared", False):
            df_log_source = pd.DataFrame(columns=df_log_source.columns)

        col_hdr1, col_hdr2 = st.columns(2)
        with col_hdr1:
            default_tgl_pasang = now_wib().strftime("%d/%m/%Y")
            info_pasang_txt = st.text_input("Info Pasang (Tanggal / Keterangan):", value=default_tgl_pasang)
            catatan_pasang_txt = st.text_input("Judul / Catatan Pasang:", value="Penggantian Versi OOH")
        with col_hdr2:
            info_bongkar_txt = st.text_input("Info Bongkar:", value="-")
            catatan_bongkar_txt = st.text_input(
                "Catatan Pengembalian Materi Lama:",
                value="Materi Lama / Lepasan > Harap segera dikembalikan ke Gudang DSO Surabaya Barat (Pak Amin)",
            )
        
        if df_log_source.empty:
            st.info("ℹ️ Belum ada riwayat pergantian materi OOH untuk ditampilkan pada tabel email.")
        else:
            # Membuat dua kolom untuk filter Vendor dan filter Tanggal Rencana Order
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                all_vendors_in_batch = sorted(list({str(v) for v in df_log_source["Nama Vendor"].dropna().unique().tolist()}))
                filter_vendor_opts = ["Semua Vendor"] + all_vendors_in_batch
                selected_vendor_filter = st.selectbox("🔍 Filter Berdasarkan Vendor:", filter_vendor_opts)

            with col_f2:
                # Mengambil daftar tanggal unik dari kolom "Tgl Rencana Order"
                all_order_dates = sorted(list({str(d).split()[0] for d in df_log_source.get("Tgl Rencana Order", pd.Series()).dropna().unique().tolist()}))
                filter_date_opts = ["Semua Tanggal Order"] + all_order_dates
                selected_order_date_filter = st.selectbox("📅 Filter Berdasarkan Tgl Rencana Order:", filter_date_opts)

            rows_formatted = []
            df_log_unique = df_log_source.drop_duplicates(subset=["ID OOH"], keep="first")

            for _, item in df_log_unique.iterrows():
                v_item = str(item.get("Nama Vendor", "-"))
                tgl_order_item = str(item.get("Tgl Rencana Order", "-")).split()[0]

                # Filter berdasarkan Vendor
                if selected_vendor_filter != "Semua Vendor" and v_item != selected_vendor_filter:
                    continue
                
                # Filter berdasarkan Tanggal Rencana Order
                if selected_order_date_filter != "Semua Tanggal Order" and tgl_order_item != selected_order_date_filter:
                    continue

                master_match = df[df["ID OOH"].astype(str) == str(item["ID OOH"])]
                if not master_match.empty:
                    m_row = master_match.iloc[0]
                    zona_val = m_row["Zona"] if pd.notna(m_row["Zona"]) else "-"
                    sektor_val = m_row["Sektor"] if pd.notna(m_row["Sektor"]) else "-"
                    jenis_val = str(m_row["Jenis OOH"]).upper() if pd.notna(m_row["Jenis OOH"]) else "-"
                    ukuran_val = m_row["Ukuran"] if pd.notna(m_row["Ukuran"]) else "-"
                    kat_val = m_row["FL / BL"] if pd.notna(m_row["FL / BL"]) else "-"
                    jml_muka = int(m_row["Jumlah Muka"]) if pd.notna(m_row["Jumlah Muka"]) else 1
                else:
                    zona_val, sektor_val, jenis_val, ukuran_val, kat_val, jml_muka = "-", "-", "-", "-", "-", 1

                ket_str = str(item.get("Keterangan / PIC", ""))

                if "[Event]" in ket_str:
                    brand_lama = clean_str(item.get("Brand Event Lama"), "")
                    if brand_lama in ["", "-"]:
                        brand_lama = clean_str(item.get("Brand Muka 1 Lama"), "-")
                    brand_lama = brand_lama.upper()

                    versi_lama = clean_str(item.get("Versi Event Lama"), "")
                    if versi_lama in ["", "-"]:
                        versi_lama = clean_str(item.get("Versi Muka 1 Lama"), "-")

                    brand_baru = clean_str(item.get("Brand Event Baru"), "-").upper()
                    versi_baru = clean_str(item.get("Versi Event Baru"), "-")
                    ket_lokasi = f"{item.get('Lokasi', '-')} (Event)"

                elif "[Selesai Event]" in ket_str:
                    brand_lama = clean_str(item.get("Brand Event Lama"), "")
                    if brand_lama in ["", "-"]:
                        brand_lama = clean_str(item.get("Brand Muka 1 Lama"), "-")
                    brand_lama = brand_lama.upper()

                    versi_lama = clean_str(item.get("Versi Event Lama"), "")
                    if versi_lama in ["", "-"]:
                        versi_lama = clean_str(item.get("Versi Muka 1 Lama"), "-")

                    brand_baru = clean_str(item.get("Brand Muka 1 Baru"), "-").upper()
                    versi_baru = clean_str(item.get("Versi Muka 1 Baru"), "-")
                    ket_lokasi = f"{item.get('Lokasi', '-')} (Selesai Event)"

                else:
                    brand_lama = clean_str(item.get("Brand Muka 1 Lama"), "-").upper()
                    versi_lama = clean_str(item.get("Versi Muka 1 Lama"), "-")
                    brand_baru = clean_str(item.get("Brand Muka 1 Baru"), "-").upper()
                    versi_baru = clean_str(item.get("Versi Muka 1 Baru"), "-")
                    ket_lokasi = str(item.get("Lokasi", "-"))

                rows_formatted.append({
                    "Zona": zona_val,
                    "Sektor": sektor_val,
                    "Jenis OOH": jenis_val,
                    "Ukuran": ukuran_val,
                    "Kat.": kat_val,
                    "Jml Titik": 1,
                    "Jml Muka / Titik": 1,
                    "Jml Muka Total": jml_muka,
                    "VENDOR": v_item.upper(),
                    "Alamat OOH": ket_lokasi,
                    "Brand": brand_lama,
                    "Versi Lama": versi_lama,
                    "Brand ": brand_baru,
                    "Versi yang Baru / Penggantian": versi_baru,
                })
            if not rows_formatted:
                st.info("ℹ️ Tidak ada data penggantian visual yang valid untuk filter vendor & tanggal rencana order ini.")
            else:
                df_visual_table = pd.DataFrame(rows_formatted)
                st.dataframe(df_visual_table, use_container_width=True, hide_index=True)

                png_bytes = generate_ooh_replacement_png(
                    df_table=df_visual_table,
                    info_pasang=info_pasang_txt,
                    info_bongkar=info_bongkar_txt,
                    catatan_pasang=catatan_pasang_txt,
                    catatan_bongkar=catatan_bongkar_txt,
                )

                st.image(png_bytes, caption="Preview Hasil Gambar Tabel (.PNG)", use_container_width=True)

                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.download_button(
                        label="📥 Download Gambar Tabel (.PNG)",
                        data=png_bytes,
                        file_name=f"Penggantian_Visual_OOH_{selected_vendor_filter.replace(' ', '_')}_{now_wib().strftime('%Y%m%d_%H%M')}.png",
                        mime="image/png",
                        type="primary",
                        use_container_width=True,
                    )

                with col_d2:
                    if selected_vendor_filter != "Semua Vendor":
                        target_vendor = selected_vendor_filter
                    elif all_vendors_in_batch:
                        target_vendor = all_vendors_in_batch[0]
                    else:
                        target_vendor = None

                    if target_vendor:
                        v_email_row = df_vendor_master[
                            df_vendor_master["Nama Vendor"].astype(str).str.lower()
                            == target_vendor.lower()
                        ]
                        to_email = (
                            v_email_row["Email Vendor"].values[0]
                            if not v_email_row.empty
                            else ""
                        )

                        cc_emails = (
                            "; ".join(
                                df_pejabat_master["CC Email"].dropna().astype(str).tolist()
                            )
                            if not df_pejabat_master.empty
                            else ""
                        )
                        email_subject = (
                            f"Penggantian Visual OOH - {info_pasang_txt} "
                            f"({target_vendor})"
                        )
                        email_body = (
                            f"Dear {target_vendor},\n\n"
                            "Berikut penggantian visual OOH:\n\n"
                            "Regards,\n\n"
                            "Eka Sulawestara"
                        )
                        mailto_url = (
                            f"mailto:{urllib.parse.quote(to_email)}"
                            f"?cc={urllib.parse.quote(cc_emails)}"
                            f"&subject={urllib.parse.quote(email_subject)}"
                            f"&body={urllib.parse.quote(email_body)}"
                        )

                        st.link_button(
                            label=f"✉️ Buka Draft Email (TO: {to_email})",
                            url=mailto_url,
                            use_container_width=True,
                        )
                    else:
                        st.warning(
                            "Draft email tidak dapat dibuat karena nama vendor "
                            "belum tercatat pada riwayat."
                        )

                    st.write("")
                    if st.button(
                        "🗑️ Reset / Kosongkan Antrean Email Ini",
                        use_container_width=True,
                        type="secondary",
                        key="btn_reset_antrean_email",
                    ):
                        st.session_state["email_batch_cleared"] = True
                        st.success("✅ Antrean kirim email berhasil dikosongkan!")
                        st.rerun()

        st.divider()
        with st.expander("📜 Riwayat Lengkap Penggantian Visual OOH", expanded=False):
            if df_log_history.empty:
                st.info("Belum ada riwayat pergantian visual OOH.")
            else:
                history_columns = [
                    "Tanggal Update", "ID OOH", "Kota", "Lokasi", "Nama Vendor",
                    "Tgl Rencana Order", "Tgl Rencana Ganti",
                    "Brand Muka 1 Lama", "Brand Muka 1 Baru",
                    "Versi Muka 1 Lama", "Versi Muka 1 Baru",
                    "Brand Muka 2 Lama", "Brand Muka 2 Baru",
                    "Versi Muka 2 Lama", "Versi Muka 2 Baru",
                    "Brand Event Lama", "Brand Event Baru",
                    "Versi Event Lama", "Versi Event Baru", "Keterangan / PIC",
                ]
                visible_history_columns = [
                    column for column in history_columns if column in df_log_history.columns
                ]
                visible_history_columns.extend(
                    column for column in df_log_history.columns
                    if column not in visible_history_columns
                )
                st.dataframe(
                    df_log_history[visible_history_columns],
                    use_container_width=True,
                    hide_index=True,
                )

# ==============================================================================
# MENU 4: REPORT KONTRAK & WARNING
# ==============================================================================
elif menu == "4. Report Kontrak & Warning":
    st.title("Report Jangka Waktu Kontrak & Warning")

    report_filter_columns = [
        ("Jenis OOH", "Filter Jenis OOH"),
        ("Kota", "Filter Kota"),
        ("Zona", "Filter Zona"),
        ("Sektor", "Filter Sektor"),
    ]
    report_filters = {}
    filter_containers = st.columns(len(report_filter_columns))
    for (column, label), container in zip(report_filter_columns, filter_containers):
        options = ["Semua"] + sorted(df[column].dropna().astype(str).unique().tolist())
        with container:
            report_filters[column] = st.selectbox(
                label,
                options,
                key=f"report_filter_{column}",
            )

    df_rep = df.copy()
    for column, selected_value in report_filters.items():
        if selected_value != "Semua":
            df_rep = df_rep[df_rep[column].astype(str) == selected_value]

    columns_through_location = list(df_rep.columns[:df_rep.columns.get_loc("Lokasi") + 1])
    brand_columns = [
        "Mother Brand Muka 1",
        "Mother Brand Muka 2",
        "Master Brand Muka 1",
        "Versi Muka 1",
        "Master Brand Muka 2",
        "Versi Muka 2",
        "Master Brand Event",
        "Versi event",
    ]
    report_columns = columns_through_location + [
        column for column in brand_columns
        if column in df_rep.columns and column not in columns_through_location
    ]
    report_columns.extend(column for column in df_rep.columns if column not in report_columns)
    df_rep = df_rep[report_columns].rename(columns={"Versi event": "Versi Event"})

    st.dataframe(df_rep, use_container_width=True, hide_index=True)
    st.download_button("Download Report (.xlsx)", data=to_excel_bytes(df_rep), file_name="Report_OOH.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==============================================================================
# MENU 5: Pengaturan MASTER (VENDOR, VISUAL & PEJABAT)
# ==============================================================================
elif menu == "5. Pengaturan Master (Vendor, Visual & Pejabat)":
    st.title("⚙️ Pengaturan Master Data (Vendor, Visual OOH & Email Pejabat)")
    
    # Memuat data terbaru dari file Excel
    df_vendor_master, df_visual_master, df_pejabat_master = load_extra_masters()

    t_v, t_vis, t_p = st.tabs(["Master Vendor & Email", "Master Visual OOH (Brand & Versi)", "Master Email Pejabat (CC)"])

    with t_v:
        st.subheader("Daftar Email Vendor")
        edited_vendor = st.data_editor(df_vendor_master, num_rows="dynamic", use_container_width=True, key="editor_vendor")
        if st.button("Simpan Perubahan Master Vendor", type="primary"):
            save_extra_masters(edited_vendor, df_visual_master, df_pejabat_master)
            st.success("Master Vendor berhasil disimpan ke file Excel!")
            st.rerun()

    with t_vis:
        st.subheader("Daftar Brand & Versi Visual OOH")
        edited_visual = st.data_editor(df_visual_master, num_rows="dynamic", use_container_width=True, key="editor_visual")
        if st.button("Simpan Perubahan Master Visual", type="primary"):
            save_extra_masters(df_vendor_master, edited_visual, df_pejabat_master)
            st.success("Master Visual berhasil disimpan ke file Excel!")
            st.rerun()

    with t_p:
        st.subheader("Daftar Email Pejabat (CC)")
        edited_pejabat = st.data_editor(df_pejabat_master, num_rows="dynamic", use_container_width=True, key="editor_pejabat")
        if st.button("Simpan Perubahan Master Pejabat", type="primary"):
            save_extra_masters(df_vendor_master, df_visual_master, edited_pejabat)
            st.success("Master Pejabat berhasil disimpan ke file Excel!")
            st.rerun()

elif menu == "6. Monitoring Visual OOH (Event)":
    st.title("📺 Monitoring Visual OOH Terpasang — Event")
    st.caption("Menampilkan titik OOH yang memiliki brand event aktif.")

    if "Master Brand Event" not in df.columns:
        st.error("Kolom 'Master Brand Event' tidak ditemukan di data master.")
    else:
        brand_event = df["Master Brand Event"].astype("string").str.strip()
        event_mask = (
            brand_event.notna()
            & ~brand_event.str.lower().isin(["", "-", "nan", "none", "<na>"])
        )
        df_event = df.loc[event_mask].copy()

        if df_event.empty:
            st.info("Belum ada visual event yang sedang terpasang.")
        else:
            col1, col2, col3 = st.columns(3)

            with col1:
                kota_opts = sorted(df_event["Kota"].dropna().astype(str).unique())
                selected_kota_event = st.selectbox(
                    "Filter Kota", ["Semua Kota"] + kota_opts
                )

            with col2:
                vendor_opts_event = sorted(
                    df_event["Nama Vendor"].dropna().astype(str).unique()
                )
                selected_vendor_event = st.selectbox(
                    "Filter Vendor", ["Semua Vendor"] + vendor_opts_event
                )

            with col3:
                brand_opts_event = sorted(brand_event.loc[event_mask].dropna().unique())
                selected_brand_event = st.selectbox(
                    "Filter Brand Event", ["Semua Brand"] + brand_opts_event
                )

            if selected_kota_event != "Semua Kota":
                df_event = df_event[
                    df_event["Kota"].astype(str) == selected_kota_event
                ]

            if selected_vendor_event != "Semua Vendor":
                df_event = df_event[
                    df_event["Nama Vendor"].astype(str) == selected_vendor_event
                ]

            if selected_brand_event != "Semua Brand":
                df_event = df_event[
                    df_event["Master Brand Event"].astype("string").str.strip()
                    == selected_brand_event
                ]

            st.metric("Jumlah Titik dengan Event Aktif", f"{len(df_event)} titik")

            columns_to_show = [
                "Kota", "Zona", "Sektor", "ID OOH", "Nama Vendor",
                "Jenis OOH", "Ukuran", "Jumlah Muka", "Lokasi",
                "Master Brand Event", "Versi event", "Status Kontrak",
            ]
            visible_columns = [
                column for column in columns_to_show if column in df_event.columns
            ]

            event_view = df_event[visible_columns].rename(
                columns={
                    "Master Brand Event": "Brand Event Terpasang",
                    "Versi event": "Versi Event Terpasang",
                }
            )

            st.dataframe(event_view, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Unduh daftar event (CSV)",
                data=event_view.to_csv(index=False).encode("utf-8-sig"),
                file_name="monitoring_visual_event_ooh.csv",
                mime="text/csv",
            )

elif menu == "7. List Materi Promosi":
    st.title("List Materi Promosi")
    st.caption(
        "Daftar ini hanya memuat materi dengan nama Vinyl Billboard, Vinyl Baliho, "
        "Vinyl PJU, atau Vinyl Midis."
    )

    with st.expander("Upload Data Materi Promosi (.xlsx)", expanded=False):
        st.caption("Upload akan mengganti seluruh daftar saat ini dengan data yang sesuai.")
        uploaded_promo_file = st.file_uploader(
            "Pilih file Excel",
            type=["xlsx"],
            key="promo_material_upload",
        )
        if st.button("Ganti Data Materi Promosi", key="replace_promo_materials"):
            if uploaded_promo_file is None:
                st.warning("Pilih file Excel terlebih dahulu.")
            else:
                try:
                    uploaded_promo_materials = parse_promo_material_upload(
                        uploaded_promo_file
                    )
                    if uploaded_promo_materials.empty:
                        st.error(
                            "Tidak ditemukan materi Vinyl Billboard, Vinyl Baliho, "
                            "Vinyl PJU, atau Vinyl Midis. Data saat ini tidak diubah."
                        )
                    else:
                        save_promo_materials(uploaded_promo_materials)
                        st.success(
                            f"Data Materi Promosi berhasil diganti dengan "
                            f"{len(uploaded_promo_materials)} baris."
                        )
                        st.rerun()
                except (ValueError, OSError, IndexError, KeyError) as error:
                    st.error(f"Gagal memproses file Excel: {error}")

    if df_promo_materials.empty:
        st.info("Tidak ada materi promosi yang sesuai dengan kategori tersebut.")
    else:
        col_material, col_brand, col_available = st.columns(3)
        material_options = ["Semua Material"] + sorted(
            df_promo_materials["Material"].dropna().astype(str).unique().tolist()
        )
        with col_material:
            selected_material = st.selectbox(
                "Filter Material",
                material_options,
                key="promo_list_material_filter",
            )

        df_promo_list = df_promo_materials.copy()
        if selected_material != "Semua Material":
            df_promo_list = df_promo_list[
                df_promo_list["Material"].astype(str) == selected_material
            ]

        brand_options = ["Semua Brand"] + sorted(
            df_promo_list["Brand"].dropna().astype(str).unique().tolist()
        )
        if st.session_state.get("promo_list_brand_filter") not in brand_options:
            st.session_state["promo_list_brand_filter"] = "Semua Brand"
        with col_brand:
            selected_brand = st.selectbox(
                "Filter Brand",
                brand_options,
                key="promo_list_brand_filter",
            )

        available_values = pd.to_numeric(
            df_promo_materials["Available"], errors="coerce"
        ).fillna(0)
        available_slider_max = max(int(available_values.max()), 1)
        available_filter_key = "promo_list_available_filter"
        current_available_range = st.session_state.get(available_filter_key)
        if current_available_range and current_available_range[1] > available_slider_max:
            st.session_state[available_filter_key] = (0, available_slider_max)
        with col_available:
            available_min, available_max = st.slider(
                "Filter Available",
                min_value=0,
                max_value=available_slider_max,
                value=(0, available_slider_max),
                key=available_filter_key,
            )

        if selected_brand != "Semua Brand":
            df_promo_list = df_promo_list[
                df_promo_list["Brand"].astype(str) == selected_brand
            ]
        filtered_available = pd.to_numeric(
            df_promo_list["Available"], errors="coerce"
        ).fillna(0)
        df_promo_list = df_promo_list[
            filtered_available.between(available_min, available_max)
        ]

        st.metric("Jumlah Materi", len(df_promo_list))
        st.dataframe(df_promo_list, use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Unduh List Materi Promosi (.xlsx)",
            data=to_excel_bytes(df_promo_list),
            file_name="List_Materi_Promosi.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
