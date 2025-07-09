import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
from utils_favorites import load_favorites, add_favorite, remove_favorite

# ✅ Potens.ai API 키
POTENS_API_KEY = "eykC4BBZxbq16ngzIRCXHaKoGTD36nxq"

# ==============================
# ✅ 네이버 블로그 링크 수집 (많이 가져오기)
# ==============================
def get_naver_blog_links(keyword, max_fetch=30):
    query = f"{keyword} 병원"
    search_url = f"https://search.naver.com/search.naver?where=view&query={query}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(search_url, headers=headers)

    links = []
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if 'blog.naver.com' in href and href not in links:
                links.append(href)
            if len(links) >= max_fetch:
                break
    return links

# ==============================
# ✅ 블로그 본문 크롤링
# ==============================
def crawl_blog_content(blog_url):
    headers = {"User-Agent": "Mozilla/5.0"}

    if "m.blog" not in blog_url:
        blog_url = blog_url.replace("blog", "m.blog")

    try:
        resp = requests.get(blog_url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None, None

        soup = BeautifulSoup(resp.content, 'html.parser')

        # 제목
        title_tag = soup.find("meta", property="og:title")
        title = title_tag["content"] if title_tag and title_tag.get("content") else "제목 추출 실패"

        # 본문
        try:
            content = soup.find("div", class_="se-main-container").get_text(separator="\n", strip=True)
        except:
            content = ""

        if content.strip() == "":
            return None, None

        return title, content

    except Exception:
        return None, None

# ==============================
# ✅ Potens.ai API 호출
# ==============================
def analyze_blog_content_via_potens(content, potens_api_key):
    system_prompt = (
        "당신은 한국의 의료광고 전문가이자 규제 감독자 역할을 합니다. "
        "사용자가 제공하는 한국 병원 블로그 본문을 읽고 아래 작업을 정확하고 간결하게 수행합니다.\n\n"
        "- 병원명: 본문에 등장하는 병원명을 정확히 추출 (가능하면 단일화된 명칭)\n"
        "- 과대광고/허위광고 여부: 한국 의료법 기준으로 허위·과대·오인광고 소지가 있는지 평가\n"
        "- 이유: 판단 근거를 간단명료하게 설명"
    )

    user_prompt = (
        f"아래 블로그 본문을 분석해주세요.\n\n"
        f"[본문]\n{content}\n\n"
        "분석 결과를 아래 형식으로 정리해주세요.\n"
        "---\n"
        "✅ 병원명:\n(병원명 텍스트)\n\n"
        "✅ 과대광고/허위광고 여부:\n(예: 있음 / 없음)\n\n"
        "✅ 판단 이유:\n(간단명료한 설명)"
    )

    url = "https://ai.potens.ai/api/chat"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {potens_api_key}"
    }
    data = {"prompt": f"{system_prompt}\n\n{user_prompt}"}

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        return result.get("message", "❌ Potens.ai 응답에 'message' 키가 없음!")
    else:
        return f"❌ Potens.ai API 호출 실패: {response.status_code} - {response.text}"


# ==============================
# ✅ 질병 코드 추천용 Potens.ai
# ==============================
def get_diagnosis_code_from_potens(keyword, potens_api_key):
    system_prompt = (
        "당신은 한국의 의학 전문가입니다. "
        "사용자가 입력한 증상이나 시술 키워드에 대해, "
        "병원에서 받을 수 있는 한국의료보험 진단 코드(한국질병분류코드 KCD)를 "
        "코드명(예: M99.0) + 한글 설명 형태로 표나 리스트로 추천하고 설명하는 역할을 합니다."
    )

    user_prompt = (
        f"'{keyword}' 증상으로 병원에서 진단받을 수 있는 한국의료보험 진단코드명을 "
        "코드명(예: M99.0) + 한글 설명 형태로 알려줘. "
        "표나 리스트로 보기 좋게 정리해줘."
    )

    url = "https://ai.potens.ai/api/chat"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {potens_api_key}"
    }
    data = {"prompt": f"{system_prompt}\n\n{user_prompt}"}

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        return result.get("message", "❌ Potens.ai 응답에 'message' 키가 없음!")
    else:
        return f"❌ Potens.ai API 호출 실패: {response.status_code} - {response.text}"


# ==============================
# ✅ Streamlit 앱
# ==============================
st.set_page_config(page_title="병원 광고 분석기", layout="wide")
st.title("🏥 네이버 블로그 병원 광고 분석기")

