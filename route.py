# app.py (또는 streamlit_app.py)
import os
from io import BytesIO

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages


# =========================
# 0) 설정
# =========================
DATA_PATH = "data.csv"
FONT_PATH = "fonts/NanumGothic-Regular.ttf"

NAME_COL = "name"
KM_COL = "이정(km)"
TYPE_COL = "종별구분"

DISPLAY_NAME_COL = "표시이름"


# =========================
# 1) 기본 유틸
# =========================
def setup_korean_font(font_path: str) -> None:
    """한글 폰트 등록(있으면)"""
    if not os.path.exists(font_path):
        return
    fm.fontManager.addfont(font_path)
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams["font.family"] = font_name


@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    # km는 숫자로 통일(문자 섞여 있으면 NaN 처리)
    if KM_COL in df.columns:
        df[KM_COL] = pd.to_numeric(df[KM_COL], errors="coerce")

    return df


def make_display_name(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.replace(r"\(영암\)", "", regex=True)
        .str.replace(r"\(순천\)", "", regex=True)
        .str.strip()
    )


def split_direction_masks(df: pd.DataFrame):
    has_yeongam = df[NAME_COL].astype(str).str.contains("영암", na=False)
    has_suncheon = df[NAME_COL].astype(str).str.contains("순천", na=False)
    neutral = ~(has_yeongam | has_suncheon)
    return has_yeongam, has_suncheon, neutral


def assign_numbers(df: pd.DataFrame, ascending: bool) -> pd.DataFrame:
    out = df.sort_values(KM_COL, ascending=ascending).reset_index(drop=True).copy()
    out["번호"] = out.index + 1
    return out


def find_first_ic_km(df: pd.DataFrame) -> float | None:
    """종별구분에 IC가 들어간 첫 행 km"""
    if TYPE_COL not in df.columns or KM_COL not in df.columns:
        return None
    ic_rows = df[df[TYPE_COL].astype(str).str.contains("IC", na=False)]
    if ic_rows.empty:
        return None
    km = ic_rows.iloc[0][KM_COL]
    return float(km) if pd.notna(km) else None


# =========================
# 2) 노선도(1페이지) 그리기
#    - 텍스트는 "번호만" 찍도록 고정
# =========================
def draw_route(up_df: pd.DataFrame, down_df: pd.DataFrame, ic_km: float | None = None) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(22, 10))

    # x축 범위 자동 계산(데이터 없으면 기본값)
    all_km = pd.concat([up_df.get(KM_COL, pd.Series(dtype=float)),
                        down_df.get(KM_COL, pd.Series(dtype=float))], ignore_index=True)
    if all_km.dropna().empty:
        min_km, max_km = 0.0, 106.8
    else:
        min_km = float(all_km.min(skipna=True))
        max_km = float(all_km.max(skipna=True))

    y_up = 1.0
    y_down = 0.0

    # 위/아래 라인 (텍스트 라벨은 일부러 안 찍음: "1페이지는 번호만")
    ax.hlines(y=y_up, xmin=min_km, xmax=max_km)
    ax.hlines(y=y_down, xmin=min_km, xmax=max_km)

    def flush_group(group_rows, y_base: float, marker: str, x_start_sign: int):
        """
        가까운 km끼리 묶인 그룹을 텍스트 겹침 줄이면서 찍기
        ※ 여기서 label은 무조건 (번호)만!
        """
        toggle = 1
        sign = x_start_sign

        for row in group_rows:
            km = row[KM_COL]
            if pd.isna(km):
                continue

            label = f"({int(row['번호'])})"  # ✅ 1페이지: 번호만 강제

            # y 지그재그
            y_text = (y_base - 0.18) if (toggle % 2 == 1) else (y_base + 0.40)

            # x 좌우로 퍼뜨리기
            offset_scale = (toggle + 1) // 2
            x_offset = sign * (0.8 * offset_scale)

            toggle += 1
            sign *= -1

            ax.scatter(km, y_base, marker=marker)
            ax.text(
                km + x_offset,
                y_text,
                label,
                rotation=90,
                ha="center",
                va="center",
                fontsize=9,
            )

    def iter_groups(sorted_df: pd.DataFrame, threshold_km: float = 0.31):
        group = []
        prev_km = None

        for _, r in sorted_df.iterrows():
            km = r[KM_COL]
            if pd.isna(km):
                continue

            if prev_km is None:
                group = [r]
            elif abs(prev_km - km) < threshold_km:
                group.append(r)
            else:
                yield group
                group = [r]
            prev_km = km

        if group:
            yield group

    # 영암(내림차순): 아래 방향 삼각형
    up_sorted = up_df.sort_values(KM_COL, ascending=False)
    for g in iter_groups(up_sorted, threshold_km=0.31):
        flush_group(g, y_base=y_up, marker="v", x_start_sign=-1)

    # 순천(오름차순): 위 방향 삼각형
    down_sorted = down_df.sort_values(KM_COL, ascending=True)
    for g in iter_groups(down_sorted, threshold_km=0.31):
        flush_group(g, y_base=y_down, marker="^", x_start_sign=+1)

    # IC는 "선만" 표시(텍스트는 안 찍음: 1페이지 번호만)
    if ic_km is not None and (min_km <= ic_km <= max_km):
        ax.vlines(ic_km, y_up, y_up + 0.25)
        ax.vlines(ic_km, y_down - 0.25, y_down)

    ax.set_xlim(min_km, max_km)
    ax.set_ylim(-1.0, 2.0)
    ax.axis("off")
    fig.tight_layout()
    return fig


