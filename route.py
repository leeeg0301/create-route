# route.py
# - 1페이지(노선도): 번호만 표시 (가까운 교량은 (1~3)처럼 묶음 라벨)
# - 2페이지(목록): 교량명 그대로 표시
# - 지사 기준점/주요 지점 표시는 "항상 고정"으로 hline 위에 표시(이정 로직 영향 없음)

import os
from io import BytesIO

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages


# ======================================================
# 1) 폰트(있으면 적용)
# ======================================================
FONT_PATH = "fonts/NanumGothic-Regular.ttf"
if os.path.exists(FONT_PATH):
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()


# ======================================================
# 2) 데이터 로드
# ======================================================
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")


df = load_data()

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"

# ✅ 이정 숫자화(정렬/그룹핑 안정)
df[KM_COL] = pd.to_numeric(df[KM_COL], errors="coerce")

# 표시용 이름(괄호 제거)
df["표시이름"] = (
    df[NAME_COL]
    .astype(str)
    .str.replace(r"\(영암\)", "", regex=True)
    .str.replace(r"\(순천\)", "", regex=True)
    .str.strip()
)


# ======================================================
# 3) 방향 분류
# ======================================================
has_yeongam = df[NAME_COL].astype(str).str.contains("영암", na=False)
has_suncheon = df[NAME_COL].astype(str).str.contains("순천", na=False)
neutral = ~(has_yeongam | has_suncheon)

yeongam_options = df[has_yeongam | neutral][NAME_COL].dropna().unique().tolist()
suncheon_options = df[has_suncheon | neutral][NAME_COL].dropna().unique().tolist()


# ======================================================
# 4) UI
# ======================================================
st.title("거리비례 노선도 생성기")

st.sidebar.header("교량 선택")
selected_yeongam = st.sidebar.multiselect("영암 방향 표시할 교량", yeongam_options)
selected_suncheon = st.sidebar.multiselect("순천 방향 표시할 교량", suncheon_options)

st.sidebar.divider()

# ✅ 가까운 교량 묶는 기준(0.01k대면 0.03~0.05 추천)
group_threshold_km = st.sidebar.number_input("가까운 교량 묶음 기준(km)", value=0.03, step=0.01)

# ✅ 지사 기준/주요 지점은 "항상 고정 표시"
FIXED_POINTS = [
    ("서영암", 0.38),
    ("학산", 5.34),
    ("강진", 19.53),
    ("장흥", 38.26),
    ("지사 기준", 61.00),
    ("벌교", 79.71),
    ("고흥", 83.91),
    ("순천만", 100.27),
]


# ======================================================
# 5) 선택 반영 + 번호 부여
# ======================================================
df_up_base = df[has_yeongam | neutral]
df_down_base = df[has_suncheon | neutral]

df_up = df[df[NAME_COL].isin(selected_yeongam)] if selected_yeongam else df_up_base
df_down = df[df[NAME_COL].isin(selected_suncheon)] if selected_suncheon else df_down_base

# 영암: 큰 km -> 작은 km
df_up_sorted = df_up.sort_values(KM_COL, ascending=False).reset_index(drop=True)
df_up_sorted["번호"] = df_up_sorted.index + 1

# 순천: 작은 km -> 큰 km
df_down_sorted = df_down.sort_values(KM_COL, ascending=True).reset_index(drop=True)
df_down_sorted["번호"] = df_down_sorted.index + 1


# ======================================================
# 6) (선택) IC 자동 감지(있으면 표시) - 기존 흐름 유지용
# ======================================================
ic_rows = df[df[TYPE_COL].astype(str).str.contains("IC", na=False)]
ic_km = float(ic_rows.iloc[0][KM_COL]) if (not ic_rows.empty and pd.notna(ic_rows.iloc[0][KM_COL])) else None


