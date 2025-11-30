import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from io import BytesIO

# ======================================================
# 1. 한글 폰트 설정 (fonts/NanumGothic.ttf 있으면 사용)
# ======================================================
font_path = "fonts/NanumGothic-Regular.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams["font.family"] = "NanumGothic"
#else:
    # 폰트 없으면 시스템 기본폰트 사용
    #plt.rcParams["font.family"] = "DejaVu Sans"

# ======================================================
# 2. 데이터 불러오기 (data.csv)
# ======================================================
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"

# 괄호 안의 방향표시 제거한 순수 교량명 컬럼 추가
df["표시이름"] = (
    df[NAME_COL]
    .str.replace(r"\(영암\)", "", regex=True)
    .str.replace(r"\(순천\)", "", regex=True)
    .str.strip()
)

# ======================================================
# 3. 방향 자동 분류 & 선택창 옵션
# ======================================================
has_yeongam = df[NAME_COL].str.contains("영암", na=False)
has_suncheon = df[NAME_COL].str.contains("순천", na=False)
neutral = ~(has_yeongam | has_suncheon)  # 둘 다 없는 중립

# 선택창에 보일 교량 목록
yeongam_options = df[has_yeongam | neutral][NAME_COL].unique().tolist()
suncheon_options = df[has_suncheon | neutral][NAME_COL].unique().tolist()

# ======================================================
# 4. Streamlit UI
# ======================================================
st.title("거리비례 노선도 생성기")

st.sidebar.header("교량 선택")

selected_yeongam = st.sidebar.multiselect(
    "영암 방향 표시할 교량",
    yeongam_options,
)

selected_suncheon = st.sidebar.multiselect(
    "순천 방향 표시할 교량",
    suncheon_options,
)

st.sidebar.write("※ 선택 안 하면 해당 방향의 전체 교량이 자동 표시됩니다.")

# 영암/순천 기본 데이터 (선택 없을 경우)
df_up_auto = df[has_yeongam | neutral]
df_down_auto = df[has_suncheon | neutral]

df_up = df[df[NAME_COL].isin(selected_yeongam)] if selected_yeongam else df_up_auto
df_down = df[df[NAME_COL].isin(selected_suncheon)] if selected_suncheon else df_down_auto

# ======================================================
# 5. 번호 매기기 (영암: 큰 km→작은 km / 순천: 작은 km→큰 km)
#     표시는 (1), (2) ...
# ======================================================
# 영암
df_up_sorted = df_up.sort_values(KM_COL, ascending=False).reset_index(drop=True)
df_up_sorted["번호"] = df_up_sorted.index + 1
df_up_sorted["표시번호"] = df_up_sorted["번호"].apply(lambda x: f"({x})")

# 순천
df_down_sorted = df_down.sort_values(KM_COL, ascending=True).reset_index(drop=True)
df_down_sorted["번호"] = df_down_sorted.index + 1
df_down_sorted["표시번호"] = df_down_sorted["번호"].apply(lambda x: f"({x})")

# ======================================================
# 6. IC 자동 감지 (종별구분에 'IC' 포함된 첫 번째)
# ======================================================
ic_rows = df[df[TYPE_COL].str.contains("IC", case=False, na=False)]
ic_km = float(ic_rows.iloc[0][KM_COL]) if not ic_rows.empty else None

# ======================================================
# 7. 노선도 그리는 함수
# ======================================================
def draw_route(up_df, down_df, ic_km=None):
    fig, ax = plt.subplots(figsize=(22, 10))

    MIN_KM = 0
    MAX_KM = 106.8

    # ---------------- 영암 방향 (위) ----------------
    y_up = 1.0
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.15, "영암 방향 (106.8k → 0k)", fontsize=14)

    for _, row in up_df.iterrows():
        km = row[KM_COL]
        name = row["표시이름"]
        num_label = row["표시번호"]

# ---------------- 겹침 방지 x-offset ----------------
        if prev_km_up is not None and abs(prev_km_up - km) < 0.25:
            x_offset = 0.3
        else:
            x_offset = 0
        prev_km_up = km
# -----------------------------------------------------

        ax.scatter(km, y_up, marker="v", s=220, color="black")
        # 90도 회전 텍스트 (번호 / 이름 / km)
        text = f"{num_label}\n{name}\n({km}k)"
        ax.text(
            km,
            y_up - 0.18,
            text,
            ha="center",
            va="top",
            fontsize=11,
            rotation=90,
        )

    # ---------------- 순천 방향 (아래) ----------------
    y_down = 0.0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.15, "순천 방향 (0k → 106.8k)", fontsize=14)

    for _, row in down_df.iterrows():
        km = row[KM_COL]
        name = row["표시이름"]
        num_label = row["표시번호"]

    # ---------------- 겹침 방지 x-offset ----------------
        if prev_km_down is not None and abs(prev_km_down - km) < 0.25:
            x_offset = 0.3
        else:
            x_offset = 0
        prev_km_down = km
  # -----------------------------------------------------

        ax.scatter(km, y_down, marker="^", s=220, color="black")
        text = f"{num_label}\n{name}\n({km}k)"
        ax.text(
            km,
            y_down - 0.20,
            text,
            ha="center",
            va="top",
            fontsize=11,
            rotation=90,
        )

    # ---------------- 보성IC 등 IC 표시 (양방향) ----------------
    if ic_km is not None:
        # 위쪽 IC
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.32, f"보성IC ({ic_km}k)", ha="center", fontsize=12)

        # 아래쪽 IC
        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(
            ic_km,
            y_down - 0.32,
            f"보성IC ({ic_km}k)",
            ha="center",
            va="top",
            fontsize=12,
        )

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1.0, 2.0)
    ax.axis("off")
    fig.tight_layout()

    return fig

# ======================================================
# 8. 교량 목록 페이지(2페이지용) 그리기
# ======================================================
def draw_list_page(up_df, down_df):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    # 제목
    ax.text(0.05, 0.93, "영암 방향 교량 목록", fontsize=18, weight="bold")
    ax.text(0.55, 0.93, "순천 방향 교량 목록", fontsize=18, weight="bold")

    # 영암 목록 텍스트
    up_lines = [
        f"{int(row['번호'])}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in up_df.iterrows()
    ]
    up_text = "\n".join(up_lines) if up_lines else "선택된 교량 없음"

    # 순천 목록 텍스트
    down_lines = [
        f"{int(row['번호'])}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in down_df.iterrows()
    ]
    down_text = "\n".join(down_lines) if down_lines else "선택된 교량 없음"

    ax.text(0.05, 0.85, up_text, fontsize=14, va="top")
    ax.text(0.55, 0.85, down_text, fontsize=14, va="top")

    fig.tight_layout()
    return fig

# ======================================================
# 9. 버튼 동작: 노선도 + PDF 2페이지 생성
# ======================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    # 그림 생성
    fig_route = draw_route(df_up_sorted, df_down_sorted, ic_km)
    fig_list = draw_list_page(df_up_sorted, df_down_sorted)

    # 화면에 노선도 미리보기
    st.subheader("노선도 미리보기")
    st.pyplot(fig_route)

    # PDF 버퍼 생성 (2페이지)
    pdf_buffer = BytesIO()
    with PdfPages(pdf_buffer) as pdf:
        pdf.savefig(fig_route, bbox_inches="tight")
        pdf.savefig(fig_list, bbox_inches="tight")
    pdf_buffer.seek(0)

    st.download_button(
        label="📄 PDF 다운로드 (노선도 + 목록)",
        data=pdf_buffer,
        file_name="노선도_및_교량목록.pdf",
        mime="application/pdf",
    )


