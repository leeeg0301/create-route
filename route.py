import os
import re
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from io import BytesIO

# ======================================================
# 0. Streamlit 기본 설정
# ======================================================
st.set_page_config(page_title="거리비례 노선도 생성기", layout="wide")

# ======================================================
# 1. 한글 폰트 설정
# ======================================================
font_path = "fonts/NanumGothic-Regular.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False

# ======================================================
# 2. CSV 불러오기
# ======================================================
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

try:
    df = load_data()
except Exception as e:
    st.error(f"data.csv를 읽을 수 없습니다: {e}")
    st.stop()

# 컬럼명(원본 기준)
NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"

# KM 숫자화
if KM_COL in df.columns:
    df[KM_COL] = pd.to_numeric(df[KM_COL], errors="coerce")

# 표시이름(방향 괄호 제거)
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
selected_yeongam = st.sidebar.multiselect("영암 방향 표시할 교량", yeongam_options)
selected_suncheon = st.sidebar.multiselect("순천 방향 표시할 교량", suncheon_options)
st.sidebar.write("※ 선택하지 않으면 해당 방향 전체 자동 표시됩니다.")

label_mode = st.sidebar.radio("노선도 라벨 표시", ["번호만", "짧게", "전체"], index=0)

# 원래 코드 느낌 유지용(지그재그/그룹) 튜닝 슬라이더
st.sidebar.subheader("겹침/간격 튜닝")
close_km = st.sidebar.slider("가까운 km 그룹 기준(이 값 이내면 한 그룹)", 0.05, 1.00, 0.30, 0.05)
zigzag_offset = st.sidebar.slider("지그재그 1층 간격", 0.20, 1.20, 0.55, 0.05)
layer_step = st.sidebar.slider("2층/3층 추가 간격", 0.10, 1.20, 0.45, 0.05)
line_gap = st.sidebar.slider("영암-순천 노선 간격", 2.0, 10.0, 6.0, 0.5)

# ======================================================
# 5. 선택 데이터 정리 + 번호 매기기
# ======================================================
df_up_base = df[has_yeongam | neutral].copy()
df_down_base = df[has_suncheon | neutral].copy()

df_up = df[df[NAME_COL].isin(selected_yeongam)].copy() if selected_yeongam else df_up_base
df_down = df[df[NAME_COL].isin(selected_suncheon)].copy() if selected_suncheon else df_down_base

# 영암: 큰 km → 작은 km
df_up_sorted = df_up.sort_values(KM_COL, ascending=False).reset_index(drop=True)
df_up_sorted["번호"] = df_up_sorted.index + 1
df_up_sorted["표시번호"] = df_up_sorted["번호"].apply(lambda x: f"({x})")

# 순천: 작은 km → 큰 km
df_down_sorted = df_down.sort_values(KM_COL, ascending=True).reset_index(drop=True)
df_down_sorted["번호"] = df_down_sorted.index + 1
df_down_sorted["표시번호"] = df_down_sorted["번호"].apply(lambda x: f"({x})")

# ======================================================
# 6. IC 자동 감지 (여러 개 대응)
# ======================================================
ic_rows = df[df[TYPE_COL].astype(str).str.contains("IC", na=False)].copy()
ic_km = None
if not ic_rows.empty and KM_COL in ic_rows.columns:
    ic_rows = ic_rows.dropna(subset=[KM_COL])
    ic_km = ic_rows[KM_COL].astype(float).tolist()

# ======================================================
# 7. 라벨 문자열
# ======================================================
def make_label(row, mode):
    num = row.get("표시번호", "")
    name = str(row.get("표시이름", ""))
    km = row.get(KM_COL, "")

    if mode == "번호만":
        return f"{num}"
    if mode == "짧게":
        short = (name[:6] + "…") if len(name) > 7 else name
        return f"{num}\n{short}"
    return f"{num}\n{name}\n({km}k)"

# ======================================================
# 8. (핵심) 원래 느낌의 지그재그 배치 + 가까운 km 그룹화
# ======================================================
def compute_zigzag_positions(df_sorted, base_y, first_above=True,
                             close_km=0.30, offset=0.55, layer_step=0.45,
                             same_km_jitter=0.06):
    """
    df_sorted: km 정렬된 데이터프레임
    base_y: 해당 방향의 선 y
    first_above: 그룹 내 첫 항목을 위(+)/아래(-) 중 어디로 둘지
    close_km: 이전 항목과 km 차이가 이 값 이하면 같은 그룹
    offset: 1층(기본) 지그재그 간격
    layer_step: 같은 방향으로 2층/3층 쌓일 때 추가 간격
    same_km_jitter: 동일 km(소수점2자리)일 때 x 지터
    """
    items = []
    rows = df_sorted.dropna(subset=[KM_COL]).reset_index(drop=True)

    # 동일 km 지터
    dup_counter = {}

    # 그룹 생성
    group = []
    prev_km = None
    groups = []

    for _, r in rows.iterrows():
        km = float(r[KM_COL])
        if prev_km is None or abs(km - prev_km) <= close_km:
            group.append(r)
        else:
            groups.append(group)
            group = [r]
        prev_km = km
    if group:
        groups.append(group)

    # 그룹 내 지그재그 배치
    for g in groups:
        for j, r in enumerate(g):
            km = float(r[KM_COL])

            key = round(km, 2)
            dup_counter[key] = dup_counter.get(key, 0) + 1
            x = km + (dup_counter[key] - 1) * same_km_jitter

            # 아래위 아래위
            # j=0: first_above 기준, j=1 반대, j=2 다시 first_above(2층), ...
            side_is_above = (j % 2 == 0) if first_above else (j % 2 == 1)
            side = +1 if side_is_above else -1
            level = j // 2  # 0층, 1층, 2층...

            y = base_y + side * (offset + level * layer_step)

            items.append((x, y, r))
    return items

