import streamlit as st
import requests

st.set_page_config(page_title="나와 어울리는 영화는?", page_icon="🎬", layout="wide")

# -----------------------------
# TMDB 설정
# -----------------------------
GENRES = {
    "action": {"name": "액션", "id": 28},
    "comedy": {"name": "코미디", "id": 35},
    "drama": {"name": "드라마", "id": 18},
    "sf": {"name": "SF", "id": 878},
    "romance": {"name": "로맨스", "id": 10749},
    "fantasy": {"name": "판타지", "id": 14},
}
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"

def build_poster_url(poster_path: str):
    if not poster_path:
        return None
    return POSTER_BASE_URL + poster_path

@st.cache_data(show_spinner=False)
def fetch_popular_movies_by_genre(api_key: str, genre_id: int, language: str = "ko-KR", count: int = 5):
    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": api_key,
        "with_genres": genre_id,
        "language": language,
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "page": 1,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])[:count]

def analyze_genre(selected_indices):
    """
    선택지 인덱스(0~3)를 기반으로 장르 점수를 계산해 최종 장르를 결정한다.
    - 0: 로맨스/드라마 계열 -> 질문별로 로맨스/드라마로 분기
    - 1: 액션
    - 2: SF/판타지 계열 -> 질문별로 SF/판타지로 분기
    - 3: 코미디
    """
    scores = {k: 0 for k in GENRES.keys()}

    per_question_map = [
        ["drama",   "action", "fantasy", "comedy"],  # Q1
        ["drama",   "action", "sf",      "comedy"],  # Q2
        ["romance", "action", "fantasy", "comedy"],  # Q3
        ["drama",   "action", "sf",      "comedy"],  # Q4
        ["drama",   "action", "sf",      "comedy"],  # Q5
    ]

    for i, idx in enumerate(selected_indices):
        scores[per_question_map[i][idx]] += 1

    # 동점 처리 우선순위
    tie_priority = ["drama", "romance", "sf", "fantasy", "action", "comedy"]
    max_score = max(scores.values())
    tied = [k for k, v in scores.items() if v == max_score]
    tied.sort(key=lambda x: tie_priority.index(x))
    return tied[0], scores

def recommendation_reason(genre_key: str, movie: dict) -> str:
    vote = movie.get("vote_average", 0) or 0

    base = {
        "drama":   "감정선과 여운이 진한 전개를 좋아하는 성향과 잘 맞는다",
        "romance": "관계의 설렘과 감정 흐름에 몰입하는 취향과 잘 맞는다",
        "action":  "속도감 있는 전개와 시원한 쾌감을 선호하는 취향과 잘 맞는다",
        "sf":      "상상력을 자극하는 설정과 세계관을 즐기는 취향과 잘 맞는다",
        "fantasy": "현실을 벗어난 모험/세계관의 재미를 선호하는 취향과 잘 맞는다",
        "comedy":  "가볍게 웃으며 기분 전환하는 스타일과 잘 맞는다",
    }.get(genre_key, "네 취향과 잘 맞는다")

    if vote >= 7.5:
        extra = f"그리고 평점이 높은 편(⭐ {vote:.1f})이라 만족도가 높을 가능성이 크다"
    elif vote >= 6.5:
        extra = f"평점도 무난한 편(⭐ {vote:.1f})이라 편하게 보기 좋다"
    else:
        extra = f"호불호는 있을 수 있지만 인기 작품이라 한번 도전해보기 좋다(⭐ {vote:.1f})"

    return f"{base}. {extra}."

# -----------------------------
# UI
# -----------------------------
st.title("🎬 나와 어울리는 영화는?")
st.write("간단한 심리테스트로 지금의 너와 가장 잘 어울리는 영화 취향을 알아보자 😎")
st.write("아래 5개 질문에 답하고 **결과 보기**를 누르면, TMDB에서 인기 영화 5개를 추천해준다.")

st.sidebar.header("TMDB 설정")
api_key = st.sidebar.text_input("TMDB API Key", type="password", placeholder="여기에 API Key 입력")

st.divider()

