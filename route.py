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

    # ===== 가독성 파라미터(여기만 만지면 튜닝 쉬움) =====
    EDGE_MARGIN_KM = 1.5       # 끝단(0k/106.8k) 근처에서 라벨이 바깥으로 나가는 것 방지
    X_OFFSET_STEP_KM = 0.6     # 그룹 내 라벨을 좌우로 벌리는 기본 간격(0.8이면 더 넓게 퍼짐)
    GROUP_THRESHOLD_KM = 0.31  # 이정이 이 값보다 가까우면 같은 그룹으로 묶기

    # y 레벨(촘촘하게 4단 분산)
    y_up = 1.0
    y_down = 0.0
    UP_Y_LEVELS   = [y_up - 0.12, y_up + 0.16, y_up - 0.24, y_up + 0.04]
    DOWN_Y_LEVELS = [y_down + 0.16, y_down - 0.12, y_down + 0.28, y_down - 0.24]
    # =====================================================

    # 라인 + 라벨(원래처럼 유지)
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.6, "영암 방향 (106.8k → 0k)", fontsize=14)

    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.6, "순천 방향 (0k → 106.8k)", fontsize=14)

    def clamp_x(x):
        # 아주 살짝 안쪽으로 클램프(끝단에서 텍스트 완전 잘림 방지)
        return min(max(x, MIN_KM + 0.2), MAX_KM - 0.2)

    # -------- 영암 방향(위쪽) --------
    prev_km = None
    group = []

    def flush_group_up(group):
        toggle = 1
        sign = -1  # 왼쪽부터 시작

        for _, row in group:
            km = row[KM_COL]
            if pd.isna(km):
                continue

            label = f"({int(row['번호'])})"  # ✅ 1페이지는 번호만

            # y: 4단 순환
            y_current = UP_Y_LEVELS[(toggle - 1) % len(UP_Y_LEVELS)]

            # x: 좌우로 점점 퍼뜨리기
            offset_scale = (toggle + 1) // 2
            x_offset = sign * (X_OFFSET_STEP_KM * offset_scale)

            toggle += 1
            sign *= -1

            x_text = km + x_offset

            # 끝단에서는 무조건 "안쪽"으로만
            if km < MIN_KM + EDGE_MARGIN_KM:
                x_text = km + abs(x_offset)
            elif km > MAX_KM - EDGE_MARGIN_KM:
                x_text = km - abs(x_offset)

            x_text = clamp_x(x_text)

            ax.scatter(km, y_up, marker="v", s=220, color="black")
            ax.plot([km, x_text], [y_up, y_current], linewidth=0.7, color="black")  # leader line

            ax.text(
                x_text,
                y_current,
                label,
                rotation=90,
                ha="center",
                va="center",
                fontsize=11,
            )

    for idx, row in up_df.iterrows():
        km = row[KM_COL]
        if pd.isna(km):
            continue

        if prev_km is None:
            group = [(idx, row)]
        else:
            if abs(prev_km - km) < GROUP_THRESHOLD_KM:
                group.append((idx, row))
            else:
                flush_group_up(group)
                group = [(idx, row)]
        prev_km = km

    if group:
        flush_group_up(group)

    # -------- 순천 방향(아래쪽) --------
    prev_km = None
    group = []

    def flush_group_down(group):
        toggle = 1
        sign = +1  # 오른쪽부터 시작

        for _, row in group:
            km = row[KM_COL]
            if pd.isna(km):
                continue

            label = f"({int(row['번호'])})"  # ✅ 1페이지는 번호만

            # y: 4단 순환
            y_current = DOWN_Y_LEVELS[(toggle - 1) % len(DOWN_Y_LEVELS)]

            offset_scale = (toggle + 1) // 2
            x_offset = sign * (X_OFFSET_STEP_KM * offset_scale)

            toggle += 1
            sign *= -1

            x_text = km + x_offset

            if km < MIN_KM + EDGE_MARGIN_KM:
                x_text = km + abs(x_offset)
            elif km > MAX_KM - EDGE_MARGIN_KM:
                x_text = km - abs(x_offset)

            x_text = clamp_x(x_text)

            ax.scatter(km, y_down, marker="^", s=220, color="black")
            ax.plot([km, x_text], [y_down, y_current], linewidth=0.7, color="black")  # leader line

            ax.text(
                x_text,
                y_current,
                label,
                rotation=90,
                ha="center",
                va="center",
                fontsize=11,
            )

    for idx, row in down_df.iterrows():
        km = row[KM_COL]
        if pd.isna(km):
            continue

        if prev_km is None:
            group = [(idx, row)]
        else:
            if abs(prev_km - km) < GROUP_THRESHOLD_KM:
                group.append((idx, row))
            else:
                flush_group_down(group)
                group = [(idx, row)]
        prev_km = km

    if group:
        flush_group_down(group)

    # -------- 보성 IC(기존 유지: 선 + 텍스트) --------
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














