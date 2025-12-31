import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from io import BytesIO

# ======================================================
# 1. 한글 폰트 설정 (fonts/NanumGothic.ttf 있으면 적용)
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

# 괄호 안의 방향 제거하여 표시용 이름 생성
df["표시이름"] = (
    df[NAME_COL]
    .str.replace(r"\(영암\)", "", regex=True)
    .str.replace(r"\(순천\)", "", regex=True)
    .str.strip()
)


# ======================================================
# 3. 방향 분류
# ======================================================
has_yeongam = df[NAME_COL].str.contains("영암", na=False)
has_suncheon = df[NAME_COL].str.contains("순천", na=False)
neutral = ~(has_yeongam | has_suncheon)

yeongam_options = df[has_yeongam | neutral][NAME_COL].unique().tolist()
suncheon_options = df[has_suncheon | neutral][NAME_COL].unique().tolist()


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
ic_rows = df[df[TYPE_COL].str.contains("IC", na=False)]
ic_km = float(ic_rows.iloc[0][KM_COL]) if not ic_rows.empty else None


# ======================================================
# 7. 노선도 그리기 (겹침방지 포함)
# ======================================================
def draw_route(up_df, down_df, ic_km=None):
    fig, ax = plt.subplots(figsize=(22, 10))

    MIN_KM = 0
    MAX_KM = 106.8

    # ============================ 영암 방향 ============================
    y_up = 1.0
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.6, "영암 방향 (106.8k → 0k)", fontsize=14)

    up_df_sorted = up_df.sort_values(KM_COL, ascending=False).reset_index(drop=True)

    prev_km = None
    group = []

    def flush_group_up(group):
        toggle = 1       # 1,2,3,4...
        sign = -1        # 영암 방향은 왼쪽(-)부터 시작

        for _, row in group:
            km = row[KM_COL]
            label = f"({int(row['번호'])})"   # ✅ 1페이지는 번호만

            # y 지그재그
            if toggle % 2 == 1:
                y_current = y_up - 0.18   # 아래
            else:
                y_current = y_up + 0.30   # 위

            # x 오프셋
            offset_scale = (toggle + 1) // 2
            x_offset = sign * (0.8 * offset_scale)

            toggle += 1
            sign *= -1

            ax.scatter(km, y_up, marker="v", s=220, color="black")

            ax.text(
                km + x_offset,
                y_current,
                label,
                rotation=90,
                ha="center",
                va="center",
                fontsize=11,
            )

    # 그룹핑(영암)
    for idx, row in up_df_sorted.iterrows():
        km = row[KM_COL]
        if prev_km is None:
            group = [(idx, row)]
        else:
            if abs(prev_km - km) < 0.31:
                group.append((idx, row))
            else:
                flush_group_up(group)
                group = [(idx, row)]
        prev_km = km

    if group:
        flush_group_up(group)

    # ============================ 순천 방향 ============================
    y_down = 0.0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.6, "순천 방향 (0k → 106.8k)", fontsize=14)

    down_df_sorted = down_df.sort_values(KM_COL, ascending=True).reset_index(drop=True)

    prev_km = None
    group = []

    def flush_group_down(group):
        toggle = 1
        sign = +1     # 순천 방향은 오른쪽(+)부터 시작

        for _, row in group:
            km = row[KM_COL]
            label = f"({int(row['번호'])})"   # ✅ 1페이지는 번호만

            # y 지그재그
            if toggle % 2 == 1:
                y_current = y_down + 0.30   # 위
            else:
                y_current = y_down - 0.18   # 아래

            offset_scale = (toggle + 1) // 2
            x_offset = sign * (0.8 * offset_scale)

            toggle += 1
            sign *= -1

            ax.scatter(km, y_down, marker="^", s=220, color="black")

            ax.text(
                km + x_offset,
                y_current,
                label,
                rotation=90,
                ha="center",
                va="center",
                fontsize=11,
            )

    # 그룹핑(순천)
    for idx, row in down_df_sorted.iterrows():
        km = row[KM_COL]
        if prev_km is None:
            group = [(idx, row)]
        else:
            if abs(prev_km - km) < 0.31:
                group.append((idx, row))
            else:
                flush_group_down(group)
                group = [(idx, row)]
        prev_km = km

    if group:
        flush_group_down(group)

    # ============================ 보성 IC ============================
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
        f"{row['번호']}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in up_df.iterrows()
    ]
    up_text = "\n".join(up_list) if up_list else "선택된 교량 없음"

    # 순천
    down_list = [
        f"{row['번호']}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in down_df.iterrows()
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




