# ======================================================
# 9. 노선도 그리기 (지그재그 복구 + 노선 간격 확대)
# ======================================================
def draw_route(up_df, down_df, ic_km=None, label_mode="번호만",
               close_km=0.30, zigzag_offset=0.55, layer_step=0.45,
               line_gap=6.0):

    fig, ax = plt.subplots(figsize=(22, 6))

    # x 범위
    MIN_KM = 0
    MAX_KM = 106.8
    all_km = pd.concat([up_df[KM_COL], down_df[KM_COL]], ignore_index=True).dropna()

    if not all_km.empty:
        left = max(MIN_KM, float(all_km.min()) - 2.0)
        right = min(MAX_KM, float(all_km.max()) + 2.0)
        if right - left < 10:
            mid = (left + right) / 2
            left = max(MIN_KM, mid - 5)
            right = min(MAX_KM, mid + 5)
    else:
        left, right = MIN_KM, MAX_KM

    # 노선 y(간격 확!)
    y_up = +line_gap / 2.0
    y_down = -line_gap / 2.0

    # 노선
    ax.hlines(y_up, left, right, colors="black", linewidth=2)
    ax.text(left, y_up + 0.6, "영암 방향 (큰 km → 작은 km)", fontsize=12)

    ax.hlines(y_down, left, right, colors="black", linewidth=2)
    ax.text(left, y_down + 0.6, "순천 방향 (작은 km → 큰 km)", fontsize=12)

    # 지그재그 배치 (영암: 큰→작 정렬, 순천: 작은→큰 정렬)
    up_sorted = up_df.sort_values(KM_COL, ascending=False)
    down_sorted = down_df.sort_values(KM_COL, ascending=True)

    up_items = compute_zigzag_positions(
        up_sorted, base_y=y_up, first_above=True,
        close_km=close_km, offset=zigzag_offset, layer_step=layer_step
    )
    down_items = compute_zigzag_positions(
        down_sorted, base_y=y_down, first_above=False,
        close_km=close_km, offset=zigzag_offset, layer_step=layer_step
    )

    # 마커 + 라벨
    # (원래처럼 선에 가깝게 보이도록 작은 fontsize + rotation 90 유지)
    for x, y, r in up_items:
        ax.scatter(x, y_up, marker="v", s=200, color="black")
        ax.text(x, y, make_label(r, label_mode), rotation=90,
                ha="center", va="center", fontsize=10)

    for x, y, r in down_items:
        ax.scatter(x, y_down, marker="^", s=200, color="black")
        ax.text(x, y, make_label(r, label_mode), rotation=90,
                ha="center", va="center", fontsize=10)

    # IC 표시
    if ic_km is not None:
        vals = [float(v) for v in (ic_km if isinstance(ic_km, (list, tuple, pd.Series)) else [ic_km])]
        for v in vals:
            if left <= v <= right:
                ax.vlines(v, y_up, y_up + 0.25, colors="black")
                ax.text(v, y_up + 0.32, f"IC ({v}k)", ha="center", fontsize=10)

                ax.vlines(v, y_down - 0.25, y_down, colors="black")
                ax.text(v, y_down - 0.32, f"IC ({v}k)", ha="center", va="top", fontsize=10)

    # ylim은 실제 라벨 y 기반으로 타이트하게
    all_y = [y_up, y_down] + [y for _, y, _ in up_items] + [y for _, y, _ in down_items]
    ymin = min(all_y) - 1.0
    ymax = max(all_y) + 1.0

    ax.set_xlim(left, right)
    ax.set_ylim(ymin, ymax)
    ax.axis("off")
    fig.tight_layout()
    return fig

# ======================================================
# 10. 2페이지: 교량 목록
# ======================================================
def draw_list_page(up_df, down_df):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    ax.text(0.05, 0.93, "영암 방향 교량 목록", fontsize=18, weight="bold")
    ax.text(0.55, 0.93, "순천 방향 교량 목록", fontsize=18, weight="bold")

    up_list = [
        f"{row['번호']}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in up_df.iterrows()
        if pd.notna(row.get(KM_COL))
    ]
    up_text = "\n".join(up_list) if up_list else "선택된 교량 없음"

    down_list = [
        f"{row['번호']}. {row['표시이름']} — {row[KM_COL]}k"
        for _, row in down_df.iterrows()
        if pd.notna(row.get(KM_COL))
    ]
    down_text = "\n".join(down_list) if down_list else "선택된 교량 없음"

    ax.text(0.05, 0.85, up_text, fontsize=14, va="top")
    ax.text(0.55, 0.85, down_text, fontsize=14, va="top")

    fig.tight_layout()
    return fig

# ======================================================
# 11. PDF 생성 버튼
# ======================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    fig_route = draw_route(
        df_up_sorted, df_down_sorted,
        ic_km=ic_km,
        label_mode=label_mode,
        close_km=close_km,
        zigzag_offset=zigzag_offset,
        layer_step=layer_step,
        line_gap=line_gap
    )
    fig_list = draw_list_page(df_up_sorted, df_down_sorted)

    st.subheader("노선도 미리보기")
    st.pyplot(fig_route, use_container_width=True)

    pdf_buffer = BytesIO()
    with PdfPages(pdf_buffer) as pdf:
        pdf.savefig(fig_route, bbox_inches="tight", pad_inches=0.25)
        pdf.savefig(fig_list, bbox_inches="tight", pad_inches=0.25)
    pdf_buffer.seek(0)

    st.download_button(
        label="📄 PDF 다운로드 (노선도 + 교량목록)",
        data=pdf_buffer,
        file_name="노선도_및_교량목록.pdf",
        mime="application/pdf"
    )












