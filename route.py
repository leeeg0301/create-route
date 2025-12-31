import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from io import BytesIO

# ======================================================
# 1. 한글 폰트 설정 (fonts/NanumGothic-Regular.ttf 있으면 적용)
# ======================================================
font_path = "fonts/NanumGothic-Regular.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams["font.family"] = "NanumGothic"

# ======================================================
# 2. CSV 불러오기
# ======================================================
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"

# ✅ 이정(km) 숫자 변환(그룹핑/정렬 안정화)
df[KM_COL] = pd.to_numeric(df[KM_COL], errors="coerce")

# 괄호 안의 방향 제거하여 표시용 이름 생성
df["표시이름"] = (
    df[NAME_COL]
    .astype(str)
    .str.replace(r"\(영암\)", "", regex=True)
    .str.replace(r"\(순천\)", "", regex=True)
    .str.strip()
)

# ======================================================
# 3. 방향 분류
# ======================================================
has_yeongam = df[NAME_COL].astype(str).str.contains("영암", na=False)
has_suncheon = df[NAME_COL].astype(str).str.contains("순천", na=False)
neutral = ~(has_yeongam | has_suncheon)

yeongam_options = df[has_yeongam | neutral][NAME_COL].dropna().unique().tolist()
suncheon_options = df[has_suncheon | neutral][NAME_COL].dropna().unique().tolist()

# ======================================================
# 4. Streamlit UI
# ======================================================
st.title("거리비례 노선도 생성기")

st.sidebar.header("교량 선택")

selected_yeongam = st.sidebar.multiselect(
    "영암 방향 표시할 교량", yeongam_options
)

selected_suncheon = st.sidebar.multiselect(
    "순천 방향 표시할 교량", suncheon_options
)

st.sidebar.write("※ 선택하지 않으면 해당 방향 전체 자동 표시됩니다.")

# ======================================================
# 5. 선택된 교량 데이터 정리 + 번호 매기기
# ======================================================
df_up_base = df[has_yeongam | neutral]
df_down_base = df[has_suncheon | neutral]

df_up = df[df[NAME_COL].isin(selected_yeongam)] if selected_yeongam else df_up_base
df_down = df[df[NAME_COL].isin(selected_suncheon)] if selected_suncheon else df_down_base

# 영암: 큰 km → 작은 km
df_up_sorted = df_up.sort_values(KM_COL, ascending=False).reset_index(drop=True)
df_up_sorted["번호"] = df_up_sorted.index + 1
df_up_sorted["표시번호"] = df_up_sorted["번호"].apply(lambda x: f"({x})")

# 순천: 작은 km → 큰 km
df_down_sorted = df_down.sort_values(KM_COL, ascending=True).reset_index(drop=True)
df_down_sorted["번호"] = df_down_sorted.index + 1
df_down_sorted["표시번호"] = df_down_sorted["번호"].apply(lambda x: f"({x})")

# ======================================================
# 6. IC 자동 감지
# ======================================================
ic_rows = df[df[TYPE_COL].astype(str).str.contains("IC", na=False)]
ic_km = float(ic_rows.iloc[0][KM_COL]) if (not ic_rows.empty and pd.notna(ic_rows.iloc[0][KM_COL])) else None

