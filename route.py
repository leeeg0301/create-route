import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO

# ============================================================
# 1. 한글 폰트 설정 (깨짐 방지)
# ============================================================
plt.rcParams["font.family"] = ["NanumGothic", "NanumMyeongjo", "UnDotum", "DejaVu Sans"]


# ============================================================
# 2. CSV 불러오기 (파일명: data.csv)
# ============================================================
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"


# ============================================================
# 3. 방향 자동 분류
# ============================================================

# "(영암)" 포함하면 영암
is_yeongam = df[NAME_COL].str.contains("영암", na=False)

# "(순천)" 포함하면 순천
is_suncheon = df[NAME_COL].str.contains("순천", na=False)

# 둘 다 없으면 중립 → 양쪽 다 넣음
is_neutral = ~(is_yeongam | is_suncheon)

# 영암 방향
df_up = df[is_yeongam | is_neutral].sort_values(KM_COL)

# 순천 방향
df_down = df[is_suncheon | is_neutral].sort_values(KM_COL)


# ============================================================
# 4. 보성IC 자동 감지
# ============================================================
ic_rows = df[df[TYPE_COL].str.contains("IC", case=False, na=False)]
bosung_ic_km = None

if not ic_rows.empty:
    bosung_ic_km = float(ic_rows.iloc[0][KM_COL])


# ============================================================
# 5. 노선도 생성 함수 (거리비례)
# ============================================================
def draw_route(df_up, df_down, ic_km=None):
    fig, ax = plt.subplots(figsize=(20, 7))

    MIN_KM = 0
    MAX_KM = 106.8

    # -------------------- 영암 방향 (위) --------------------
    y_up = 1
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.12, "영암 방향 (106.8k → 0k)", fontsize=13)

    for _, row in df_up.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL].replace("(영암)", "").replace("(순천)", "")
        ax.scatter(km, y_up, marker="v", s=200, color="black")
        ax.text(km, y_up - 0.15, f"{name}\n({km}k)", ha="center", va="top", fontsize=11)

    # -------------------- 순천 방향 (아래) --------------------
    y_down = 0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.12, "순천 방향 (0k → 106.8k)", fontsize=13)

    for _, row in df_down.iterrows():
        km = row[KM_COL]
        name = row[NAME_COL].replace("(영암)", "").replace("(순천)", "")
        ax.scatter(km, y_down, marker="^", s=200, color="black")
        ax.text(km, y_down - 0.18, f"{name}\n({km}k)", ha="center", va="top", fontsize=11)

    # -------------------- 보성IC (양쪽 모두 표시) --------------------
    if ic_km is not None:
        # 위쪽
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.30, f"보성IC ({ic_km}k)", ha="center", fontsize=11)

        # 아래쪽
        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.30, f"보성IC ({ic_km}k)", ha="center", va="top", fontsize=11)

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1, 2)
    ax.axis("off")
    plt.tight_layout()

    return fig


# ============================================================
# 6. Streamlit UI
# ============================================================
st.title("거리비례 노선도 생성기 (영암/순천 자동분류 + 보성IC 자동표시)")

st.write("CSV에서 방향을 자동으로 판별하여 노선도를 생성합니다.")


# ============================================================
# 7. 생성 버튼
# ============================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    fig = draw_route(df_up, df_down, bosung_ic_km)

    st.subheader("미리보기")
    st.pyplot(fig)

    # PDF 생성
    pdf_buffer = BytesIO()
    fig.savefig(pdf_buffer, format="pdf", bbox_inches="tight")
    pdf_buffer.seek(0)

    st.download_button(
        label="📄 PDF 다운로드",
        data=pdf_buffer,
        file_name="노선도.pdf",
        mime="application/pdf",
    )

