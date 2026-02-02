import math
import requests
import streamlit as st
from contextlib import contextmanager

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
ID_TO_KEY = {v["id"]: k for k, v in GENRES.items()}

POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"

# 장르별 성격(대략값): light(가벼움), pace(속도감), escape(현실탈출)
GENRE_TRAITS = {
    "drama":   {"light": 0.20, "pace": 0.35, "escape": 0.20},
    "romance": {"light": 0.45, "pace": 0.40, "escape": 0.25},
    "action":  {"light": 0.55, "pace": 0.85, "escape": 0.45},
    "sf":      {"light": 0.45, "pace": 0.60, "escape": 0.95},
    "fantasy": {"light": 0.55, "pace": 0.60, "escape": 0.90},
    "comedy":  {"light": 0.95, "pace": 0.60, "escape": 0.35},
}

# 베이지안 평균 파라미터(간단 신뢰도 보정)
BAYES_C = 6.8   # 전체 평균 평점(대략)
BAYES_M = 500   # 신뢰 임계 투표수(클수록 표본 적은 영화가 평균으로 끌림)

# -----------------------------
# 유틸/캐시
# -----------------------------
def build_poster_url(poster_path: str):
    if not poster_path:
        return None
    return POSTER_BASE_URL + poster_path

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def safe_year(release_date: str):
    if not release_date:
        return None
    try:
        return int(release_date[:4])
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def tmdb_discover(api_key: str, with_genres: str, language: str = "ko-KR", page: int = 1):
    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": api_key,
        "with_genres": with_genres,
        "language": language,
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "page": page,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])

@st.cache_data(show_spinner=False)
def tmdb_recommendations(api_key: str, movie_id: int, language: str = "ko-KR", page: int = 1):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/recommendations"
    params = {"api_key": api_key, "language": language, "page": page}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])

@st.cache_data(show_spinner=False)
def tmdb_similar(api_key: str, movie_id: int, language: str = "ko-KR", page: int = 1):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/similar"
    params = {"api_key": api_key, "language": language, "page": page}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])

@contextmanager
def card_container():
    """Streamlit 버전에 따라 border 지원이 없을 수 있어서 안전하게 처리한다."""
    try:
        with st.container(border=True):
            yield
    except TypeError:
        with st.container():
            yield

# -----------------------------
# 1) 답변 -> 취향 벡터(장르 가중치 + 무드 축)
# -----------------------------
def profile_from_answers(selected_indices):
    """
    selected_indices: 각 질문의 선택지 인덱스(0~3)
    반환:
      - genre_w: 장르 가중치(dict)
      - axes: light/pace/escape (0~1)
    """
    genre_w = {k: 0.0 for k in GENRES.keys()}

    # 질문별로 0(A)/1(B)/2(C)/3(D)가 어느 장르로 더 기운지(세분화)
    per_question_map = [
        ["drama",   "action", "fantasy", "comedy"],  # Q1
        ["drama",   "action", "sf",      "comedy"],  # Q2
        ["romance", "action", "fantasy", "comedy"],  # Q3
        ["drama",   "action", "sf",      "comedy"],  # Q4
        ["drama",   "action", "sf",      "comedy"],  # Q5
    ]

    # 각 선택지(0~3)가 무드 축에 주는 영향(대략)
    # 0(A)=감정/여운(무거움, 느림, 현실쪽)
    # 1(B)=짜릿(가벼움 약간, 빠름, 현실/탈출 중간)
    # 2(C)=세계관(탈출 높음)
    # 3(D)=웃김(가벼움 높음)
    axes = {"light": 0.5, "pace": 0.5, "escape": 0.5}

    axis_delta = {
        0: {"light": -0.12, "pace": -0.08, "escape": -0.06},
        1: {"light": +0.05, "pace": +0.18, "escape": +0.05},
        2: {"light": +0.03, "pace": +0.05, "escape": +0.22},
        3: {"light": +0.20, "pace": +0.02, "escape": +0.02},
    }

    for qi, choice_idx in enumerate(selected_indices):
        g = per_question_map[qi][choice_idx]
        genre_w[g] += 1.0

        d = axis_delta[choice_idx]
        axes["light"] += d["light"]
        axes["pace"] += d["pace"]
        axes["escape"] += d["escape"]

    # 0~1로 클램프
    axes = {k: clamp(v, 0.0, 1.0) for k, v in axes.items()}

    # 0점 방지(혹시라도)
    total = sum(genre_w.values())
    if total <= 0:
        for k in genre_w:
            genre_w[k] = 1.0
        total = sum(genre_w.values())

    # 정규화(합이 1이 되게)
    genre_w = {k: v / total for k, v in genre_w.items()}

    return {"genre_w": genre_w, "axes": axes}