# ======================================================
# 7. 노선도 그리기 (겹침방지 + 가까운 교량 라벨 묶음)
# ======================================================
def draw_route(up_df, down_df, ic_km=None):
    fig, ax = plt.subplots(figsize=(22, 10))

    MIN_KM = 0
    MAX_KM = 106.8

    # ---- 튜닝 값(너가 필요하면 여기만 바꾸면 됨) ----
    GROUP_THRESHOLD_KM = 0.03   # ✅ 0.01k 수준이면 0.03~0.05 추천 (원하면 0.31로 크게도 가능)
    EDGE_MARGIN_KM = 1.5        # 끝단(0k/106.8k)에서 바깥으로 나가는 걸 막기
    X_STEP = 0.55               # 라벨을 좌/우로 퍼뜨리는 정도(km 단위)
    X_OFFSETS = [-0.8, 0.8, -1.6, 1.6, -2.4, 2.4]
    UP_Y_LEVELS   = [1.0 - 0.10, 1.0 + 0.12, 1.0 - 0.20, 1.0 + 0.04, 1.0 - 0.28, 1.0 + 0.20]
    DOWN_Y_LEVELS = [0.0 + 0.12, 0.0 - 0.10, 0.0 + 0.20, 0.0 - 0.18, 0.0 + 0.28, 0.0 - 0.26]
    # -----------------------------------------------

    def clamp_x(x):
        return min(max(x, MIN_KM + 0.05), MAX_KM - 0.05)

    # ============================ 영암 방향 ============================
    y_up = 1.0
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.6, "영암 방향 (106.8k → 0k)", fontsize=14)

    up_df_sorted = up_df.sort_values(KM_COL, ascending=False).reset_index(drop=True)

    prev_km = None
    group = []

    # ✅ 그룹 라벨 “한 번만” 찍기
    def flush_group_up(group, group_idx):
        # group: [(idx, row), ...]
        kms = [float(r[KM_COL]) for _, r in group if pd.notna(r[KM_COL])]
        if not kms:
            return

        # 마커는 각 교량 위치에 그대로
        for km in kms:
            ax.scatter(km, y_up, marker="v", s=220, color="black")

        nums = [int(r["번호"]) for _, r in group]
        n1, n2 = min(nums), max(nums)

        # ✅ 1페이지: 번호만(묶음이면 범위로)
        label = f"({n1}~{n2})" if n1 != n2 else f"({n1})"

        km_anchor = sum(kms) / len(kms)

        # 라벨 배치(그룹 단위로 좌/우 번갈아)
        x_offset = X_OFFSETS[group_idx % len(X_OFFSETS)]

        # y 레벨도 그룹 단위로 순환
        y_current = UP_Y_LEVELS[group_idx % len(UP_Y_LEVELS)]

        x_text = km_anchor + x_offset

        # 끝단이면 안쪽으로만
        if km_anchor < MIN_KM + EDGE_MARGIN_KM:
            x_text = km_anchor + abs(x_offset)
        elif km_anchor > MAX_KM - EDGE_MARGIN_KM:
            x_text = km_anchor - abs(x_offset)

        x_text = clamp_x(x_text)

        # leader line + 라벨
        ax.plot([km_anchor, x_text], [y_up, y_current], linewidth=0.7, color="black")
        ax.text(
            x_text,
            y_current,
            label,
            rotation=90,
            ha="center",
            va="center",
            fontsize=11,
        )

    # 그룹핑(영암)
    group_idx = 0
    for idx, row in up_df_sorted.iterrows():
        km = row[KM_COL]
        if pd.isna(km):
            continue

        if prev_km is None:
            group = [(idx, row)]
        else:
            if abs(prev_km - km) <= GROUP_THRESHOLD_KM:
                group.append((idx, row))
            else:
                flush_group_up(group, group_idx)
                group_idx += 1
                group = [(idx, row)]
        prev_km = km

    if group:
        flush_group_up(group, group_idx)

    # ============================ 순천 방향 ============================
    y_down = 0.0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.6, "순천 방향 (0k → 106.8k)", fontsize=14)

    down_df_sorted = down_df.sort_values(KM_COL, ascending=True).reset_index(drop=True)

    prev_km = None
    group = []

    def flush_group_down(group, group_idx):
        kms = [float(r[KM_COL]) for _, r in group if pd.notna(r[KM_COL])]
        if not kms:
            return

        for km in kms:
            ax.scatter(km, y_down, marker="^", s=220, color="black")

        nums = [int(r["번호"]) for _, r in group]
        n1, n2 = min(nums), max(nums)
        label = f"({n1}~{n2})" if n1 != n2 else f"({n1})"

        km_anchor = sum(kms) / len(kms)

        x_offset = X_OFFSETS[group_idx % len(X_OFFSETS)]
        y_current = DOWN_Y_LEVELS[group_idx % len(DOWN_Y_LEVELS)]

        x_text = km_anchor + x_offset

        if km_anchor < MIN_KM + EDGE_MARGIN_KM:
            x_text = km_anchor + abs(x_offset)
        elif km_anchor > MAX_KM - EDGE_MARGIN_KM:
            x_text = km_anchor - abs(x_offset)

        x_text = clamp_x(x_text)

        ax.plot([km_anchor, x_text], [y_down, y_current], linewidth=0.7, color="black")
        ax.text(
            x_text,
            y_current,
            label,
            rotation=90,
            ha="center",
            va="center",
            fontsize=11,
        )

    # 그룹핑(순천)
    group_idx = 0
    for idx, row in down_df_sorted.iterrows():
        km = row[KM_COL]
        if pd.isna(km):
            continue

        if prev_km is None:
            group = [(idx, row)]
        else:
            if abs(prev_km - km) <= GROUP_THRESHOLD_KM:
                group.append((idx, row))
            else:
                flush_group_down(group, group_idx)
                group_idx += 1
                group = [(idx, row)]
        prev_km = km

    if group:
        flush_group_down(group, group_idx)

    # ============================ 보성 IC ============================
    if ic_km is not None:
        # 위쪽
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.32, f"보성IC ({ic_km}k)", ha="center", fontsize=12)

        # 아래쪽
        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.32, f"보성IC ({ic_km}k)", ha="center", va="top", fontsize=12)

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1.0, 2.0)
    ax.axis("off")
    fig.tight_layout()

    return fig

# ======================================================
# 8. 2페이지: 교량 목록
# ======================================================
def draw_list_page(up_df, down_df):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    ax.text(0.05, 0.93, "영암 방향 교량 목록", fontsize=18, weight="bold")
    ax.text(0.55, 0.93, "순천 방향 교량 목록", fontsize=18, weight="bold")

    # 영암
    up_list = [
        f"{int(row['번호'])}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in up_df.iterrows()
        if pd.notna(row[KM_COL])
    ]
    up_text = "\n".join(up_list) if up_list else "선택된 교량 없음"

    # 순천
    down_list = [
        f"{int(row['번호'])}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in down_df.iterrows()
        if pd.notna(row[KM_COL])
    ]
    down_text = "\n".join(down_list) if down_list else "선택된 교량 없음"

    ax.text(0.05, 0.85, up_text, fontsize=14, va="top")
    ax.text(0.55, 0.85, down_text, fontsize=14, va="top")

    fig.tight_layout()
    return fig

# ======================================================
# 9. PDF 생성 버튼
# ======================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    fig_route = draw_route(df_up_sorted, df_down_sorted, ic_km)
    fig_list = draw_list_page(df_up_sorted, df_down_sorted)

    st.subheader("노선도 미리보기")
    st.pyplot(fig_route)

    pdf_buffer = BytesIO()
    with PdfPages(pdf_buffer) as pdf:
        pdf.savefig(fig_route, bbox_inches="tight")
        pdf.savefig(fig_list, bbox_inches="tight")
    pdf_buffer.seek(0)

    st.download_button(
        label="📄 PDF 다운로드 (노선도 + 교량목록)",
        data=pdf_buffer,
        file_name="노선도_및_교량목록.pdf",
        mime="application/pdf"
    )






