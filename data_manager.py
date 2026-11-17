import os
import pandas as pd
from datetime import datetime
import pytz

MASTER_FILE = "data/Master OOH.xlsx"
LOG_FILE = "data/Riwayat Pergantian.xlsx"
VENDOR_FILE = "data/Master Vendor.xlsx"
VISUAL_FILE = "data/Master Visual.xlsx"
PEJABAT_FILE = "data/Master Pejabat.xlsx"
EXCEL_PATH = "data/Master Vendor-Visual OOH-Email Pejabat.xlsx"

COLUMNS_MASTER = [
    "No", "Kota", "Zona", "Sektor", "ID OOH", "Nama Vendor", "Jenis OOH",
    "Ukuran", "Jumlah Muka", "FL / BL", "Lokasi", "Periode Kontak Awal",
    "Periode Kontak Akhir", "Nominal Kontrak", "Longitude", "Latitude",
    "Master Brand Muka 1", "Master Brand Muka 2", "Versi Muka 1", "Versi Muka 2",
    "Master Brand Event", "Versi event"
]

COLUMNS_LOG = [
    "Tanggal Update", "ID OOH", "Kota", "Lokasi", "Nama Vendor",
    "Tgl Rencana Order", "Tgl Rencana Ganti",
    "Brand Muka 1 Lama", "Brand Muka 1 Baru", "Versi Muka 1 Lama", "Versi Muka 1 Baru",
    "Brand Muka 2 Lama", "Brand Muka 2 Baru", "Versi Muka 2 Lama", "Versi Muka 2 Baru",
    "Brand Event Lama", "Brand Event Baru", "Versi Event Lama", "Versi Event Baru",
    "Keterangan / PIC"
]

def now_wib():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def ensure_storage():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(MASTER_FILE):
        df_init = pd.DataFrame(columns=COLUMNS_MASTER)
        df_init.to_excel(MASTER_FILE, index=False)

    if not os.path.exists(LOG_FILE):
        df_init = pd.DataFrame(columns=COLUMNS_LOG)
        df_init.to_excel(LOG_FILE, index=False)

    if not os.path.exists(EXCEL_PATH):
        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
            pd.DataFrame(columns=["Nama Vendor", "Email Vendor"]).to_excel(writer, sheet_name="Master Vendor", index=False)
            pd.DataFrame(columns=["Master Brand", "Versi / Visual"]).to_excel(writer, sheet_name="Master Visual OOH", index=False)
            pd.DataFrame(columns=["CC Email"]).to_excel(writer, sheet_name="Master Email Pejabat", index=False)

def load_master_data() -> pd.DataFrame:
    ensure_storage()
    if not os.path.exists(MASTER_FILE):
        return pd.DataFrame(columns=COLUMNS_MASTER)
    
    df = pd.read_excel(MASTER_FILE)
    df.columns = [str(c).strip() for c in df.columns]
    if "Master Brand Event" not in df.columns and "Master Brand Event " in df.columns:
        df.rename(columns={"Master Brand Event ": "Master Brand Event"}, inplace=True)

    for col in COLUMNS_MASTER:
        if col not in df.columns:
            df[col] = None
            
    df["Periode Kontak Awal"] = pd.to_datetime(df["Periode Kontak Awal"], errors="coerce")
    df["Periode Kontak Akhir"] = pd.to_datetime(df["Periode Kontak Akhir"], errors="coerce")
    
    return enrich_contract_metrics(df)

def save_master_data(df: pd.DataFrame):
    ensure_storage()
    df_to_save = df[COLUMNS_MASTER].copy()
    df_to_save["No"] = range(1, len(df_to_save) + 1)
    df_to_save.to_excel(MASTER_FILE, index=False)

def load_log_data() -> pd.DataFrame:
    ensure_storage()
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=COLUMNS_LOG)
    df = pd.read_excel(LOG_FILE)
    for col in COLUMNS_LOG:
        if col not in df.columns:
            df[col] = None
    return df

def save_log_data(df_log: pd.DataFrame):
    ensure_storage()
    df_log.to_excel(LOG_FILE, index=False)

def append_log_pergantian(log_entry: dict):
    df_log = load_log_data()
    new_row = pd.DataFrame([log_entry])
    df_log = pd.concat([new_row, df_log], ignore_index=True)
    save_log_data(df_log)

def rollback_log_entry(log_row):
    id_ooh = str(log_row.get("ID OOH"))
    df_master = load_master_data()
    
    text_cols = [
        "Master Brand Muka 1", "Master Brand Muka 2", "Versi Muka 1", "Versi Muka 2",
        "Master Brand Event", "Versi event", "Nama Vendor", "Kota", "Lokasi"
    ]
    for c in text_cols:
        if c in df_master.columns:
            df_master[c] = df_master[c].astype("object")

    match_idx = df_master[df_master["ID OOH"].astype(str) == id_ooh].index
    if not match_idx.empty:
        idx = match_idx[0]
        ket = str(log_row.get("Keterangan / PIC", ""))

        if "[Event]" in ket:
            df_master.at[idx, "Master Brand Event"] = log_row.get("Brand Event Lama") if pd.notna(log_row.get("Brand Event Lama")) else None
            df_master.at[idx, "Versi event"] = log_row.get("Versi Event Lama") if pd.notna(log_row.get("Versi Event Lama")) else None
        elif "[Selesai Event]" in ket:
            if pd.notna(log_row.get("Brand Event Lama")):
                df_master.at[idx, "Master Brand Event"] = log_row.get("Brand Event Lama")
            if pd.notna(log_row.get("Versi Event Lama")):
                df_master.at[idx, "Versi event"] = log_row.get("Versi Event Lama")
        else:
            if pd.notna(log_row.get("Brand Muka 1 Lama")):
                df_master.at[idx, "Master Brand Muka 1"] = log_row.get("Brand Muka 1 Lama")
            if pd.notna(log_row.get("Versi Muka 1 Lama")):
                df_master.at[idx, "Versi Muka 1"] = log_row.get("Versi Muka 1 Lama")
            if pd.notna(log_row.get("Brand Muka 2 Lama")):
                df_master.at[idx, "Master Brand Muka 2"] = log_row.get("Brand Muka 2 Lama")
            if pd.notna(log_row.get("Versi Muka 2 Lama")):
                df_master.at[idx, "Versi Muka 2"] = log_row.get("Versi Muka 2 Lama")

        save_master_data(df_master)