def apply_feedback_adjustments(base_profile, fb):
    """
    (8) 좋아요/별로예요 피드백을 프로필에 반영한다.
    fb: {"genre_adj":{...}, "axis_adj":{...}}
    """
    genre_w = base_profile["genre_w"].copy()
    axes = base_profile["axes"].copy()

    # 장르 가중치에 가산/감산 적용
    genre_adj = fb.get("genre_adj", {})
    for k, delta in genre_adj.items():
        genre_w[k] = max(0.0, genre_w.get(k, 0.0) + delta)

    # 다시 정규화
    s = sum(genre_w.values())
    if s <= 0:
        # 다 0이 되면 베이스로 복구
        genre_w = base_profile["genre_w"].copy()
    else:
        genre_w = {k: v / s for k, v in genre_w.items()}

    # 축 보정
    axis_adj = fb.get("axis_adj", {})
    for k, delta in axis_adj.items():
        axes[k] = clamp(axes.get(k, 0.5) + delta, 0.0, 1.0)

    return {"genre_w": genre_w, "axes": axes}

# -----------------------------
# 3) 품질 점수(베이지안) + 4) 재랭킹 스코어
# -----------------------------
def bayesian_rating(vote_average: float, vote_count: int, C=BAYES_C, m=BAYES_M):
    v = max(0, int(vote_count or 0))
    R = float(vote_average or 0.0)
    return (v / (v + m)) * R + (m / (v + m)) * C if (v + m) > 0 else C

def movie_trait_vector(movie):
    """영화 장르 id들을 기반으로 trait 평균을 만든다."""
    gids = movie.get("genre_ids", []) or []
    keys = [ID_TO_KEY.get(g) for g in gids if ID_TO_KEY.get(g) in GENRE_TRAITS]
    keys = [k for k in keys if k]
    if not keys:
        return {"light": 0.5, "pace": 0.5, "escape": 0.5}
    light = sum(GENRE_TRAITS[k]["light"] for k in keys) / len(keys)
    pace  = sum(GENRE_TRAITS[k]["pace"] for k in keys) / len(keys)
    esc   = sum(GENRE_TRAITS[k]["escape"] for k in keys) / len(keys)
    return {"light": light, "pace": pace, "escape": esc}

def trait_alignment(user_axes, movie_axes):
    # 0~1 (1이 더 잘 맞음)
    dist = math.sqrt(
        (user_axes["light"] - movie_axes["light"]) ** 2 +
        (user_axes["pace"] - movie_axes["pace"]) ** 2 +
        (user_axes["escape"] - movie_axes["escape"]) ** 2
    ) / math.sqrt(3)
    return 1.0 - dist

def genre_match_score(user_genre_w, movie):
    gids = movie.get("genre_ids", []) or []
    score = 0.0
    for gid in gids:
        k = ID_TO_KEY.get(gid)
        if k:
            score += user_genre_w.get(k, 0.0)
    # 최대 1을 넘지 않게(장르 여러 개면 합이 커질 수 있음)
    return clamp(score, 0.0, 1.0)

