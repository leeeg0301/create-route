import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO


# -----------------------------
# 한글 폰트 자동 설정
# -----------------------------
def set_korean_font():
    files = fm.findSystemFonts()
    for f in files:
        if "NotoSansCJK" in f or "Noto Sans CJK" in f:
            plt.rcParams['font.family'] = fm.FontProperties(fname=f).get_name()
            return
    plt.rcParams['font.family'] = "DejaVu Sans"

set_korean_font()


# -----------------------------
# 데이터 불러오기
# -----------------------------
@st.cache_data
def load_bridge_data():
    df = pd.read_csv("data.csv")
    return df

df = load_bridge_data()

MIN_KM = 0
MAX_KM = 106.8


# -----------------------------
# 노선도 생성 함수 (IC 양방향 포함)
# -----------------------------
def draw_route_chart(yeongam_df, suncheon_df, ic_km=None):
    fig, ax = plt.subplots(figsize=(18, 6))

    # ===== 영암 방향 (위) =====
    y_up = 1.0
    ax.hlines(y_up, MIN_KM, MAX_KM, colors='black', linewidth=2)
    ax.text(MIN_KM, y_up + 0.15, "영암 방향 (106.8k → 0k)", fontsize=12)

    for _, row in yeongam_df.iterrows():
        km = row["km"]
        name = row["name"]

        ax.scatter(km, y_up, marker="v", s=160, color="black")
        ax.text(km, y_up - 0.13, f"{name}\n({km}k)", ha="center", va="top", fontsize=10)

    # ===== 순천 방향 (아래) =====
    y_down = 0.0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors='black', linewidth=2)
    ax.text(MIN_KM, y_down + 0.12, "순천 방향 (0k → 106.8k)", fontsize=12)

    for _, row in suncheon_df.iterrows():
        km = row["km"]
        name = row["name"]

        ax.scatter(km, y_down, marker="^", s=160, color="black")
        ax.text(km, y_down - 0.17, f"{name}\n({km}k)", ha="center", va="top", fontsize=10)

    # ===== 보성IC (위아래 모두 표시) =====
    if ic_km is not None:
        # 위쪽
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.30, f"보성IC ({ic_km}k)", ha="center", fontsize=10)

        # 아래쪽
        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.30, f"보성IC ({ic_km}k)", ha="center", va="top", fontsize=10)

    # 전체 영역 설정
    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1, 2)
    ax.axis("off")

    plt.tight_layout()
    return fig


# -----------------------------
# Streamlit UI
# -----------------------------
st.title("교량·IC 선택 기반 거리비례 노선도 PDF 생성기")

st.write("좌측에서 교량을 선택하고 노선도를 생성해보세요.")

# Sidebar
yeongam_options = df[df["direction"] == "영암"]["name"].unique().tolist()
suncheon_options = df[df["direction"] == "순천"]["name"].unique().tolist()

select_yeongam = st.sidebar.multiselect("영암 방향 교량 선택", yeongam_options)
select_suncheon = st.sidebar.multiselect("순천 방향 교량 선택", suncheon_options)

# 보성IC 위치 가져오기
ic_row = df[df["is_ic"] == 1]
bosung_ic_km = float(ic_row.iloc[0]["km"]) if not ic_row.empty else None

if st.button("노선도 생성 및 PDF 내보내기"):
    df_up = df[(df["direction"] == "영암") & (df["name"].isin(select_yeongam))].sort_values("km")
    df_down = df[(df["direction"] == "순천") & (df["name"].isin(select_suncheon))].sort_values("km")

    if df_up.empty and df_down.empty:
        st.warning("교량을 선택하세요.")
    else:
        fig = draw_route_chart(df_up, df_down, bosung_ic_km)

        st.subheader("노선도 미리보기")
        st.pyplot(fig)

        buf = BytesIO()
        fig.savefig(buf, format="pdf", bbox_inches="tight")
        buf.seek(0)

        st.download_button(
            label="📄 PDF 다운로드",
            data=buf,
            file_name="노선도.pdf",
            mime="application/pdf"

        )