def get_effective_brand_version(row) -> dict:
    bev = row.get("Master Brand Event")
    vev = row.get("Versi event")
    if pd.notna(bev) and str(bev).strip() not in ["", "-", "nan", "NONE", "None"]:
        return {"Brand": str(bev).strip(), "Version": str(vev).strip() if pd.notna(vev) else "-"}
    
    bm1 = row.get("Master Brand Muka 1")
    vm1 = row.get("Versi Muka 1")
    return {"Brand": str(bm1).strip() if pd.notna(bm1) else "-", "Version": str(vm1).strip() if pd.notna(vm1) else "-"}

def enrich_contract_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    required_cols = [
        "Durasi (Hari)", "Durasi (Bulan)", "Durasi (Tahun)",
        "Nominal Tahunan", "Sisa Hari", "Status Kontrak"
    ]

    if df.empty:
        for col in required_cols:
            if col not in df.columns:
                df[col] = pd.Series(dtype="object")
        return df

    if "Periode Kontak Awal" not in df.columns:
        df["Periode Kontak Awal"] = pd.NaT
    if "Periode Kontak Akhir" not in df.columns:
        df["Periode Kontak Akhir"] = pd.NaT
    if "Nominal Kontrak" not in df.columns:
        df["Nominal Kontrak"] = 0

    df["Periode Kontak Awal"] = pd.to_datetime(df["Periode Kontak Awal"], errors="coerce").dt.tz_localize(None)
    df["Periode Kontak Akhir"] = pd.to_datetime(df["Periode Kontak Akhir"], errors="coerce").dt.tz_localize(None)

    today = pd.Timestamp(now_wib().date()).tz_localize(None)

    durasi_hari = ((df["Periode Kontak Akhir"] - df["Periode Kontak Awal"]).dt.days.fillna(0) + 1).clip(lower=1)

    df["Durasi (Hari)"] = durasi_hari
    df["Durasi (Bulan)"] = (durasi_hari / 30.4375).round(1)
    df["Durasi (Tahun)"] = (durasi_hari / 365.25).round(2)

    df["Nominal Kontrak"] = pd.to_numeric(df["Nominal Kontrak"], errors="coerce").fillna(0)
    df["Nominal Tahunan"] = (df["Nominal Kontrak"] / (durasi_hari / 365.0)).round(0)
    df["Sisa Hari"] = (df["Periode Kontak Akhir"] - today).dt.days

    def get_status(sisa):
        if pd.isna(sisa):
            return "Tidak Valid"
        elif sisa < 0:
            return "Expired"
        elif sisa <= 30:
            return "Kritis (<= 30 Hari)"
        elif sisa <= 90:
            return "Warning (31-90 Hari)"
        else:
            return "Aktif (> 90 Hari)"

    df["Status Kontrak"] = df["Sisa Hari"].apply(get_status)
    return df

def load_extra_masters():
    """Memuat data master vendor, visual, dan pejabat dari file Excel di folder data."""
    ensure_storage()
    if os.path.exists(EXCEL_PATH):
        try:
            df_v = pd.read_excel(EXCEL_PATH, sheet_name="Master Vendor")
        except Exception:
            df_v = pd.DataFrame(columns=["Nama Vendor", "Email Vendor"])
        
        try:
            df_vis = pd.read_excel(EXCEL_PATH, sheet_name="Master Visual OOH")
        except Exception:
            try:
                df_vis = pd.read_excel(EXCEL_PATH, sheet_name="Master Visual")
            except Exception:
                df_vis = pd.DataFrame(columns=["Master Brand", "Versi / Visual"])
        
        try:
            df_p = pd.read_excel(EXCEL_PATH, sheet_name="Master Email Pejabat")
        except Exception:
            try:
                df_p = pd.read_excel(EXCEL_PATH, sheet_name="Master Pejabat")
            except Exception:
                df_p = pd.DataFrame(columns=["CC Email"])
    else:
        df_v = pd.DataFrame(columns=["Nama Vendor", "Email Vendor"])
        df_vis = pd.DataFrame(columns=["Master Brand", "Versi / Visual"])
        df_p = pd.DataFrame(columns=["CC Email"])
        
    return df_v, df_vis, df_p

def save_extra_masters(df_v, df_vis, df_p):
    """Menyimpan kembali perubahan master data ke file Excel dengan multi-sheet."""
    ensure_storage()
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        df_v.to_excel(writer, sheet_name="Master Vendor", index=False)
        df_vis.to_excel(writer, sheet_name="Master Visual OOH", index=False)
        df_p.to_excel(writer, sheet_name="Master Email Pejabat", index=False)