def completeness_penalty(movie):
    pen = 0.0
    if not movie.get("poster_path"):
        pen += 0.20
    if not (movie.get("overview") or "").strip():
        pen += 0.15
    return pen

def composite_score(profile, movie):
    """
    (4) 재랭킹 점수: 취향 매칭 + 품질(보정 평점) + 무드 매칭 + 약간의 인기
    """
    user_genre_w = profile["genre_w"]
    user_axes = profile["axes"]

    # 취향(장르) 매칭
    gmatch = genre_match_score(user_genre_w, movie)

    # 무드 매칭
    maxes = movie_trait_vector(movie)
    align = trait_alignment(user_axes, maxes)

    # 품질(베이지안) 보정 점수
    R = float(movie.get("vote_average", 0) or 0)
    v = int(movie.get("vote_count", 0) or 0)
    bayes = bayesian_rating(R, v)  # 0~10
    bayes_norm = clamp(bayes / 10.0, 0.0, 1.0)

    # 인기(가볍게)
    pop = float(movie.get("popularity", 0) or 0)
    pop_norm = clamp(math.log1p(pop) / math.log1p(1000), 0.0, 1.0)

    pen = completeness_penalty(movie)

    # 가중치(취향 중심)
    score = (
        0.50 * gmatch +
        0.25 * align +
        0.20 * bayes_norm +
        0.05 * pop_norm -
        pen
    )
    return score

# -----------------------------
# 5) 다양성 선택(MMR)
# -----------------------------
def genre_jaccard(a, b):
    ga = set(a.get("genre_ids", []) or [])
    gb = set(b.get("genre_ids", []) or [])
    if not ga and not gb:
        return 0.0
    inter = len(ga & gb)
    union = len(ga | gb)
    return inter / union if union else 0.0

def year_similarity(a, b):
    ya = safe_year(a.get("release_date", ""))
    yb = safe_year(b.get("release_date", ""))
    if ya is None or yb is None:
        return 0.0
    d = abs(ya - yb)
    return clamp(1.0 - (d / 10.0), 0.0, 1.0)  # 10년 이상 차이면 0

def similarity(a, b):
    # 장르 유사도 + 연도 유사도
    return 0.75 * genre_jaccard(a, b) + 0.25 * year_similarity(a, b)

def mmr_select(candidates, base_scores, k=5, lam=0.75):
    """
    lam: 1에 가까울수록 '점수' 우선, 0에 가까울수록 '다양성' 우선
    """
    selected = []
    remaining = candidates[:]

    # 첫 개는 그냥 최고점
    remaining.sort(key=lambda m: base_scores.get(m["id"], -1e9), reverse=True)
    if not remaining:
        return selected
    selected.append(remaining.pop(0))

    while remaining and len(selected) < k:
        best = None
        best_mmr = -1e9
        for m in remaining:
            rel = base_scores.get(m["id"], -1e9)
            sim = max(similarity(m, s) for s in selected) if selected else 0.0
            mmr = lam * rel - (1 - lam) * sim
            if mmr > best_mmr:
                best_mmr = mmr
                best = m
        if best is None:
            break
        selected.append(best)
        remaining = [x for x in remaining if x["id"] != best["id"]]
    return selected

