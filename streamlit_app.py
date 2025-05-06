import streamlit as st
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import folium
from streamlit_folium import st_folium

# GitHub 경로 (사용자 경로로 수정 필요)
road_url = "https://raw.githubusercontent.com/annemayer30/NOO/main/도로지점 위경도.xlsx"
lamp_url = "https://raw.githubusercontent.com/annemayer30/NOO/main/가로등 위치 정보.xlsx"
traffic_url = "https://raw.githubusercontent.com/annemayer30/NOO/main/2024_서울시_일일 총 교통량.xlsx"

# 사용자 입력
st.sidebar.header("입력 값 설정")
radius_m = st.sidebar.number_input("반경 (m)", value=344)
energy_per_pass = st.sidebar.number_input("압전 모듈 1회 통과당 발전량 (Wh)", value=0.00000289)
modules = st.sidebar.number_input("설치 압전 모듈 수", value=3000)
lamp_power = st.sidebar.number_input("가로등 소비 전력 (W)", value=100)
hours = st.sidebar.number_input("점등 시간 (h)", value=13)

@st.cache_data
def load_data():
    road = pd.read_excel(road_url)
    lamp = pd.read_excel(lamp_url)
    traffic = pd.read_excel(traffic_url)
    for df in [road, lamp, traffic]:
        df.columns = df.columns.str.strip()
    return road, lamp, traffic

def latlon_to_cartesian(lat, lon):
    R = 6371000
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    x = R * np.cos(lat_rad) * np.cos(lon_rad)
    y = R * np.cos(lat_rad) * np.sin(lon_rad)
    z = R * np.sin(lat_rad)
    return np.stack((x, y, z), axis=-1)

def get_purple(rank, max_rank):
    norm = 1 - (rank - 1) / (max_rank - 1) if max_rank > 1 else 1
    green = int(200 * (1 - norm))
    return f'#{128:02x}{green:02x}{255:02x}'

# 처리 시작
road_df, lamp_df, traffic_df = load_data()

road_coords = latlon_to_cartesian(road_df["위도"].values, road_df["경도"].values)
lamp_coords = latlon_to_cartesian(lamp_df["위도"].values, lamp_df["경도"].values)

tree = cKDTree(road_coords)
distances, indices = tree.query(lamp_coords, k=1)

mapping = []
for lamp_idx, road_idx in enumerate(indices):
    if distances[lamp_idx] <= radius_m:
        mapping.append({
            "지점 위치": road_df.iloc[road_idx]["지점 위치"],
            "위도": lamp_df.iloc[lamp_idx]["위도"],
            "경도": lamp_df.iloc[lamp_idx]["경도"]
        })

mapped_df = pd.DataFrame(mapping)

lamp_count = mapped_df["지점 위치"].value_counts().reset_index()
lamp_count.columns = ["지점 위치", "가로등개수"]
merged = pd.merge(lamp_count, traffic_df, on="지점 위치", how="left")
merged["상대교통량"] = merged["교통량"] / merged["가로등개수"]
merged["생산전력량_Wh"] = (energy_per_pass * modules * 4 * merged["교통량"]).astype(int)
merged["점등가로등수"] = (merged["생산전력량_Wh"] / (lamp_power * hours)).astype(int)

mapped_df = mapped_df.merge(merged[["지점 위치", "교통량", "상대교통량", "생산전력량_Wh", "점등가로등수"]], on="지점 위치", how="left")
mapped_df["교통량_순위"] = mapped_df["교통량"].rank(method="min", ascending=False).astype(int)
mapped_df["상대교통량_순위"] = mapped_df["상대교통량"].rank(method="min", ascending=False).astype(int)

highlight_df = []
for _, row in merged.iterrows():
    lamps = mapped_df[mapped_df["지점 위치"] == row["지점 위치"]]
    highlight_df.append(lamps.sample(min(row["점등가로등수"], len(lamps)), random_state=1)[["위도", "경도"]])
green_df = pd.concat(highlight_df, ignore_index=True)

# 지도 함수
def create_map(df, rank_col):
    m = folium.Map(location=[df["위도"].mean(), df["경도"].mean()], zoom_start=13)
    max_rank = df[rank_col].max()
    for _, row in df.iterrows():
        folium.CircleMarker(
            location=(row["위도"], row["경도"]),
            radius=5,
            color=get_purple(row[rank_col], max_rank),
            fill=True,
            fill_opacity=0.9,
        ).add_to(m)
    for _, row in green_df.iterrows():
        folium.CircleMarker(
            location=(row["위도"], row["경도"]),
            radius=5,
            color="green",
            fill=True,
            fill_opacity=0.9,
        ).add_to(m)
    return m

col1, col2 = st.columns(2)
with col1:
    st.subheader("🚗 교통량 순위 지도")
    st_folium(create_map(mapped_df, "교통량_순위"), height=400, width=500)

with col2:
    st.subheader("📶 상대교통량 순위 지도")
    st_folium(create_map(mapped_df, "상대교통량_순위"), height=400, width=500)

# 표 출력
st.subheader("📋 지점별 분석 결과 요약")
summary_df = merged[["지점 위치", "가로등개수", "교통량", "상대교통량", "생산전력량_Wh", "점등가로등수"]]
summary_df["상대교통량"] = summary_df["상대교통량"].astype(int)
st.dataframe(summary_df, use_container_width=True)

