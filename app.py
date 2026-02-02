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

def build_poster_url(poster_path: str) -> str | None:
    if not poster_path:
        return None
    return POSTER_BASE_URL + poster_path

@st.cache_data(show_spinner=False)
def fetch_popular_movies_by_genre(api_key: str, genre_id: int, language: str = "ko-KR", count: int = 5):
    """
    TMDB discover API로 특정 장르의 인기 영화 목록을 가져온다.
    """
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
    results = data.get("results", [])[:count]
    return results

def analyze_genre(selected_answers):
    """
    사용자 답변을 분석해서 최종 장르를 결정한다.
    - 각 질문은 4개 선택지(로맨스/드라마, 액션/어드벤처, SF/판타지, 코미디)지만
      결과는 TMDB 장르(드라마/로맨스/SF/판타지/액션/코미디) 중 하나로 뽑는다.
    """
    scores = {k: 0 for k in GENRES.keys()}

    # 질문별로 (A,B,C,D) 선택이 어떤 장르로 더 기운다고 볼지 약간 세분화해둠
    # - A(로맨스/드라마): 주로 드라마지만 Q3은 로맨스 쪽으로 가중
    # - C(SF/판타지): 질문 성격에 따라 SF/판타지로 분기
    per_question_map = [
        ["drama",   "action", "fantasy", "comedy"],  # Q1
        ["drama",   "action", "sf",      "comedy"],  # Q2
        ["romance", "action", "fantasy", "comedy"],  # Q3
        ["drama",   "action", "sf",      "comedy"],  # Q4
        ["drama",   "action", "sf",      "comedy"],  # Q5
    ]

    for i, ans_index in enumerate(selected_answers):
        genre_key = per_question_map[i][ans_index]
        scores[genre_key] += 1

    # 동점이면 우선순위로 결정(드라마/로맨스/SF/판타지/액션/코미디)
    tie_priority = ["drama", "romance", "sf", "fantasy", "action", "comedy"]
    max_score = max(scores.values())
    tied = [k for k, v in scores.items() if v == max_score]
    tied.sort(key=lambda x: tie_priority.index(x))

    return tied[0], scores

def recommendation_reason(genre_key: str, movie: dict) -> str:
    """
    '이 영화를 추천하는 이유'를 간단히 생성한다.
    """
    vote = movie.get("vote_average", 0) or 0
    popularity_hint = "인기 순으로 많이 보는 작품"  # discover 기본이 popularity.desc라서
    base = {
        "drama":   "감정선이 깊고 여운이 남는 전개가 강점이라서",
        "romance": "관계의 설렘과 감정 흐름을 중심으로 몰입하기 좋아서",
        "action":  "속도감 있는 전개와 시원한 액션/모험 감각이 살아있어서",
        "sf":      "상상력을 자극하는 설정과 세계관 몰입도가 좋아서",
        "fantasy": "현실을 벗어난 세계관과 모험의 재미가 확실해서",
        "comedy":  "가볍게 웃으면서 보기 좋은 포인트가 많아서",
    }.get(genre_key, "네 취향과 잘 맞는 결이라서")

    if vote >= 7.5:
        extra = f"게다가 평점이 높다(평점 {vote:.1f})는 점도 추천 이유다"
    elif vote >= 6.5:
        extra = f"평점도 무난한 편(평점 {vote:.1f})이라 가볍게 도전하기 좋다"
    else:
        extra = f"호불호는 있을 수 있지만, {popularity_hint}라서 한 번쯤 보기 좋다"

    return f"{base}. {extra}."

# -----------------------------
# UI
# -----------------------------
st.title("🎬 나와 어울리는 영화는?")
st.write("간단한 심리테스트로 지금의 너와 가장 잘 어울리는 영화 취향을 알아보자 😎")
st.write("아래 5개 질문에 답하고 **결과 보기**를 누르면, TMDB에서 인기 영화 5개를 추천해준다.")

st.sidebar.header("TMDB 설정")
api_key = st.sidebar.text_input("TMDB API Key", type="password", placeholder="여기에 API Key 입력")
st.sidebar.caption("키는 화면에 노출되지 않게 비밀번호 형태로 입력받는다.")

st.divider()