# -----------------------------
# 2) 후보 생성 + 3) 추천망 확장 + 4/5) 재랭킹/다양성
# -----------------------------
def collect_candidates(api_key: str, profile, per_call=40):
    """
    (2) discover로 넓게 후보 생성
    - 상위 2~3개 장르 단독 + (가능하면) 혼합 장르도 호출
    """
    # 선호 장르 상위 3개
    top = sorted(profile["genre_w"].items(), key=lambda x: x[1], reverse=True)[:3]
    top_keys = [k for k, _ in top]
    top_ids = [GENRES[k]["id"] for k in top_keys]

    candidates = {}
    # 단독 장르
    for gid in top_ids:
        results = tmdb_discover(api_key, str(gid), language="ko-KR", page=1)[:per_call]
        for m in results:
            if m.get("id"):
                candidates[m["id"]] = m

    # 혼합 장르(상위 2개, 상위 3개)
    if len(top_ids) >= 2:
        combo = f"{top_ids[0]},{top_ids[1]}"
        results = tmdb_discover(api_key, combo, language="ko-KR", page=1)[:per_call]
        for m in results:
            if m.get("id"):
                candidates[m["id"]] = m

    if len(top_ids) >= 3:
        combo3 = f"{top_ids[0]},{top_ids[1]},{top_ids[2]}"
        results = tmdb_discover(api_key, combo3, language="ko-KR", page=1)[:per_call]
        for m in results:
            if m.get("id"):
                candidates[m["id"]] = m

    return list(candidates.values())

def expand_by_graph(api_key: str, seeds, per_seed=25):
    """
    (3) seed 영화들을 기반으로 recommendations + similar로 후보 확장
    """
    expanded = {}
    for s in seeds:
        mid = s.get("id")
        if not mid:
            continue

        # recommendations
        try:
            recs = tmdb_recommendations(api_key, int(mid), language="ko-KR", page=1)[:per_seed]
            for m in recs:
                if m.get("id"):
                    expanded[m["id"]] = m
        except Exception:
            pass

        # similar
        try:
            sims = tmdb_similar(api_key, int(mid), language="ko-KR", page=1)[:per_seed]
            for m in sims:
                if m.get("id"):
                    expanded[m["id"]] = m
        except Exception:
            pass

    return list(expanded.values())

def quality_filter(candidates):
    """
    (3) 최소 vote_count 기준을 두되, 후보가 너무 줄면 완화한다.
    """
    # 점진적으로 완화
    thresholds = [300, 150, 50, 0]
    for t in thresholds:
        filtered = [m for m in candidates if int(m.get("vote_count", 0) or 0) >= t]
        if len(filtered) >= 25 or t == 0:
            return filtered
    return candidates

def generate_recommendations(api_key: str, profile, final_k=5):
    # (2) 후보 생성
    base_candidates = collect_candidates(api_key, profile, per_call=50)

    # (3) 최소 품질 필터(너무 과격하면 추천이 비게 되니까 완화 가능)
    base_candidates = quality_filter(base_candidates)

    # (4) 1차 점수화 -> seed 선정
    base_scores = {m["id"]: composite_score(profile, m) for m in base_candidates if m.get("id")}
    seeds = sorted(base_candidates, key=lambda m: base_scores.get(m["id"], -1e9), reverse=True)[:3]

    # (3) 추천망 확장
    expanded = expand_by_graph(api_key, seeds, per_seed=30)

    # 합치고 중복 제거
    merged = {}
    for m in base_candidates + expanded:
        if m.get("id"):
            merged[m["id"]] = m
    candidates = list(merged.values())

    # (3) 확장 후에도 품질 필터 한 번 더
    candidates = quality_filter(candidates)

    # (4) 재랭킹 점수 계산
    scores = {m["id"]: composite_score(profile, m) for m in candidates if m.get("id")}

    # 점수순으로 상위만 조금 잘라서 다양성 선택(속도/품질 균형)
    candidates_sorted = sorted(candidates, key=lambda m: scores.get(m["id"], -1e9), reverse=True)[:80]

    # (5) 다양성 선택(MMR)
    selected = mmr_select(candidates_sorted, scores, k=final_k, lam=0.78)

    return selected, scores

