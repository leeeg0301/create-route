import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO

# --------------------------
#  한글 폰트 강제 등록 (100% 깨짐 방지)
# --------------------------
font_path = "fonts/NanumGothic.ttf"

# matplotlib에 수동 등록
fm.fontManager.addfont(font_path)
plt.rcParams["font.family"] = "NanumGothic"

# ============================================================
# 2) CSV 불러오기 (data.csv)
# ============================================================
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"


# ============================================================
# 3) 방향 자동 판별
# ============================================================
has_yeongam = df[NAME_COL].str.contains("영암", na=False)
has_suncheon = df[NAME_COL].str.contains("순천", na=False)
neutral = ~(has_yeongam | has_suncheon)   # 중립

# 선택창에 보여줄 교량 목록
yeongam_options = df[has_yeongam | neutral][NAME_COL].unique().tolist()
suncheon_options = df[has_suncheon | neutral][NAME_COL].unique().tolist()


# ============================================================
# 4) Streamlit UI – 교량 선택창
# ============================================================
st.title("거리비례 노선도 생성기 (자동분류 + 선택기능 + IC 자동표시)")

st.sidebar.header("교량 선택")

selected_yeongam = st.sidebar.multiselect(
    "영암 방향 표시할 교량",
    yeongam_options
)

selected_suncheon = st.sidebar.multiselect(
    "순천 방향 표시할 교량",
    suncheon_options
)

st.sidebar.write("※ 선택하지 않으면 해당 방향의 모든 교량이 표시됩니다.")


# ============================================================
# 5) 실제 표시할 교량 데이터 구성
# ============================================================

# 영암 방향 기본값 = (영암 + 중립)
df_up_auto = df[has_yeongam | neutral].sort_values(KM_COL)

# 선택한 경우 우선
if selected_yeongam:
    df_up = df[df[NAME_COL].isin(selected_yeongam)].sort_values(KM_COL)
else:
    df_up = df_up_auto


# 순천 방향 기본값 = (순천 + 중립)
df_down_auto = df[has_suncheon | neutral].sort_values(KM_COL)

if selected_suncheon:
    df_down = df[df[NAME_COL].isin(selected_suncheon)].sort_values(KM_COL)
else:
    df_down = df_down_auto


# ============================================================
# 6) 보성IC 자동 감지 (양방향 표시)
# ============================================================
ic_rows = df[df[TYPE_COL].str.contains("IC", case=False, na=False)]
bosung_ic_km = float(ic_rows.iloc[0][KM_COL]) if not ic_rows.empty else None


# ============================================================
# 7) 노선도 (matplotlib)
# ============================================================
def draw_route(df_up, df_down, ic_km=None):
    fig, ax = plt.subplots(figsize=(22, 8))

    MIN_KM = 0
    MAX_KM = 106.8

    # ---------------- 영암 방향 ----------------
    y_up = 1
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.15, "영암 방향 (106.8k → 0k)", fontsize=14)

    for _, row in df_up.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL].replace("(영암)", "").replace("(순천)", "")
        ax.scatter(km, y_up, marker="v", s=240, color="black")
        ax.text(km, y_up - 0.17, f"{name}\n({km}k)", ha="center", va="top", fontsize=11)

    # ---------------- 순천 방향 ----------------
    y_down = 0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.15, "순천 방향 (0k → 106.8k)", fontsize=14)

    for _, row in df_down.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL].replace("(영암)", "").replace("(순천)", "")
        ax.scatter(km, y_down, marker="^", s=240, color="black")
        ax.text(km, y_down - 0.20, f"{name}\n({km}k)", ha="center", va="top", fontsize=11)

    # ---------------- 보성IC (양방향) ----------------
    if ic_km is not None:
        # 영암쪽
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.32, f"보성IC ({ic_km}k)", ha="center", fontsize=12)

        # 순천쪽
        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.32, f"보성IC ({ic_km}k)", ha="center", va="top", fontsize=12)

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1, 2)
    ax.axis("off")
    plt.tight_layout()

    return fig


# ============================================================
# 8) 실행 버튼
# ============================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    fig = draw_route(df_up, df_down, bosung_ic_km)

    st.subheader("미리보기")
    st.pyplot(fig)

    # PDF 저장
    pdf = BytesIO()
    fig.savefig(pdf, format="pdf", bbox_inches="tight")
    pdf.seek(0)

    st.download_button(
        "📄 PDF 다운로드",
        data=pdf,
        file_name="노선도.pdf",
        mime="application/pdf"
    )