# =========================
# 3) 목록(2페이지) 그리기
#    - 이름/노선명은 여기서만 보여줌
# =========================
def draw_list_page(up_df: pd.DataFrame, down_df: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    ax.text(0.05, 0.92, "영암 방향 교량 목록", fontsize=14, weight="bold")
    ax.text(0.55, 0.92, "순천 방향 교량 목록", fontsize=14, weight="bold")

    def build_lines(df: pd.DataFrame) -> str:
        if df.empty:
            return "선택된 교량 없음"
        lines = []
        for _, r in df.iterrows():
            km = r[KM_COL]
            km_txt = f"{km:.2f}k" if pd.notna(km) else "km 미상"
            lines.append(f"{int(r['번호'])}. {r[DISPLAY_NAME_COL]} — {km_txt}")  # ✅ 2페이지: 이름 표시
        return "\n".join(lines)

    ax.text(0.05, 0.88, build_lines(up_df), fontsize=10, va="top")
    ax.text(0.55, 0.88, build_lines(down_df), fontsize=10, va="top")

    fig.tight_layout()
    return fig


def make_pdf(fig1: plt.Figure, fig2: plt.Figure) -> BytesIO:
    buf = BytesIO()
    with PdfPages(buf) as pdf:
        pdf.savefig(fig1, bbox_inches="tight")
        pdf.savefig(fig2, bbox_inches="tight")
    buf.seek(0)
    return buf


# =========================
# 4) Streamlit 메인
# =========================
def main():
    setup_korean_font(FONT_PATH)

    st.title("거리비례 노선도 생성기")

    df = load_data(DATA_PATH).copy()
    df[DISPLAY_NAME_COL] = make_display_name(df[NAME_COL])

    has_yeongam, has_suncheon, neutral = split_direction_masks(df)

    # 옵션(중립은 양쪽에 포함)
    yeongam_options = df[has_yeongam | neutral][NAME_COL].dropna().unique().tolist()
    suncheon_options = df[has_suncheon | neutral][NAME_COL].dropna().unique().tolist()

    st.sidebar.header("교량 선택")
    selected_yeongam = st.sidebar.multiselect("영암 방향에서 표시할 교량", yeongam_options)
    selected_suncheon = st.sidebar.multiselect("순천 방향에서 표시할 교량", suncheon_options)
    st.sidebar.caption("아무것도 선택하지 않으면 전체 교량이 자동으로 표시됩니다.")

    # 선택 있으면 선택만 / 없으면 기본 전체
    up_base = df[has_yeongam | neutral]
    down_base = df[has_suncheon | neutral]

    up_df = df[df[NAME_COL].isin(selected_yeongam)] if selected_yeongam else up_base
    down_df = df[df[NAME_COL].isin(selected_suncheon)] if selected_suncheon else down_base

    # 번호 부여(방향별 정렬 기준)
    up_sorted = assign_numbers(up_df, ascending=False)     # 영암: 큰 km부터
    down_sorted = assign_numbers(down_df, ascending=True)  # 순천: 작은 km부터

    # IC 위치(있으면 선만 표시)
    ic_km = find_first_ic_km(df)

    if st.button("노선도 생성 및 PDF 다운로드"):
        fig_route = draw_route(up_sorted, down_sorted, ic_km)
        fig_list = draw_list_page(up_sorted, down_sorted)

        st.subheader("노선도 미리보기(1페이지: 번호만)")
        st.pyplot(fig_route)

        pdf_buf = make_pdf(fig_route, fig_list)

        # 메모리 누적 방지
        plt.close(fig_route)
        plt.close(fig_list)

        st.download_button(
            label="PDF 다운로드",
            data=pdf_buf,
            file_name="노선도_및_교량목록.pdf",
            mime="application/pdf",
        )


if __name__ == "__main__":
    main()