def build_reason(profile, movie):
    """
    사용자 축(가벼움/속도/탈출)과 영화 trait을 비교해 간단 이유를 만든다.
    """
    u = profile["axes"]
    m = movie_trait_vector(movie)

    # 가장 큰 차이/강점을 한두 줄로
    parts = []
    if u["escape"] >= 0.62 and m["escape"] >= 0.65:
        parts.append("현실 탈출/세계관 몰입 포인트가 강하다")
    if u["pace"] >= 0.62 and m["pace"] >= 0.65:
        parts.append("전개가 비교적 빠르고 시원하다")
    if u["light"] >= 0.62 and m["light"] >= 0.70:
        parts.append("가볍게 즐기기 좋다")
    if u["light"] <= 0.40 and m["light"] <= 0.45:
        parts.append("여운/감정선 쪽 만족도가 높을 가능성이 크다")

    if not parts:
        parts.append("네 선택 흐름과 잘 맞는 결의 작품이다")

    vote = float(movie.get("vote_average", 0) or 0)
    vcnt = int(movie.get("vote_count", 0) or 0)
    bayes = bayesian_rating(vote, vcnt)

    parts.append(f"평점 신뢰도 보정 기준으로도 무난하다(보정 평점 {bayes:.1f})")
    return " · ".join(parts)

# -----------------------------
# (8) 피드백 저장/적용
# -----------------------------
def init_state():
    if "base_profile" not in st.session_state:
        st.session_state.base_profile = None
    if "feedback" not in st.session_state:
        # 장르/축 조정값 누적
        st.session_state.feedback = {"genre_adj": {k: 0.0 for k in GENRES.keys()},
                                     "axis_adj": {"light": 0.0, "pace": 0.0, "escape": 0.0}}
    if "recs" not in st.session_state:
        st.session_state.recs = None
    if "last_genre_title" not in st.session_state:
        st.session_state.last_genre_title = None

def add_feedback(movie, like: bool):
    """
    좋아요면 +, 별로예요면 - 로 프로필 조정치를 누적한다.
    """
    sign = 1.0 if like else -1.0
    gids = movie.get("genre_ids", []) or []
    for gid in gids:
        k = ID_TO_KEY.get(gid)
        if k:
            st.session_state.feedback["genre_adj"][k] += sign * 0.08  # 너무 세지 않게
            st.session_state.feedback["genre_adj"][k] = clamp(st.session_state.feedback["genre_adj"][k], -0.25, 0.25)

    # 축도 살짝 조정(장르 trait 기반)
    mk = [ID_TO_KEY.get(g) for g in gids if ID_TO_KEY.get(g) in GENRE_TRAITS]
    mk = [x for x in mk if x]
    if mk:
        t = {
            "light": sum(GENRE_TRAITS[x]["light"] for x in mk) / len(mk),
            "pace": sum(GENRE_TRAITS[x]["pace"] for x in mk) / len(mk),
            "escape": sum(GENRE_TRAITS[x]["escape"] for x in mk) / len(mk),
        }
        # 좋아요면 사용자 축을 영화 방향으로 조금 끌어가고, 싫어요면 반대로
        # (너무 튀지 않게 작은 스텝)
        step = 0.05 * sign
        st.session_state.feedback["axis_adj"]["light"] += (t["light"] - 0.5) * step
        st.session_state.feedback["axis_adj"]["pace"] += (t["pace"] - 0.5) * step
        st.session_state.feedback["axis_adj"]["escape"] += (t["escape"] - 0.5) * step

        for k in ["light", "pace", "escape"]:
            st.session_state.feedback["axis_adj"][k] = clamp(st.session_state.feedback["axis_adj"][k], -0.20, 0.20)

# -----------------------------
# UI
# -----------------------------
init_state()

st.title("🎬 나와 어울리는 영화는?")
st.write("간단한 심리테스트로 지금의 너와 가장 잘 어울리는 영화 취향을 알아보자 😎")
st.write("아래 5개 질문에 답하고 **결과 보기**를 누르면, TMDB 기반으로 맞춤 추천이 나온다.")
st.write("추천 결과에서 👍/👎 피드백을 주면 다음 추천이 더 정확해진다.")

st.sidebar.header("TMDB 설정")
api_key = st.sidebar.text_input("TMDB API Key", type="password", placeholder="여기에 API Key 입력")