# ✅ 홈으로 가는 버튼
st.page_link("", label="🏠 홈으로", icon="🏠")


# ✅ 즐겨찾기 관리 사이드바
st.sidebar.header("⭐ 즐겨찾기 관리")
favorites = load_favorites()

# ✅ 즐겨찾기 추가
new_fav = st.sidebar.text_input("즐겨찾기에 추가할 키워드", "")
if st.sidebar.button("⭐ 추가"):
    if new_fav.strip():
        favorites = add_favorite(new_fav.strip())
        st.sidebar.success(f"✅ '{new_fav}' 추가 완료!")

# ✅ 즐겨찾기 목록
if favorites:
    st.sidebar.markdown("### ✅ 내 즐겨찾기")
    for fav in favorites:
        col1, col2 = st.sidebar.columns([4, 1])
        col1.markdown(f"- {fav}")
        if col2.button("❌", key=f"del_{fav}"):
            favorites = remove_favorite(fav)
            st.sidebar.warning(f"❌ '{fav}' 제거됨")




# ✅ 공통 검색 키워드
# ✅ 즐겨찾기 선택
selected_fav = None
if favorites:
    st.subheader("✅ 즐겨찾기에서 선택")
    selected_fav = st.selectbox("⭐ 즐겨찾기 키워드", favorites)

user_keyword = st.text_input("분석할 키워드 입력", placeholder="예) 도수치료")

if selected_fav and selected_fav.strip():
    user_keyword = selected_fav


# ✅ 세션 초기화
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = []
if "diagnosis_result" not in st.session_state:
    st.session_state.diagnosis_result = ""

# ==============================
# ✅ 병원 광고 링크 + 분석
# ==============================
st.header("✅ 병원 블로그 링크 수집 및 분석")
num_links = st.slider("가져올 분석 결과 수", min_value=1, max_value=10, value=5)

if st.button("🔎 병원 광고 링크 수집 + 본문 분석하기"):
    if user_keyword.strip() == "":
        st.warning("❗ 키워드를 입력해주세요.")
    else:
        st.session_state.analysis_results = []
        with st.spinner(f"네이버에서 '{user_keyword} 병원' 검색 링크 수집 중..."):
            candidate_links = get_naver_blog_links(user_keyword, max_fetch=30)

        if not candidate_links:
            st.error("❌ 링크를 찾지 못했습니다. 네이버 구조가 바뀌었거나 결과가 없습니다.")
        else:
            st.success(f"✅ 후보 링크 수집. 본문 크롤링 및 분석을 시작합니다!")

            successful_count = 0
            for idx, link in enumerate(candidate_links, 1):
                if successful_count >= num_links:
                    break

                with st.spinner(f"[{successful_count+1}/{num_links}] 본문 크롤링 중..."):
                    title, content = crawl_blog_content(link)

                if not content:
                    continue  # 본문 추출 실패는 스킵

                with st.spinner(f"[{successful_count+1}/{num_links}] Potens.ai 분석 중..."):
                    analysis_result = analyze_blog_content_via_potens(content, POTENS_API_KEY)

                st.session_state.analysis_results.append({
                    "index": successful_count + 1,
                    "title": title,
                    "link": link,
                    "analysis": analysis_result
                })

                successful_count += 1
                time.sleep(1)  # 너무 빠른 요청 방지

            if successful_count < num_links:
                st.warning(f"⚠️ 요청한 {num_links}개를 모두 채우지 못했습니다. (성공: {successful_count})")

# ✅ 분석 결과 출력
if st.session_state.analysis_results:
    st.subheader("🩺 병원 블로그 분석 결과")
    for item in st.session_state.analysis_results:
        st.markdown(f"### ✅ {item['index']}. {item['title']}")
        st.markdown(f"[블로그 링크]({item['link']})")
        st.markdown("---")
        st.markdown(item['analysis'])
        st.divider()


# ==============================
# ✅ 진단 코드 추천 (별도)
# ==============================
st.header("✅ 증상/시술 키워드로 진단 코드 추천")
if st.button("🩺 진단 코드 추천받기"):
    if user_keyword.strip() == "":
        st.warning("❗ 키워드를 입력해주세요.")
    else:
        with st.spinner("Potens.ai에 요청 중..."):
            diagnosis_code = get_diagnosis_code_from_potens(user_keyword, POTENS_API_KEY)
            st.session_state.diagnosis_result = diagnosis_code

if st.session_state.diagnosis_result:
    st.success("✅ 추천 진단 코드")
    st.markdown(st.session_state.diagnosis_result)