# ======================================================
# 7) 노선도(1페이지)
#    - 그룹당 라벨 1개: (n1~n2) 또는 (n)
#    - 라벨은 패턴 오프셋(무한 증가 X) + leader line
#    - 지사 기준/주요 지점은 hline 위에 고정 표시(+0.4)
# ======================================================
def draw_route(up_df, down_df, ic_km=None, group_threshold_km=0.03, fixed_points=None):
    fig, ax = plt.subplots(figsize=(22, 10))

    MIN_KM = 0.0
    MAX_KM = 106.8

    # 선 위치
    y_up = 1.0
    y_down = 0.0

    # 끝단 여유(라벨이 밖으로 튀지 않게)
    EDGE_MARGIN_KM = 1.5

    # ✅ 라벨 오프셋은 "고정 패턴"으로 반복(거미줄 방지)
    X_OFFSETS = [-0.8, 0.8, -1.6, 1.6, -2.4, 2.4]
    UP_Y_LEVELS =   [y_up + 0.12, y_up - 0.10, y_up + 0.04, y_up - 0.18, y_up + 0.20, y_up - 0.28]
    DOWN_Y_LEVELS = [y_down + 0.12, y_down - 0.10, y_down + 0.20, y_down - 0.18, y_down + 0.28, y_down - 0.26]

    def clamp_x(x):
        return min(max(x, MIN_KM + 0.05), MAX_KM - 0.05)

    # ---------------- 라인(기본) ----------------
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.6, "영암 방향 (106.8k → 0k)", fontsize=14)

    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.6, "순천 방향 (0k → 106.8k)", fontsize=14)

    # ---------------- 고정 지점 표시(세로선: 위~아래 관통 + 라벨은 위로 0.4) ----------------
    if fixed_points is None:
        fixed_points = []

    TEXT_DY = 0.40  # 라벨 위치를 0.4 올림

    for name, km in fixed_points:
        if km < MIN_KM or km > MAX_KM:
            continue

        # ✅ 전부 "관통 세로선"으로
        lw = 2.2 if name == "지사 기준" else 1.2  # 지사 기준만 조금 굵게(원하면 삭제 가능)
        ax.vlines(
            km,
            y_down - 0.35,
            y_up + 0.35,
            colors="black",
            linewidth=lw,
            zorder=9
        )

        # 라벨은 위쪽 라인 기준으로 +0.4
        ax.text(
            km,
            y_up + TEXT_DY,
            f"{name} {km:.2f}k",
            ha="center",
            va="bottom",
            fontsize=11,
            zorder=10,
            bbox=dict(boxstyle="round,pad=0.20", fc="white", ec="black", lw=1),
        )
    # ---------------- 그룹핑 유틸 ----------------
    def iter_groups(sorted_df, threshold_km):
        prev_km = None
        group = []
        for idx, row in sorted_df.iterrows():
            km = row[KM_COL]
            if pd.isna(km):
                continue

            if prev_km is None:
                group = [(idx, row)]
            else:
                if abs(float(prev_km) - float(km)) <= float(threshold_km):
                    group.append((idx, row))
                else:
                    yield group
                    group = [(idx, row)]
            prev_km = km

        if group:
            yield group

    # ---------------- 영암(위) ----------------
    up_sorted = up_df.sort_values(KM_COL, ascending=False).reset_index(drop=True)

    for g_idx, g in enumerate(iter_groups(up_sorted, group_threshold_km)):
        kms = [float(r[KM_COL]) for _, r in g if pd.notna(r[KM_COL])]
        if not kms:
            continue

        # 마커는 각 교량 위치에 그대로
        for km in kms:
            ax.scatter(km, y_up, marker="v", s=220, color="black")

        nums = [int(r["번호"]) for _, r in g]
        n1, n2 = min(nums), max(nums)
        label = f"({n1}~{n2})" if n1 != n2 else f"({n1})"

        km_anchor = sum(kms) / len(kms)

        x_offset = X_OFFSETS[g_idx % len(X_OFFSETS)]
        y_text = UP_Y_LEVELS[g_idx % len(UP_Y_LEVELS)]

        if km_anchor < MIN_KM + EDGE_MARGIN_KM:
            x_text = km_anchor + abs(x_offset)
        elif km_anchor > MAX_KM - EDGE_MARGIN_KM:
            x_text = km_anchor - abs(x_offset)
        else:
            x_text = km_anchor + x_offset

        x_text = clamp_x(x_text)

        ax.plot([km_anchor, x_text], [y_up, y_text], linewidth=0.7, color="black")
        ax.text(
            x_text,
            y_text,
            label,
            rotation=90,
            ha="center",
            va="center",
            fontsize=11,
        )

    # ---------------- 순천(아래) ----------------
    down_sorted = down_df.sort_values(KM_COL, ascending=True).reset_index(drop=True)

    for g_idx, g in enumerate(iter_groups(down_sorted, group_threshold_km)):
        kms = [float(r[KM_COL]) for _, r in g if pd.notna(r[KM_COL])]
        if not kms:
            continue

        for km in kms:
            ax.scatter(km, y_down, marker="^", s=220, color="black")

        nums = [int(r["번호"]) for _, r in g]
        n1, n2 = min(nums), max(nums)
        label = f"({n1}~{n2})" if n1 != n2 else f"({n1})"

        km_anchor = sum(kms) / len(kms)

        x_offset = X_OFFSETS[g_idx % len(X_OFFSETS)]
        y_text = DOWN_Y_LEVELS[g_idx % len(DOWN_Y_LEVELS)]

        if km_anchor < MIN_KM + EDGE_MARGIN_KM:
            x_text = km_anchor + abs(x_offset)
        elif km_anchor > MAX_KM - EDGE_MARGIN_KM:
            x_text = km_anchor - abs(x_offset)
        else:
            x_text = km_anchor + x_offset

        x_text = clamp_x(x_text)

        ax.plot([km_anchor, x_text], [y_down, y_text], linewidth=0.7, color="black")
        ax.text(
            x_text,
            y_text,
            label,
            rotation=90,
            ha="center",
            va="center",
            fontsize=11,
        )

    # ---------------- (선택) IC 표시(기존 유지용) ----------------
    if ic_km is not None and MIN_KM <= float(ic_km) <= MAX_KM:
        ik = float(ic_km)
        ax.vlines(ik, y_up, y_up + 0.25, colors="black", zorder=8)
        ax.text(
            ik,
            y_up + 0.32,
            f"IC ({ik:.2f}k)",
            ha="center",
            fontsize=12,
            zorder=9,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="black", lw=1),
        )

        ax.vlines(ik, y_down - 0.25, y_down, colors="black", zorder=8)
        ax.text(
            ik,
            y_down - 0.32,
            f"IC ({ik:.2f}k)",
            ha="center",
            va="top",
            fontsize=12,
            zorder=9,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="black", lw=1),
        )

    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1.0, 2.0)
    ax.axis("off")
    fig.tight_layout()
    return fig


