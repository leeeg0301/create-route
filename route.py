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
# 1. 한글 폰트 설정 (fonts/NanumGothic-Regular.ttf 있으면 적용)
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

# 옵션(선택 목록)
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


# ======================================================
# 5. 선택된 교량 데이터 정리 + 번호 매기기
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
ic_list = []
if not ic_rows.empty and KM_COL in ic_rows.columns:
    ic_rows = ic_rows.dropna(subset=[KM_COL])
    # IC 이름이 name에 있으면 표시이름 쓰고, 없으면 "IC"
    for _, r in ic_rows.iterrows():
        ic_list.append({"name": str(r.get("표시이름", "IC")), "km": float(r[KM_COL])})
ic_km = [x["km"] for x in ic_list] if ic_list else None


# ======================================================
# 7. 노선도 그리기 (겹침 자동 회피: 레인 배치)
# ======================================================
def _bbox_data(ax, artist, renderer):
    """artist bbox를 data 좌표계 bbox로 변환"""
    bb = artist.get_window_extent(renderer=renderer)
    return bb.transformed(ax.transData.inverted())


def _overlaps(bb, occupied, pad_x=0.10, pad_y=0.05):
    """bbox 겹침 체크(패딩 포함)"""
    for obb in occupied:
        if (bb.x0 - pad_x < obb.x1 and bb.x1 + pad_x > obb.x0 and
            bb.y0 - pad_y < obb.y1 and bb.y1 + pad_y > obb.y0):
            return True
    return False


def _place_label_lanes(fig, ax, x, y_base, text, rotation, fontsize,
                       occupied_bboxes, lane_step=0.60, max_lanes=10, lane_sign=+1):
    """
    라벨이 겹치면 y를 레인 단위로 (+)올리거나 (-)내리면서 빈 자리 찾기
    """
    t = ax.text(
        x, y_base, text,
        rotation=rotation, ha="center", va="center",
        fontsize=fontsize
    )

    renderer = fig.canvas.get_renderer()

    for lane in range(max_lanes + 1):
        y = y_base + lane_sign * lane * lane_step
        t.set_position((x, y))
        bb = _bbox_data(ax, t, renderer)
        if not _overlaps(bb, occupied_bboxes):
            occupied_bboxes.append(bb)
            return

    # 끝까지 겹치면 마지막 위치로 둠
    bb = _bbox_data(ax, t, renderer)
    occupied_bboxes.append(bb)


def draw_route(up_df, down_df, ic_km=None, label_mode="번호만"):
    fig, ax = plt.subplots(figsize=(22, 10))

    MIN_KM = 0
    MAX_KM = 106.8

    # 선택 데이터 기반으로 x 범위 자동 조절(너무 좁으면 최소폭 유지)
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

    # 레인 파라미터(라벨 많아도 잘리지 않게 ylim도 같이 늘림)
    lane_step = 0.60
    max_lanes = 10

    y_up = 2.5
    y_down = 0.0

    ax.hlines(y_up, left, right, colors="black", linewidth=2)
    ax.text(left, y_up + 0.6, "영암 방향 (큰 km → 작은 km)", fontsize=14)

    ax.hlines(y_down, left, right, colors="black", linewidth=2)
    ax.text(left, y_down + 0.6, "순천 방향 (작은 km → 큰 km)", fontsize=14)

    # bbox 계산을 위해 1회 draw
    fig.canvas.draw()

    # 동일 km 마커 지터(겹침 방지)용
    def km_key(v):
        return round(float(v), 2)

    up_dup = {}
    down_dup = {}

    def make_label(row):
        num = row.get("표시번호", "")
        name = row.get("표시이름", "")
        km = row.get(KM_COL, "")
        if label_mode == "번호만":
            return f"{num}"
        if label_mode == "짧게":
            name_s = str(name)
            short = (name_s[:6] + "…") if len(name_s) > 7 else name_s
            return f"{num}\n{short}"
        return f"{num}\n{name}\n({km}k)"

    # ================= 영암(큰→작) =================
    occupied_up = []
    up_sorted = up_df.sort_values(KM_COL, ascending=False).reset_index(drop=True)

    for _, row in up_sorted.iterrows():
        if pd.isna(row.get(KM_COL)):
            continue

        km = float(row[KM_COL])
        key = km_key(km)
        up_dup[key] = up_dup.get(key, 0) + 1
        jitter = (up_dup[key] - 1) * 0.08  # 0.08km(80m) 정도만 살짝
        x = km + jitter

        ax.scatter(x, y_up, marker="v", s=220, color="black")

        _place_label_lanes(
            fig, ax, x, y_up + 0.35, make_label(row),
            rotation=90, fontsize=11,
            occupied_bboxes=occupied_up,
            lane_step=lane_step, max_lanes=max_lanes, lane_sign=+1
        )

    # ================= 순천(작→큰) =================
    occupied_down = []
    down_sorted = down_df.sort_values(KM_COL, ascending=True).reset_index(drop=True)

    for _, row in down_sorted.iterrows():
        if pd.isna(row.get(KM_COL)):
            continue

        km = float(row[KM_COL])
        key = km_key(km)
        down_dup[key] = down_dup.get(key, 0) + 1
        jitter = (down_dup[key] - 1) * 0.08
        x = km + jitter

        ax.scatter(x, y_down, marker="^", s=220, color="black")

        _place_label_lanes(
            fig, ax, x, y_down - 0.35, make_label(row),
            rotation=90, fontsize=11,
            occupied_bboxes=occupied_down,
            lane_step=lane_step, max_lanes=max_lanes, lane_sign=-1
        )

    # ================= IC 표시(여러 개 지원) =================
    if ic_km is not None:
        if isinstance(ic_km, (list, tuple, pd.Series)):
            ic_vals = [float(v) for v in ic_km]
        else:
            ic_vals = [float(ic_km)]

        for v in ic_vals:
            if left <= v <= right:
                # 위쪽
                ax.vlines(v, y_up, y_up + 0.25, colors="black")
                ax.text(v, y_up + 0.32, f"IC ({v}k)", ha="center", fontsize=12)
                # 아래쪽
                ax.vlines(v, y_down - 0.25, y_down, colors="black")
                ax.text(v, y_down - 0.32, f"IC ({v}k)", ha="center", va="top", fontsize=12)

    ax.set_xlim(left, right)
    ax.set_ylim(
        y_down - (max_lanes * lane_step) - 1.0,
        y_up + (max_lanes * lane_step) + 1.2
    )
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
        if pd.notna(row.get(KM_COL))
    ]
    up_text = "\n".join(up_list) if up_list else "선택된 교량 없음"

    # 순천
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
# 9. PDF 생성 버튼
# ======================================================
if st.button("노선도 생성 및 PDF 다운로드"):
    fig_route = draw_route(df_up_sorted, df_down_sorted, ic_km, label_mode=label_mode)
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














