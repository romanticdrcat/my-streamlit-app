import streamlit as st
from openai import OpenAI

st.title("🤖 나의 AI 챗봇")

# 사이드바에서 API Key 입력
api_key = st.sidebar.text_input("OpenAI API Key", type="password")
mood_options = {
    "기분 좋음": "밝고 즐거운 톤으로 대화를 이어가세요.",
    "평온함": "차분하고 안정적인 톤으로 대화를 이어가세요.",
    "우울함": "따뜻하고 위로가 되는 톤으로 대화를 이어가세요.",
    "불안함": "안심을 주는 톤으로 차근차근 설명하세요.",
    "화남": "공감하며 침착하게 대화를 이어가세요.",
}
mood = st.sidebar.selectbox("현재 기분 선택", list(mood_options.keys()))

# 대화 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 이전 대화 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 사용자 입력 처리
if prompt := st.chat_input("메시지를 입력하세요"):
    if not api_key:
        st.error("⚠️ 사이드바에서 API Key를 입력해주세요!")
    else:
        system_message = (
            "너는 친절한 한국어 챗봇이야. "
            f"사용자의 현재 기분은 '{mood}'이며, "
            f"{mood_options[mood]}"
        )
        # 사용자 메시지 저장 및 표시
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # AI 응답 생성
        with st.chat_message("assistant"):
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_message}]
                + st.session_state.messages
            )
            reply = response.choices[0].message.content
            st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
