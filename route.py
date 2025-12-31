import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from io import BytesIO

# ---------------------------
# 한글 폰트 설정
# ---------------------------
font_path = "fonts/NanumGothic-Regular.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams["font.family"] = fm.FontProperties(fname=font_path).get_name()

# ---------------------------
# CSV 로드
# ---------------------------
@st.cache_data
def load_data():
    df_ = pd.read_csv("data.csv")
    # 이정(km) 숫자화(정렬/계산 안정성)
    df_[ "이정(km)" ] = pd.to_numeric(df_[ "이정(km)" ], errors="coerce")
    return df_

df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"

# 표시용 이름
df["표시이름"] = (
    df[NAME_COL]
    .astype(str)
    .str.replace(r"\(영암\)", "", regex=True)
    .str.replace(r"\(순천\)", "", regex=True)
    .str.strip()
)

# 방향 분류
has_yeongam = df[NAME_COL].astype(str).str.contains("영암", na=False)
has_suncheon = df[NAME_COL].astype(str).str.contains("순천", na=False)
neutral = ~(has_yeongam | has_suncheon)

yeongam_options = df[has_yeongam | neutral][NAME_COL].dropna().unique().tolist()
suncheon_options = df[has_suncheon | neutral][NAME_COL].dropna().unique().tolist()

# ---------------------------
# UI
# ---------------------------
st.title("거리비례 노선도 생성기")

st.sidebar.header("교량 선택")
selected_yeongam = st.sidebar.multiselect("영암 방향에서 표시할 교량", yeongam_options)
selected_suncheon = st.sidebar.multiselect("순천 방향에서 표시할 교량", suncheon_options)
st.sidebar.caption("아무것도 선택하지 않으면 전체 교량이 자동으로 표시됩니다.")

df_up_base = df[has_yeongam | neutral]
df_down_base = df[has_suncheon | neutral]

df_up = df[df[NAME_COL].isin(selected_yeongam)] if selected_yeongam else df_up_base
df_down = df[df[NAME_COL].isin(selected_suncheon)] if selected_suncheon else df_down_base

# 정렬 + 번호 부여
df_up_sorted = df_up.sort_values(KM_COL, ascending=False).reset_index(drop=True)
df_up_sorted["번호"] = df_up_sorted.index + 1
df_up_sorted["표시번호"] = df_up_sorted["번호"].apply(lambda x: f"({x})")  # (참고용)

df_down_sorted = df_down.sort_values(KM_COL, ascending=True).reset_index(drop=True)
df_down_sorted["번호"] = df_down_sorted.index + 1
df_down_sorted["표시번호"] = df_down_sorted["번호"].apply(lambda x: f"({x})")  # (참고용)

# IC 감지(첫 IC)
ic_rows = df[df[TYPE_COL].astype(str).str.contains("IC", na=False)]
ic_km = float(ic_rows.iloc[0][KM_COL]) if (not ic_rows.empty and pd.notna(ic_rows.iloc[0][KM_COL])) else None


# ---------------------------
# 1페이지: 노선도
# ---------------------------
def draw_route(up_df, down_df, ic_km=None):
    fig, ax = plt.subplots(figsize=(22, 10))

    MIN_KM = 0
    MAX_KM = 106.8

    # ===== 튜닝 파라미터 =====
    GROUP_THRESHOLD_KM = 0.31   # 가까운 km를 같은 그룹으로 묶는 기준
    EDGE_MARGIN_KM = 1.5        # 끝단에서 라벨이 바깥으로 튀지 않게 하는 구간

    # "포인트(화면)" 단위 오프셋 패턴 (겹침 줄이기 핵심)
    DX_SEQ = [-28, 28, -56, 56, -84, 84, -112, 112]
    DY_SEQ_UP =   [-16, 20, -28, 32, -40, 44, -52, 56]   # 위 라인용
    DY_SEQ_DOWN = [20, -16, 32, -28, 44, -40, 56, -52]   # 아래 라인용
    # =======================

    # 라인 위치
    y_up = 1.0
    y_down = 0.0

    # 라인 + 라벨(원래대로 유지)
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.6, "영암 방향 (106.8k → 0k)", fontsize=14)

    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.6, "순천 방향 (0k → 106.8k)", fontsize=14)

    # -------------------
    # 영암 방향(위쪽)
    # -------------------
    up_df_sorted = up_df.sort_values(KM_COL, ascending=False).reset_index(drop=True)
    prev_km = None
    group = []