st.divider()

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

colA, colB = st.columns([1, 1], gap="large")
with colA:
    run_btn = st.button("결과 보기", type="primary", use_container_width=True)
with colB:
    rerun_btn = st.button("추천 새로 고침(피드백 반영)", use_container_width=True)

def top_genre_title(profile):
    top = sorted(profile["genre_w"].items(), key=lambda x: x[1], reverse=True)[:1]
    if not top:
        return "당신에게 딱인 장르는: ???!"
    gk = top[0][0]
    return f"당신에게 딱인 장르는: {GENRES[gk]['name']}!"

def render_results(api_key, base_profile):
    # 피드백 반영한 최종 프로필
    profile = apply_feedback_adjustments(base_profile, st.session_state.feedback)

    with st.spinner("분석 중..."):
        recs, scores = generate_recommendations(api_key, profile, final_k=5)

    st.session_state.recs = recs
    st.session_state.last_genre_title = top_genre_title(profile)

    # 결과 제목
    st.markdown(f"# {st.session_state.last_genre_title}")
    st.write("아래 추천은 **취향(장르/무드) + 보정 평점(신뢰도) + 다양성**까지 고려해서 뽑은 리스트다 👇")

    with st.expander("내 취향 벡터 보기"):
        gw = profile["genre_w"]
        ax = profile["axes"]
        st.write("**장르 가중치(정규화)**")
        st.write(", ".join([f"{GENRES[k]['name']} {gw[k]:.2f}" for k in sorted(gw, key=gw.get, reverse=True)]))
        st.write("**무드 축(0~1)**")
        st.write(f"가벼움 {ax['light']:.2f} · 속도감 {ax['pace']:.2f} · 현실탈출 {ax['escape']:.2f}")

    if not recs:
        st.info("추천할 영화가 부족하다. 다른 선택으로 다시 시도해줘.")
        return

    st.markdown("## 🎞️ 추천 영화")
    st.caption("카드 안에서 상세 정보를 펼치고, 👍/👎로 취향을 더 정교하게 만들 수 있다.")

    # 3열 카드
    cols = st.columns(3, gap="large")
    for idx, movie in enumerate(recs):
        col = cols[idx % 3]

        mid = movie.get("id")
        title = movie.get("title") or movie.get("original_title") or "제목 정보 없음"
        vote = float(movie.get("vote_average", 0) or 0)
        vcnt = int(movie.get("vote_count", 0) or 0)
        overview = (movie.get("overview") or "").strip() or "줄거리 정보가 부족하다."
        poster_url = build_poster_url(movie.get("poster_path"))

        reason = build_reason(profile, movie)

        with col:
            with card_container():
                if poster_url:
                    st.image(poster_url, use_container_width=True)
                else:
                    st.write("🖼️ 포스터 없음")

                st.markdown(f"### {title}")
                st.write(f"⭐ 평점: {vote:.1f}  (투표 {vcnt:,}개)")

                # 피드백 버튼
                b1, b2 = st.columns(2)
                with b1:
                    like_clicked = st.button("👍 좋아요", key=f"like_{mid}", use_container_width=True)
                with b2:
                    dislike_clicked = st.button("👎 별로예요", key=f"dislike_{mid}", use_container_width=True)

                if like_clicked:
                    add_feedback(movie, like=True)
                    st.toast("좋아요 반영 완료! 새로 고침하면 더 맞춤 추천이 나온다.", icon="✅")

                if dislike_clicked:
                    add_feedback(movie, like=False)
                    st.toast("별로예요 반영 완료! 새로 고침하면 더 맞춤 추천이 나온다.", icon="✅")

                with st.expander("상세 정보"):
                    st.write(f"**줄거리**: {overview}")
                    st.write(f"**이 영화를 추천하는 이유**: {reason}")

    st.markdown("---")
    st.write("✅ 추천이 마음에 들면 👍을, 별로면 👎을 눌러줘. 그 다음 **추천 새로 고침(피드백 반영)**을 누르면 추천이 더 맞춰진다.")