# -----------------------------
# 질문/선택지 (장르명 노출 제거 버전)
# -----------------------------
QUESTIONS = [
    (
        "Q1. 완전 지친 날, 너는 어떻게 기분을 돌려?",
        [
            "A. 누군가랑 조용히 이야기하면서 마음이 정리되는 편이다",
            "B. 몸 좀 움직이거나 짜릿한 걸 해야 스트레스가 풀린다",
            "C. 현실에서 잠깐 탈출해서 다른 세계에 다녀오고 싶다",
            "D. 웃긴 거 보면서 “아 됐다” 하고 털어버린다",
        ],
    ),
    (
        "Q2. 너가 끌리는 주인공 타입은?",
        [
            "A. 상처나 사연이 있지만 결국 성장하는 사람",
            "B. 말보다 행동! 위기에서 해결해버리는 사람",
            "C. 남들이 못 보는 진실을 알아차리는 사람/특별한 존재",
            "D. 허당인데 매력 있어서 자꾸 응원하게 되는 사람",
        ],
    ),
    (
        "Q3. 여행을 간다면 너의 코스는?",
        [
            "A. 분위기 좋은 거리 걷고, 예쁜 카페 가고, 감성 사진 찍기",
            "B. 액티비티 풀코스! 서핑/등산/짚라인 같은 거 하고 싶다",
            "C. 자연경관 끝내주는 곳이나 신비로운 유적지에서 세계관 충전",
            "D. 계획은 대충! 길 가다 재밌는 거 있으면 그때그때 즐기기",
        ],
    ),
    (
        "Q4. 갑자기 큰 문제가 터졌을 때 너의 반응은?",
        [
            "A. “왜 이런 일이…” 감정부터 정리하고 나서 움직인다",
            "B. 일단 해결부터! 바로 행동하고 부딪힌다",
            "C. 원인/구조를 분석한다. 숨은 규칙이 있을 것 같다",
            "D. 일단 웃긴 말 한 번 던지고 분위기부터 살린다",
        ],
    ),
    (
        "Q5. 너가 가장 좋아하는 엔딩 느낌은?",
        [
            "A. 마음이 꽉 차면서 여운이 오래 남는 엔딩",
            "B. “와 미쳤다…” 한 방 크게 터지고 시원한 엔딩",
            "C. 반전/확장/떡밥! 상상하게 만드는 엔딩",
            "D. 끝까지 기분 좋고, 나도 모르게 미소 짓는 엔딩",
        ],
    ),
]

selected_indices = []

for i, (q, options) in enumerate(QUESTIONS, start=1):
    st.subheader(q)
    choice = st.radio(
        label="",
        options=options,
        index=None,
        key=f"q{i}",
    )
    if choice is None:
        selected_indices.append(None)
    else:
        selected_indices.append(options.index(choice))

st.divider()

# -----------------------------
# 결과 보기 버튼
# -----------------------------
if st.button("결과 보기", type="primary"):
    if not api_key:
        st.error("사이드바에 TMDB API Key를 입력해줘.")
        st.stop()

    if any(x is None for x in selected_indices):
        st.warning("아직 선택하지 않은 질문이 있다. 5개 모두 답해줘!")
        st.stop()

    with st.spinner("분석 중..."):
        # 장르 분석
        genre_key, scores = analyze_genre(selected_indices)
        genre_name = GENRES[genre_key]["name"]
        genre_id = GENRES[genre_key]["id"]

        # TMDB에서 영화 가져오기
        try:
            movies = fetch_popular_movies_by_genre(api_key, genre_id, language="ko-KR", count=5)
        except requests.HTTPError:
            st.error("TMDB 요청에 실패했다. API Key가 맞는지 확인해줘.")
            st.stop()
        except requests.RequestException:
            st.error("네트워크 문제로 TMDB에 연결하지 못했다. 잠깐 후 다시 시도해줘.")
            st.stop()

    # -----------------------------
    # 예쁜 결과 화면
    # -----------------------------
    st.markdown(f"# 당신에게 딱인 장르는: **{genre_name}**!")
    st.write("지금 너의 선택 흐름을 보면, 아래 작품들이 특히 잘 맞을 확률이 높다 👇")

    # (선택) 점수 분석 보기
    with st.expander("내 선택 분석 보기"):
        st.write(", ".join([f"{GENRES[k]['name']} {v}점" for k, v in scores.items() if v > 0]) or "점수 정보가 없다.")

    if not movies:
        st.info("추천할 영화가 없다. 다른 선택으로 다시 시도해줘.")
        st.stop()

    st.markdown("## 🎞️ 추천 영화")
    st.caption("카드를 누르면 상세 정보를 펼쳐볼 수 있다.")

    # 3열 카드 레이아웃
    cols = st.columns(3, gap="large")
    for idx, movie in enumerate(movies):
        col = cols[idx % 3]

        title = movie.get("title") or movie.get("original_title") or "제목 정보 없음"
        vote = movie.get("vote_average", 0) or 0
        overview = movie.get("overview") or "줄거리 정보가 부족하다."
        poster_url = build_poster_url(movie.get("poster_path"))
        reason = recommendation_reason(genre_key, movie)

        with col:
            # 카드처럼 보이게 컨테이너 사용
            with st.container(border=True):
                if poster_url:
                    st.image(poster_url, use_container_width=True)
                else:
                    st.write("🖼️ 포스터 없음")

                st.markdown(f"### {title}")
                st.write(f"⭐ 평점: {vote:.1f}")

                with st.expander("상세 보기"):
                    st.write(f"**줄거리**: {overview}")
                    st.write(f"**이 영화를 추천하는 이유**: {reason}")

