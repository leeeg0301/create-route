import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO

# ============================================================
# 1) 한글 폰트 설정 (Cloud에서도 깨짐 없음)
# ============================================================
plt.rcParams['font.family'] = ['NanumGothic', 'NanumMyeongjo', 'UnDotum', 'DejaVu Sans']


# ============================================================
# 2) CSV 불러오기 (파일명: data.csv)
# ============================================================
@st.cache_data
def load_data():
    df = pd.read_csv("data.csv")
    return df

df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"


# ============================================================
# 3) UI – 교량 선택
# ============================================================
st.title("고속도로 거리비례 노선도 생성기 (양방향 + IC 자동표시)")

all_bridges = df[NAME_COL].dropna().unique().tolist()

st.sidebar.header("교량 선택")

select_yeongam = st.sidebar.multiselect("영암 방향 교량 선택", all_bridges)
select_suncheon = st.sidebar.multiselect("순천 방향 교량 선택", all_bridges)


# ============================================================
# 4) 보성IC 자동 감지
# ============================================================
ic_rows = df[df[TYPE_COL].str.contains("IC", case=False, na=False)]
bosung_ic_km = None

if not ic_rows.empty:
    bosung_ic_km = float(ic_rows.iloc[0][KM_COL])


# ============================================================
# 5) 노선도 생성 함수
# ============================================================
def draw_route(yeongam_df, suncheon_df, ic_km=None):
    fig, ax = plt.subplots(figsize=(18, 6))

    MIN_KM = 0
    MAX_KM = 106.8

    # -------------------- 영암 방향 --------------------
    y_up = 1
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.15, "영암 방향 (106.8k → 0k)", fontsize=12)

    for _, row in yeongam_df.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL]
        ax.scatter(km, y_up, marker="v", s=160, color="black")
        ax.text(km, y_up - 0.13, f"{name}\n({km}k)", ha="center", va="top")

    # -------------------- 순천 방향 --------------------
    y_down = 0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.13, "순천 방향 (0k → 106.8k)", fontsize=12)

    for _, row in suncheon_df.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL]
        ax.scatter(km, y_down, marker="^", s=160, color="black")
        ax.text(km, y_down - 0.17, f"{name}\n({km}k)", ha="center", va="top")

    # -------------------- 보성IC 양방향 --------------------
    if ic_km is not None:
        # 위(영암)
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.30, f"보성IC ({ic_km}k)", ha="center")

        # 아래(순천)
        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.30, f"보성IC ({ic_km}k)", ha="center", va="top")

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1, 2)
    ax.axis("off")
    plt.tight_layout()

    return fig


# ============================================================
# 6) 생성 버튼
# ============================================================
if st.button("노선도 생성 및 PDF 다운로드"):

    df_up = df[df[NAME_COL].isin(select_yeongam)].sort_values(KM_COL)
    df_down = df[df[NAME_COL].isin(select_suncheon)].sort_values(KM_COL)

    if df_up.empty and df_down.empty:
        st.warning("교량을 최소 1개 이상 선택하세요.")
    else:
        fig = draw_route(df_up, df_down, bosung_ic_km)

        st.subheader("노선도 미리보기")
        st.pyplot(fig)

        # PDF 생성
        pdf_buffer = BytesIO()
        fig.savefig(pdf_buffer, format="pdf", bbox_inches="tight")
        pdf_buffer.seek(0)

        st.download_button(
            label="📄 PDF 다운로드",
            data=pdf_buffer,
            file_name="노선도.pdf",
            mime="application/pdf"
        )