def flush_group_up(group):
    BASE = 0.10   # 선에서 라벨 시작 높이
    STEP = 0.08   # 라벨 층 간격(작을수록 촘촘)

    for i, (_, row) in enumerate(group):
        km = row[KM_COL]
        if pd.isna(km):
            continue

        label = f"({int(row['번호'])})"   # 번호만

        # ✅ x는 절대 안 밀기 (대각선 교차 원인 제거)
        x_text = km

        # ✅ 같은 그룹 안에서는 위로만 층층이
        y_current = y_up + BASE + STEP * i

        ax.scatter(km, y_up, marker="v", s=220, color="black", zorder=3)

        # ✅ 연결선은 수직 (교차 거의 없음)
        ax.vlines(km, y_up, y_current, colors="black", linewidth=0.7, zorder=2)

        ax.text(
            x_text,
            y_current,
            label,
            rotation=90,
            ha="center",
            va="center",
            fontsize=11,
            zorder=4,
            bbox=dict(facecolor="white", edgecolor="none", pad=0.2, alpha=0.8),
        )

    # -------------------
    # 순천 방향(아래쪽)
    # -------------------
    down_df_sorted = down_df.sort_values(KM_COL, ascending=True).reset_index(drop=True)
    prev_km = None
    group = []

def flush_group_down(group):
    BASE = 0.10
    STEP = 0.08

    for i, (_, row) in enumerate(group):
        km = row[KM_COL]
        if pd.isna(km):
            continue

        label = f"({int(row['번호'])})"

        x_text = km
        y_current = y_down - BASE - STEP * i   # ✅ 아래로만 층층이

        ax.scatter(km, y_down, marker="^", s=220, color="black", zorder=3)

        ax.vlines(km, y_current, y_down, colors="black", linewidth=0.7, zorder=2)

        ax.text(
            x_text,
            y_current,
            label,
            rotation=90,
            ha="center",
            va="center",
            fontsize=11,
            zorder=4,
            bbox=dict(facecolor="white", edgecolor="none", pad=0.2, alpha=0.8),
        )


    # -------------------
    # IC 표시(원래대로)
    # -------------------
    if ic_km is not None:
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.32, f"보성IC ({ic_km}k)", ha="center", fontsize=12)

        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.32, f"보성IC ({ic_km}k)", ha="center", va="top", fontsize=12)

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1.0, 2.0)
    ax.axis("off")
    fig.tight_layout()
    return fig


# ---------------------------
# 2페이지: 교량 목록(이름 표시 유지)
# ---------------------------
def draw_list_page(up_df, down_df):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    ax.text(0.05, 0.92, "영암 방향 교량 목록", fontsize=14, weight="bold")
    ax.text(0.55, 0.92, "순천 방향 교량 목록", fontsize=14, weight="bold")

    up_list = [
        f"{int(row['번호'])}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in up_df.iterrows()
    ]
    down_list = [
        f"{int(row['번호'])}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in down_df.iterrows()
    ]

    up_text = "\n".join(up_list) if up_list else "선택된 교량 없음"
    down_text = "\n".join(down_list) if down_list else "선택된 교량 없음"

    ax.text(0.05, 0.88, up_text, fontsize=10, va="top")
    ax.text(0.55, 0.88, down_text, fontsize=10, va="top")

    fig.tight_layout()
    return fig


# ---------------------------
# PDF 생성/다운로드
# ---------------------------
if st.button("노선도 생성 및 PDF 다운로드"):
    fig_route = draw_route(df_up_sorted, df_down_sorted, ic_km)
    fig_list = draw_list_page(df_up_sorted, df_down_sorted)

    st.subheader("노선도 미리보기(1페이지)")
    st.pyplot(fig_route)

    pdf_buffer = BytesIO()
    with PdfPages(pdf_buffer) as pdf:
        pdf.savefig(fig_route, bbox_inches="tight")
        pdf.savefig(fig_list, bbox_inches="tight")
    pdf_buffer.seek(0)

    st.download_button(
        label="PDF 다운로드",
        data=pdf_buffer,
        file_name="노선도_및_교량목록.pdf",
        mime="application/pdf",
    )











