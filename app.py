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
    "fanta