# ======================================================
# 8) 2페이지: 교량 목록(이름 표시)
# ======================================================
def draw_list_page(up_df, down_df):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    ax.text(0.05, 0.93, "영암 방향 교량 목록", fontsize=18, weight="bold")
    ax.text(0.55, 0.93, "순천 방향 교량 목록", fontsize=18, weight="bold")

    def fmt_km(x):
        return f"{float(x):.2f}k" if pd.notna(x) else "km 미상"

    up_lines = []
    for _, row in up_df.iterrows():
        up_lines.append(f"{int(row['번호'])}. {row['표시이름']} — {fmt_km(row[KM_COL])}")

    down_lines = []
    for _, row in down_df.iterrows():
        down_lines.append(f"{int(row['번호'])}. {row['표시이름']} — {fmt_km(row[KM_COL])}")

    ax.text(0.05, 0.86, "\n".join(up_lines) if up_lines else "선택된 교량 없음", fontsize=13, va="top")
    ax.text(0.55, 0.86, "\n".join(down_lines) if down_lines else "선택된 교량 없음", fontsize=13, va="top")

    fig.tight_layout()
    return fig


# ======================================================
# 9) PDF 생성/다운로드
# ======================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    fig_route = draw_route(
        df_up_sorted,
        df_down_sorted,
        ic_km=ic_km,
        group_threshold_km=group_threshold_km,
        fixed_points=FIXED_POINTS,
    )
    fig_list = draw_list_page(df_up_sorted, df_down_sorted)

    st.subheader("노선도 미리보기(1페이지)")
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
        mime="application/pdf",
    )