# -----------------------------
# 버튼 동작
# -----------------------------
if run_btn:
    if not api_key:
        st.error("사이드바에 TMDB API Key를 입력해줘.")
        st.stop()

    if any(x is None for x in selected_indices):
        st.warning("아직 선택하지 않은 질문이 있다. 5개 모두 답해줘!")
        st.stop()

    # 새 테스트 결과면 피드백 초기화(원하면 유지로 바꿔도 됨)
    st.session_state.feedback = {"genre_adj": {k: 0.0 for k in GENRES.keys()},
                                 "axis_adj": {"light": 0.0, "pace": 0.0, "escape": 0.0}}

    st.session_state.base_profile = profile_from_answers(selected_indices)
    render_results(api_key, st.session_state.base_profile)

elif rerun_btn:
    if not api_key:
        st.error("사이드바에 TMDB API Key를 입력해줘.")
        st.stop()

    if st.session_state.base_profile is None:
        st.warning("먼저 심리테스트를 완료하고 결과를 봐줘!")
        st.stop()

    render_results(api_key, st.session_state.base_profile)

else:
    # 이미 결과가 나온 상태라면(예: 버튼 클릭 후 rerun) 화면 유지
    if st.session_state.base_profile is not None and st.session_state.recs is not None:
        # 현재 피드백이 반영된 프로필로 타이틀만 다시 계산해서 보여주기
        profile = apply_feedback_adjustments(st.session_state.base_profile, st.session_state.feedback)
        st.markdown(f"# {top_genre_title(profile)}")
        st.write("이미 추천이 생성된 상태다. 아래에서 👍/👎 피드백을 주고 새로 고침하면 추천이 더 정확해진다.")

        # 저장된 추천 재렌더(불필요한 API 호출 방지)
        recs = st.session_state.recs
        st.markdown("## 🎞️ 추천 영화")
        cols = st.columns(3, gap="large")
        for idx, movie in enumerate(recs):
            col = cols[idx % 3]

            mid = movie.get("id")
            title = movie.get("title") or movie.get("original_title") or "제목 정보 없음"
            vote = float(movie.get("vote_average", 0) or 0)
            vcnt = int(movie.get("vote_count", 0) or 0)
            overview = (movie.get("overview") or "").strip() or "줄거리 정보가 부족하다."
            poster_url = build_poster_url(movie.get("poster_path"))

            reason = build_reason(profile, movie)

            with col:
                with card_container():
                    if poster_url:
                        st.image(poster_url, use_container_width=True)
                    else:
                        st.write("🖼️ 포스터 없음")

                    st.markdown(f"### {title}")
                    st.write(f"⭐ 평점: {vote:.1f}  (투표 {vcnt:,}개)")

                    b1, b2 = st.columns(2)
                    with b1:
                        like_clicked = st.button("👍 좋아요", key=f"like_keep_{mid}", use_container_width=True)
                    with b2:
                        dislike_clicked = st.button("👎 별로예요", key=f"dislike_keep_{mid}", use_container_width=True)

                    if like_clicked:
                        add_feedback(movie, like=True)
                        st.toast("좋아요 반영 완료! 새로 고침하면 더 맞춤 추천이 나온다.", icon="✅")

                    if dislike_clicked:
                        add_feedback(movie, like=False)
                        st.toast("별로예요 반영 완료! 새로 고침하면 더 맞춤 추천이 나온다.", icon="✅")

                    with st.expander("상세 정보"):
                        st.write(f"**줄거리**: {overview}")
                        st.write(f"**이 영화를 추천하는 이유**: {reason}")

        st.markdown("---")
        st.write("👉 피드백 후에는 **추천 새로 고침(피드백 반영)** 버튼을 눌러야 추천 리스트가 새로 계산된다.")