# 질문/선택지 (사용자에게 보이는 텍스트는 이전과 동일)
QUESTIONS = [
    ("Q1. 완전 지친 날, 너는 어떻게 기분을 돌려?",
     [
         "A. 누군가랑 조용히 이야기하면서 마음이 정리되는 편이다 (로맨스/드라마)",
         "B. 몸 좀 움직이거나 짜릿한 걸 해야 스트레스가 풀린다 (액션/어드벤처)",
         "C. 현실에서 잠깐 탈출해서 다른 세계에 다녀오고 싶다 (SF/판타지)",
         "D. 웃긴 거 보면서 “아 됐다” 하고 털어버린다 (코미디)",
     ]),
    ("Q2. 너가 끌리는 주인공 타입은?",
     [
         "A. 상처나 사연이 있지만 결국 성장하는 사람 (로맨스/드라마)",
         "B. 말보다 행동! 위기에서 해결해버리는 사람 (액션/어드벤처)",
         "C. 남들이 못 보는 진실을 알아차리는 사람/특별한 존재 (SF/판타지)",
         "D. 허당인데 매력 있어서 자꾸 응원하게 되는 사람 (코미디)",
     ]),
    ("Q3. 여행을 간다면 너의 코스는?",
     [
         "A. 분위기 좋은 거리 걷고, 예쁜 카페 가고, 감성 사진 찍기 (로맨스/드라마)",
         "B. 액티비티 풀코스! 서핑/등산/짚라인 같은 거 하고 싶다 (액션/어드벤처)",
         "C. 자연경관 끝내주는 곳이나 신비로운 유적지에서 세계관 충전 (SF/판타지)",
         "D. 계획은 대충! 길 가다 재밌는 거 있으면 그때그때 즐기기 (코미디)",
     ]),
    ("Q4. 갑자기 큰 문제가 터졌을 때 너의 반응은?",
     [
         "A. “왜 이런 일이…” 감정부터 정리하고 나서 움직인다 (로맨스/드라마)",
         "B. 일단 해결부터! 바로 행동하고 부딪힌다 (액션/어드벤처)",
         "C. 원인/구조를 분석한다. 숨은 규칙이 있을 것 같다 (SF/판타지)",
         "D. 일단 웃긴 말 한 번 던지고 분위기부터 살린다 (코미디)",
     ]),
    ("Q5. 너가 가장 좋아하는 엔딩 느낌은?",
     [
         "A. 마음이 꽉 차면서 여운이 오래 남는 엔딩 (로맨스/드라마)",
         "B. “와 미쳤다…” 한 방 크게 터지고 시원한 엔딩 (액션/어드벤처)",
         "C. 반전/확장/떡밥! 상상하게 만드는 엔딩 (SF/판타지)",
         "D. 끝까지 기분 좋고, 나도 모르게 미소 짓는 엔딩 (코미디)",
     ]),
]

selected_indices = []

for i, (q, options) in enumerate(QUESTIONS, start=1):
    st.subheader(q)
    choice = st.radio(
        label="",
        options=options,
        index=None,  # 선택 안 한 상태로 시작 (Streamlit 최신 버전 기준)
        key=f"q{i}",
    )
    if choice is None:
        selected_indices.append(None)
    else:
        selected_indices.append(options.index(choice))

st.divider()

if st.button("결과 보기", type="primary"):
    # 기본 검증
    if not api_key:
        st.error("사이드바에 TMDB API Key를 먼저 입력해줘.")
        st.stop()

    if any(x is None for x in selected_indices):
        st.warning("아직 선택하지 않은 질문이 있다. 5개 모두 답해줘!")
        st.stop()

    with st.spinner("분석 중..."):
        # 1) 장르 분석
        genre_key, scores = analyze_genre(selected_indices)
        genre_name = GENRES[genre_key]["name"]
        genre_id = GENRES[genre_key]["id"]

        # 2) TMDB에서 영화 가져오기
        try:
            movies = fetch_popular_movies_by_genre(api_key, genre_id, language="ko-KR", count=5)
        except requests.HTTPError as e:
            st.error("TMDB 요청에 실패했다. API Key가 맞는지, 사용량 제한에 걸린 건 아닌지 확인해줘.")
            st.stop()
        except requests.RequestException:
            st.error("네트워크 문제로 TMDB에 연결하지 못했다. 잠깐 후 다시 시도해줘.")
            st.stop()

    # 결과 표시
    st.success(f"너에게 가장 잘 맞는 장르는 **{genre_name}** 쪽이다!")

    # (선택) 점수도 보여주기
    with st.expander("내 선택 분석 보기"):
        score_text = ", ".join([f"{GENRES[k]['name']} {v}점" for k, v in scores.items() if v > 0])
        st.write(score_text if score_text else "점수 정보가 없다.")

    if not movies:
        st.info("추천할 영화가 없다. 다른 장르로 다시 시도해줘.")
        st.stop()

    st.subheader("🎞️ 추천 영화 5개 (TMDB 인기 기준)")
    st.caption("포스터/제목/평점/줄거리 + 추천 이유를 보여준다.")

    for movie in movies:
        title = movie.get("title") or movie.get("original_title") or "제목 정보 없음"
        overview = movie.get("overview") or "줄거리 정보가 부족하다."
        vote = movie.get("vote_average", 0) or 0
        poster_url = build_poster_url(movie.get("poster_path"))

        reason = recommendation_reason(genre_key, movie)

        st.markdown("---")
        cols = st.columns([1, 3], gap="large")

        with cols[0]:
            if poster_url:
                st.image(poster_url, use_container_width=True)
            else:
                st.write("🖼️ 포스터 없음")

        with cols[1]:
            st.markdown(f"### {title}")
            st.write(f"⭐ 평점: {vote:.1f}")
            st.write(f"**줄거리**: {overview}")
            st.write(f"**이 영화를 추천하는 이유**: {reason}")

