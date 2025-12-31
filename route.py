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
# 7. 노선도 그리기 (겹침/가독성 개선 버전)
#    - 가까운 교량은 "번호를 묶어서" 한 덩어리 라벨로 표시
#    - 마커(삼각형)는 km 위치 그대로 두되, 같은 지점 근처는 위/아래로 살짝 올려서 겹침 완화(짧은 연결선 포함)
#    - 라벨은 여러 층(level)로 배치해서 서로 겹치지 않게 함
# ======================================================
def draw_route(up_df, down_df, ic_km=None):
    fig, ax = plt.subplots(figsize=(22, 10))

    MIN_KM = 0.0
    MAX_KM = 106.8

    # ---- 튜닝 파라미터(겹치면 이것들만 조절하면 됨) ----
    GROUP_THRESHOLD_KM = 0.05   # 이 값(km) 이내면 '가까운 교량'으로 보고 번호 라벨을 묶음 (0.05km=50m)
    LABEL_MIN_GAP_KM = 0.60     # 같은 라벨 층(level)에서 x 간 최소 간격(클수록 더 많이 위로 올라감)
    LABEL_OFFSETS_UP = [0.25, 0.42, 0.60, 0.78]    # 영암 방향 라벨 층(윗라인 기준 +)
    LABEL_OFFSETS_DOWN = [-0.25, -0.42, -0.60, -0.78]  # 순천 방향 라벨 층(아랫라인 기준 -)

    MARKER_BASE = 0.08          # 마커를 라인에서 띄우는 기본 거리
    MARKER_STEP = 0.04          # 같은 그룹 내에서 마커 높이 단계
    MARKER_LEVELS = 5           # 같은 그룹에서 마커 높이 단계 수(순환)

    def compress_numbers(nums):
        """예: [4,5,6,8] -> '(4~6)\\n(8)' 형태"""
        nums = sorted({int(n) for n in nums})
        runs = []
        start = prev = None
        for n in nums:
            if start is None:
                start = prev = n
            elif n == prev + 1:
                prev = n
            else:
                runs.append((start, prev))
                start = prev = n
        if start is not None:
            runs.append((start, prev))

        lines = []
        for a, b in runs:
            if a == b:
                lines.append(f"({a})")
            elif b == a + 1:
                lines.append(f"({a})")
                lines.append(f"({b})")
            else:
                lines.append(f"({a}~{b})")
        return "\n".join(lines)

    def make_groups(df_sorted, threshold_km):
        groups = []
        current = []
        prev_km = None
        for _, row in df_sorted.iterrows():
            km = float(row[KM_COL])
            if prev_km is None or abs(prev_km - km) <= threshold_km:
                current.append(row)
            else:
                groups.append(current)
                current = [row]
            prev_km = km
        if current:
            groups.append(current)
        return groups

    def pick_label_y(x, levels, last_x_by_level):
        """가까운 라벨이 같은 층에 겹치지 않도록, 가능한 층으로 올려 배치"""
        for i, y in enumerate(levels):
            last_x = last_x_by_level.get(i)
            if last_x is None or abs(x - last_x) >= LABEL_MIN_GAP_KM:
                last_x_by_level[i] = x
                return y
        # 다 막히면 맨 위/아래층 사용
        i = len(levels) - 1
        last_x_by_level[i] = x
        return levels[i]

    def draw_direction(df_sorted, y_line, marker, label_offsets, marker_side):
        """
        marker_side:
          - 'above' : 라인 위에 마커 배치(짧은 선으로 라인에 연결)  -> 영암(윗줄, v)
          - 'below' : 라인 아래에 마커 배치(짧은 선으로 라인에 연결) -> 순천(아랫줄, ^)
        """
        last_x_by_level = {}
        groups = make_groups(df_sorted, GROUP_THRESHOLD_KM)

        for g in groups:
            kms = [float(r[KM_COL]) for r in g]
            nums = [int(r["번호"]) for r in g]

            # 라벨은 그룹의 중앙 km 기준
            x_center = float(pd.Series(kms).median())

            # 1) 마커: 각 교량은 km 위치 그대로 두고, 같은 그룹이면 위/아래로 단계적으로 띄움
            for i, km in enumerate(kms):
                level = i % MARKER_LEVELS
                if marker_side == "above":
                    y_marker = y_line + MARKER_BASE + MARKER_STEP * level
                    ax.vlines(km, y_line, y_marker, colors="black", linewidth=0.8)
                else:
                    y_marker = y_line - MARKER_BASE - MARKER_STEP * level
                    ax.vlines(km, y_marker, y_line, colors="black", linewidth=0.8)

                ax.scatter(km, y_marker, marker=marker, s=200, color="black")

            # 2) 라벨: 번호만(필요시 묶음)
            label_text = compress_numbers(nums)
            line_count = label_text.count("\n") + 1
            if line_count <= 3:
                fs = 10
            elif line_count <= 6:
                fs = 9
            else:
                fs = 8

            levels = [y_line + off for off in label_offsets]
            y_label = pick_label_y(x_center, levels, last_x_by_level)

            ax.vlines(x_center, y_line, y_label, colors="black", linewidth=1.0)
            ax.text(
                x_center,
                y_label,
                label_text,
                ha="center",
                va="bottom" if y_label >= y_line else "top",
                fontsize=fs
            )

    # ============================ 영암 방향 ============================
    y_up = 1.0
    ax.hlines(y_up, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_up + 0.55, "영암 방향 (106.8k → 0k)", fontsize=14)

    up_df_sorted = up_df.sort_values(KM_COL, ascending=False).reset_index(drop=True)
    draw_direction(
        df_sorted=up_df_sorted,
        y_line=y_up,
        marker="v",
        label_offsets=LABEL_OFFSETS_UP,
        marker_side="above"
    )

    # ============================ 순천 방향 ============================
    y_down = 0.0
    ax.hlines(y_down, MIN_KM, MAX_KM, colors="black", linewidth=2)
    ax.text(MIN_KM, y_down + 0.55, "순천 방향 (0k → 106.8k)", fontsize=14)

    down_df_sorted = down_df.sort_values(KM_COL, ascending=True).reset_index(drop=True)
    draw_direction(
        df_sorted=down_df_sorted,
        y_line=y_down,
        marker="^",
        label_offsets=LABEL_OFFSETS_DOWN,
        marker_side="below"
    )

    # ============================ 보성 IC ============================
    if ic_km is not None:
        ax.vlines(ic_km, y_up, y_up + 0.25, colors="black")
        ax.text(ic_km, y_up + 0.32, f"보성IC ({ic_km}k)", ha="center", fontsize=12)

        ax.vlines(ic_km, y_down - 0.25, y_down, colors="black")
        ax.text(ic_km, y_down - 0.32, f"보성IC ({ic_km}k)", ha="center", va="top", fontsize=12)

    # ============================
    ax.set_xlim(MIN_KM, MAX_KM)
    ax.set_ylim(-1.15, 2.15)
    ax.axis("off")
    fig.tight_layout()
    return fig

# ======================================================
# 8. 2페이지: 교량 목록 (이름 + km 표시)
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

    # (선택) 메모리 누수 방지
    plt.close(fig_route)
    plt.close(fig_list)

    st.download_button(
        label="📄 PDF 다운로드 (노선도 + 교량목록)",
        data=pdf_buffer,
        file_name="노선도_및_교량목록.pdf",
        mime="application/pdf"
    )








