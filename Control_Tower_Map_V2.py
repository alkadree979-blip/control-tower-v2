import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely import wkt
import folium
from streamlit_folium import st_folium
import numpy as np

# =========================
# CONFIG
# =========================
st.set_page_config(layout="wide")
st.title("🧠 AI Control Tower v4.1 (Stable)")

# =========================
# SAFE WKT
# =========================
def safe_wkt(x):
    try:
        if pd.isna(x):
            return None
        return wkt.loads(x)
    except:
        return None

# =========================
# LOAD DATA
# =========================
@st.cache_data
def load_data():
    path = r"C:\Users\anas.mohammed\Downloads\AWB Data.xlsx"

    df = pd.read_excel(path, dtype=str)
    df.columns = df.columns.str.strip().str.lower()

    # FIX DATE (from your column)
    if "delivery_sheet_created_date" in df.columns:
        df["date"] = pd.to_datetime(df["delivery_sheet_created_date"], errors="coerce")

    # geometry
    df["geometry"] = df["polygon"].apply(safe_wkt)
    df = df[df["geometry"].notnull()]

    return gpd.GeoDataFrame(df, geometry="geometry")

gdf = load_data()

if gdf.empty:
    st.error("No data loaded")
    st.stop()

st.success(f"Loaded {len(gdf)} records")

# =========================
# FILTERS
# =========================
st.sidebar.header("Filters")

# Region
regions = ["All"] + sorted(gdf["2gis region"].dropna().unique())
selected_region = st.sidebar.selectbox("Region", regions)

# Courier
if "courier_id" in gdf.columns:
    couriers = ["All"] + sorted(gdf["courier_id"].dropna().unique())
else:
    couriers = ["All"]
selected_courier = st.sidebar.selectbox("Courier", couriers)

# Day (FIXED)
if "date" in gdf.columns:
    days = ["All"] + sorted(gdf["date"].dt.day.dropna().unique())
else:
    days = ["All"]
selected_day = st.sidebar.selectbox("Day of Month", days)

# Category
if "category" in gdf.columns:
    categories = ["All"] + sorted(gdf["category"].dropna().unique())
else:
    categories = ["All"]
selected_category = st.sidebar.selectbox("Category", categories)

# =========================
# APPLY FILTERS
# =========================
df = gdf.copy()

if selected_region != "All":
    df = df[df["2gis region"] == selected_region]

if selected_courier != "All":
    df = df[df["courier_id"] == selected_courier]

if selected_day != "All" and "date" in df.columns:
    df = df[df["date"].dt.day == selected_day]

if selected_category != "All":
    df = df[df["category"] == selected_category]

# =========================
# REGION KPI
# =========================
region_kpi = df.groupby("2gis region").agg(
    shipments=("awb_num", "count")
).reset_index()

# =========================
# LOG SCALE CLASSIFICATION (FIX COLOR ISSUE)
# =========================
region_kpi["log_shipments"] = np.log1p(region_kpi["shipments"])

quantiles = region_kpi["log_shipments"].quantile([0.2, 0.4, 0.6, 0.8]).values

def classify(x):
    lx = np.log1p(x)

    if lx <= quantiles[0]:
        return "Very Low"
    elif lx <= quantiles[1]:
        return "Low"
    elif lx <= quantiles[2]:
        return "Medium"
    elif lx <= quantiles[3]:
        return "High"
    else:
        return "Very High"

region_kpi["status"] = region_kpi["shipments"].apply(classify)

# merge back
df = df.merge(region_kpi, on="2gis region", how="left")

# =========================
# CATEGORY KPI
# =========================
category_kpi = (
    df.groupby(["2gis region", "category"])
    .size()
    .reset_index(name="count")
)

# =========================
# COLORS (CLEAR GRADIENT)
# =========================
status_colors = {
    "Very Low": "#ffffcc",
    "Low": "#a1dab4",
    "Medium": "#41b6c4",
    "High": "#2c7fb8",
    "Very High": "#253494"
}

# =========================
# MAP
# =========================
m = folium.Map(location=[25.2, 55.3], zoom_start=10, tiles="cartodbpositron")

def style_fn(feature):
    region = feature["properties"]["region"]

    row = region_kpi[region_kpi["2gis region"] == region]

    if len(row) == 0:
        color = "#ccc"
    else:
        status = row["status"].values[0]
        color = status_colors.get(status, "#ccc")

    return {
        "fillColor": color,
        "color": "black",
        "weight": 1,
        "fillOpacity": 0.8
    }

for _, r in df.drop_duplicates("2gis region").iterrows():
    region = r["2gis region"]
    sub = df[df["2gis region"] == region]

    # category breakdown
    cat_html = ""
    sub_cat = category_kpi[category_kpi["2gis region"] == region]

    for _, row_cat in sub_cat.iterrows():
        cat_html += f"{row_cat['category']}: {row_cat['count']}<br>"

    popup = folium.Popup(f"""
    <b>Region:</b> {region}<br>
    <b>Shipments:</b> {len(sub)}<br><br>
    <b>Category:</b><br>{cat_html}
    """, max_width=300)

    geo = folium.GeoJson(
        {
            "type": "Feature",
            "geometry": r["geometry"].__geo_interface__,
            "properties": {"region": region}
        },
        style_function=style_fn,
        tooltip=f"{region}: {len(sub)}"
    )

    geo.add_child(popup)
    geo.add_to(m)

# =========================
# LEGEND
# =========================
legend_html = """
<div style="
position: fixed;
bottom: 50px;
left: 50px;
z-index:9999;
background-color:white;
padding:10px;
border:2px solid grey;
font-size:14px;
">
<b>Shipment Volume</b><br>
<span style="color:#253494;">⬤</span> Very High<br>
<span style="color:#2c7fb8;">⬤</span> High<br>
<span style="color:#41b6c4;">⬤</span> Medium<br>
<span style="color:#a1dab4;">⬤</span> Low<br>
<span style="color:#ffffcc;">⬤</span> Very Low<br>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# =========================
# DISPLAY MAP
# =========================
st.subheader("🗺️ Control Tower Map")
st_folium(m, width=1200, height=650)

# =========================
# KPI
# =========================
col1, col2, col3 = st.columns(3)

col1.metric("Total Shipments", len(df))
col2.metric("Regions", df["2gis region"].nunique())
col3.metric("Categories", df["category"].nunique() if "category" in df.columns else 0)

# =========================
# CATEGORY CHART
# =========================
st.subheader("📊 Category Breakdown")

if "category" in df.columns:
    st.bar_chart(df["category"].value_counts())

# =========================
# TABLE
# =========================
st.subheader("📋 Data Preview")

preview = df.drop(columns=["geometry"], errors="ignore")
st.dataframe(preview.head(200))