import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO

# ================================================
# 1. 한글 폰트 설정
# ================================================
plt.rcParams["font.family"] = ["NanumGothic", "NanumMyeongjo", "UnDotum", "DejaVu Sans"]

# ================================================
# 2. CSV 불러오기
# ================================================
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"

# ================================================
# 3. UI – 교량 목록 표시 (선택가능)
# ================================================
st.title("거리비례 노선도 생성기 (자동 분류 + 선택기능)")

all_names = df[NAME_COL].dropna().unique().tolist()

st.sidebar.header("교량 선택")

selected_yeongam = st.sidebar.multiselect("영암 방향 표시할 교량", all_names)
selected_suncheon = st.sidebar.multiselect("순천 방향 표시할 교량", all_names)

st.sidebar.write("※ 선택하지 않으면 자동 분류된 전체 교량이 표시됩니다.")


# ================================================
# 4. 방향 자동 분류
# ================================================
is_yeongam = df[NAME_COL].str.contains("영암", na=False)
is_suncheon = df[NAME_COL].str.contains("순천", na=False)
is_neutral = ~(is_yeongam | is_suncheon)

# 자동 기본값
df_up_auto = df[is_yeongam | is_neutral].sort_values(KM_COL)
df_down_auto = df[is_suncheon | is_neutral].sort_values(KM_COL)

# 선택한 게 있으면 교체
if selected_yeongam:
    df_up = df[df[NAME_COL].isin(selected_yeongam)].sort_values(KM_COL)
else:
    df_up = df_up_auto

if selected_suncheon:
    df_down = df[df[NAME_COL].isin(selected_suncheon)].sort_values(KM_COL)
else:
    df_down = df_down_auto


# ================================================
# 5. 보성IC 자동 감지
# ================================================
ic_rows = df[df[TYPE_COL].str.contains("IC", case=False, na=False)]
bosung_ic_km = float(ic_rows.iloc[0][KM_COL]) if not ic_rows.empty else None


# ================================================
# 6. 노선도 생성 함수
# ================================================
def draw_route(df_up, df_down, ic_km=None):
    fig, ax = plt.subplots(figsize=(20, 7))

    MIN_KM = 0
    MAX_KM = 106.8

    # ====== 영암 방향 (위) ======
    y_up = 1
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.12, "영암 방향 (106.8k → 0k)", fontsize=14)

    for _, row in df_up.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL].replace("(영암)", "").replace("(순천)", "")
        ax.scatter(km, y_up, marker="v", s=220, color="black")
        ax.text(km, y_up - 0.15, f"{name}\n({km}k)", ha="center", fontsize=10)

    # ====== 순천 방향 (아래) ======
    y_down = 0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.12, "순천 방향 (0k → 106.8k)", fontsize=14)

    for _, row in df_down.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL].replace("(영암)", "").replace("(순천)", "")
        ax.scatter(km, y_down, marker="^", s=220, color="black")
        ax.text(km, y_down - 0.17, f"{name}\n({km}k)", ha="center", fontsize=10)

    # ====== 보성IC 양방향 ======
    if ic_km is not None:
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.30, f"보성IC ({ic_km}k)", ha="center", fontsize=12)

        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.30, f"보성IC ({ic_km}k)", ha="center", fontsize=12, va="top")

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1, 2)
    ax.axis("off")

    plt.tight_layout()
    return fig


# ================================================
# 7. 실행 버튼
# ================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    fig = draw_route(df_up, df_down, bosung_ic_km)

    st.pyplot(fig)

    pdf = BytesIO()
    fig.savefig(pdf, format="pdf", bbox_inches="tight")
    pdf.seek(0)

    st.download_button(
        "📄 PDF 다운로드",
        data=pdf,
        file_name="노선도.pdf",
        mime="application/pdf"
    )
