import streamlit as st
import pandas as pd
import datetime
import time
import urllib.parse
from collections import Counter
import os
from utils_favorites import load_favorites, add_favorite, remove_favorite

# ✅ 하드코딩된 크롬드라이버 경로
CHROMEDRIVER_PATH = r"C:\Users\조민지\Desktop\local ai\web\chromedriver-win64\chromedriver.exe"

# -----------------------------
# ✅ 크롤러 함수
# -----------------------------
def crawl_naver_cafe(SEARCH_KEYWORD, LAST_PAGE, DRIVER_PATH):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from bs4 import BeautifulSoup

    ENCODED_KEYWORD = urllib.parse.quote(SEARCH_KEYWORD)
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(executable_path=DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    results = []

    def parse_page(html, page_num):
        soup = BeautifulSoup(html, "html.parser")
        related_keywords = [btn.get_text(strip=True) for btn in soup.select('.aside_search_tag button')]
        related_keywords_str = ", ".join(related_keywords)
        for item in soup.select('.ArticleItem'):
            link_tag = item.select_one('a')
            if link_tag:
                link = link_tag['href']
                title_elem = link_tag.select_one('strong.title')
                text_elem = link_tag.select_one('p.text')
                title = title_elem.get_text(strip=True) if title_elem else ""
                snippet = text_elem.get_text(strip=True) if text_elem else ""
            else:
                link = title = snippet = ""
            date_elem = item.select_one('span.date')
            date = date_elem.get_text(strip=True) if date_elem else ""
            results.append({
                "페이지": page_num,
                "날짜": date,
                "제목": title,
                "링크": link,
                "본문": snippet,
                "연관검색어": related_keywords_str
            })

    base_url = f"https://section.cafe.naver.com/ca-fe/home/search/articles?q={ENCODED_KEYWORD}"
    driver.get(base_url)
    time.sleep(5)
    current_block = 1
    for page in range(1, LAST_PAGE + 1):
        if page == 1:
            parse_page(driver.page_source, page)
            continue
        try:
            target_block = ((page - 1) // 10) + 1
            while current_block < target_block:
                next_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.type_next"))
                )
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(3)
                current_block += 1
            btn_xpath = f"//button[@class='btn number' and normalize-space(text())='{page}']"
            page_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, btn_xpath))
            )
            driver.execute_script("arguments[0].click();", page_btn)
            time.sleep(4)
            parse_page(driver.page_source, page)
        except Exception as e:
            st.warning(f"[오류] {page}페이지 이동 실패: {e}")

    driver.quit()
    return pd.DataFrame(results)

# -----------------------------
# ✅ 분석 함수
# -----------------------------
def clean_date(date_string, crawl_date=None):
    if crawl_date is None:
        crawl_date = datetime.date.today()
    if pd.isna(date_string):
        return str(crawl_date)
    date_string = str(date_string).strip()
    if any(keyword in date_string for keyword in ['전', '시간', '분', '일']):
        return str(crawl_date)
    return date_string

def standardize_date_format(date_string):
    if pd.isna(date_string):
        return date_string
    date_string = str(date_string).strip()
    if date_string.endswith('.'):
        date_string = date_string[:-1]
    return date_string.replace('.', '-')

def extract_top_keywords(df, top_n=5):
    from collections import Counter
    all_keywords = []
    for kw_list in df['연관검색어'].dropna():
        all_keywords.extend([kw.strip() for kw in kw_list.split(',') if kw.strip()])
    for text in df['제목'].dropna():
        all_keywords.extend(text.split())
    for text in df['본문'].dropna():
        all_keywords.extend(text.split())
    counter = Counter(all_keywords)
    return [kw for kw, _ in counter.most_common(top_n)]

# ✅ 개선된 이상감지 함수
def detect_anomaly_dynamic(df, date_column='날짜', recent_days=10, window=3):
    daily_counts = df[date_column].value_counts().sort_index()
    daily_counts.index = pd.to_datetime(daily_counts.index, errors='coerce')
    daily_counts = daily_counts.dropna().sort_index()

    # 최근 N일만 자르기
    if len(daily_counts) == 0:
        return [], None, daily_counts, None, None, None

    latest_date = daily_counts.index.max()
    cutoff_date = latest_date - pd.Timedelta(days=recent_days - 1)
    daily_counts_recent = daily_counts[daily_counts.index >= cutoff_date]

    if len(daily_counts_recent) == 0:
        return [], None, daily_counts, None, None, None

    # ✅ 총 크롤링 개수 대비 최근 N일 비중 계산
    total_count = len(df)
    recent_dates_str = daily_counts_recent.index.strftime('%Y-%m-%d')
    recent_count = len(df[df[date_column].isin(recent_dates_str)])
    recent_ratio = recent_count / total_count if total_count > 0 else 0

    # ✅ 비중 기반 민감도(k) 설정
    if recent_ratio > 0.8:
        k = 1.0
        attention_factor = 1.2
    elif recent_ratio > 0.5:
        k = 1.2
        attention_factor = 1.25
    elif recent_ratio > 0.2:
        k = 1.5
        attention_factor = 1.3
    else:
        k = 2.0
        attention_factor = 1.5

    # ✅ 임계치 계산
    moving_avg = daily_counts_recent.rolling(window=window, min_periods=1).mean()
    moving_std = daily_counts_recent.rolling(window=window, min_periods=1).std().fillna(0)
    threshold_series = moving_avg + k * moving_std

    # ✅ 이상 감지
    anomalies_idx = daily_counts_recent[daily_counts_recent > threshold_series].index
    anomalies = anomalies_idx.strftime("%Y-%m-%d").tolist()

    # ✅ 오늘 기준 감지
    today_str = str(datetime.date.today())
    today_count = daily_counts_recent.get(pd.to_datetime(today_str), 0)
    threshold_today = threshold_series.get(pd.to_datetime(today_str), None)

    return anomalies, threshold_today, daily_counts_recent, k, attention_factor, recent_ratio



#급락 감지 함수
def detect_drop_alert(daily_counts_recent, drop_ratio=0.3):
    """
    최근 며칠간 피크 대비 오늘 급락 여부를 감지
    drop_ratio: 급락 경계 비율 (default 30%)
    """
    if len(daily_counts_recent) < 3:
        return None, None

    today = pd.to_datetime(datetime.date.today())
    if today not in daily_counts_recent.index:
        return None, None

    today_count = daily_counts_recent.get(today, 0)
    peak_count = daily_counts_recent.drop(today, errors='ignore').max()

    if peak_count == 0:
        return None, None

    ratio = today_count / peak_count

    if ratio < drop_ratio:
        return ratio, peak_count
    else:
        return None, peak_count

#어제 대비 오늘
def detect_yesterday_change_alert(today_count, yesterday_count):
    if yesterday_count == 0:
        if today_count > 3:
            return "경고", f"어제 0건 → 오늘 {today_count}건 급증"
        elif today_count > 0:
            return "주의", f"어제 0건 → 오늘 {today_count}건 증가"
        else:
            return None, None

    change_ratio = (today_count - yesterday_count) / yesterday_count

    if change_ratio > 2.0:
        return "경고", f"어제 대비 +{change_ratio*100:.0f}% 급증"
    elif change_ratio > 1.0:
        return "주의", f"어제 대비 +{change_ratio*100:.0f}% 증가"
    elif change_ratio < -0.5:
        return "경고", f"어제 대비 {change_ratio*100:.0f}% 급감"
    elif change_ratio < -0.25:
        return "주의", f"어제 대비 {change_ratio*100:.0f}% 감소"
    else:
        return None, None


# -----------------------------
# ✅ Streamlit 페이지
# -----------------------------
st.set_page_config(page_title="이상 감지", layout="wide")
st.title("📈 네이버 카페 이상 감지 및 시각화")

# ✅ 뒤로가기 버튼
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

st.header("🛠️ 크롤러 설정")

# ✅ 즐겨찾기 선택
selected_fav = None
if favorites:
    selected_fav = st.selectbox("⭐ 즐겨찾기 키워드", favorites, placeholder="선택하지 않음")

custom_keyword = st.text_input("✅ 직접 입력", "")

# ✅ 최종 키워드 결정
final_keyword = None
if selected_fav and selected_fav.strip():
    final_keyword = selected_fav.strip()
elif custom_keyword.strip():
    final_keyword = custom_keyword.strip()

if final_keyword:
    st.info(f"👉 **최종 키워드: {final_keyword}**")
else:
    st.warning("❗ 키워드를 입력하거나 즐겨찾기에서 선택하세요.")


last_page = st.slider("✅ 크롤링할 페이지 수", 1, 50, 10)

start_crawl = st.button("🚀 크롤링 시작")

if start_crawl:
    if not os.path.isfile(CHROMEDRIVER_PATH):
        st.error(f"❌ 하드코딩된 ChromeDriver 경로 오류!\n```\n{CHROMEDRIVER_PATH}\n```")
    else:
        with st.spinner(f"🔎 '{final_keyword}' 크롤링 중..."):
            df = crawl_naver_cafe(final_keyword, last_page, CHROMEDRIVER_PATH)

        st.success(f"✅ 크롤링 완료! 총 {len(df)}건")

        # ✅ 날짜 처리
        df['날짜'] = df['날짜'].apply(clean_date).apply(standardize_date_format)

        # ✅ 개선된 이상감지
        anomalies, threshold_today, daily_counts_recent, k, attention_factor, recent_ratio = detect_anomaly_dynamic(df, recent_days=10)



        st.subheader("✅ 날짜별 게시글 수")
        st.bar_chart(daily_counts_recent)

        st.subheader("✅ 오늘 / 어제 비교")
        today_str = str(datetime.date.today())
        yesterday_str = str(datetime.date.today() - datetime.timedelta(days=1))
        today_count = daily_counts_recent.get(pd.to_datetime(today_str), 0)
        yesterday_count = daily_counts_recent.get(pd.to_datetime(yesterday_str), 0)
        diff_count = today_count - yesterday_count

        col1, col2 = st.columns(2)
        with col1:
            st.metric(label=f"오늘 ({today_str})", value=f"{today_count} 건", delta=f"{diff_count:+} 건")
        with col2:
            st.metric(label=f"어제 ({yesterday_str})", value=f"{yesterday_count} 건")

        if diff_count > 0:
            st.success(f"📈 오늘 어제보다 {diff_count}건 증가!")
        elif diff_count < 0:
            st.warning(f"📉 오늘 어제보다 {-diff_count}건 감소!")
        else:
            st.info("➖ 변화 없음")

        st.subheader("✅ 어제 대비 변화율 경보")
        alert_level, alert_message = detect_yesterday_change_alert(today_count, yesterday_count)
        if alert_level == "경고":
            st.error(f"❗ {alert_message}")
        elif alert_level == "주의":
            st.warning(f"⚠️ {alert_message}")
        else:
            st.success("✅ 어제 대비 큰 변화 없음")

        st.subheader("✅ 이상감지 결과")
        if threshold_today is not None:
            st.write(f"오늘 기준 임계치 (k={k:.1f}): {threshold_today:.2f}")
            st.write(f"주의 단계 계수 (Attention Factor): {attention_factor:.2f}")

            # ✅ recent_ratio 친절 출력
            st.info(
                f"📊 최근 10일치 데이터 비중: {recent_ratio*100:.1f}%\n"
                f"(전체 크롤링 {len(df)}건 중 최근 10일 {int(recent_ratio * len(df))}건)"
            )

            if today_count <= threshold_today:
                st.success(f"✅ 오늘({today_str}) 양호 - 급증 없음")
            elif today_count <= threshold_today * attention_factor:
                st.warning(f"⚠️ 오늘({today_str}) 주의 - 평소보다 다소 증가")
            else:
                st.error(f"❗ 오늘({today_str}) 경고 - 급증 감지!")
        else:
            st.warning("오늘 데이터가 없습니다.")


# ✅ 급락 감지 결과
        st.subheader("✅ 최근 피크 대비 급락 경보")
        drop_ratio, recent_peak = detect_drop_alert(daily_counts_recent)
        if drop_ratio is not None:
            st.error(f"❗ 오늘 건수가 최근 피크 ({recent_peak}건)의 {drop_ratio*100:.1f}% 수준으로 급락!")
        else:
            if recent_peak is not None:
                st.success(f"✅ 급락 경보 없음 (최근 피크 {recent_peak}건 기준)")
            else:
                st.info("➖ 급락 감지를 위한 데이터가 부족하거나 일정합니다.")


        st.subheader("✅ 인기 키워드 Top 5")
        extracted_keywords = extract_top_keywords(df)
        if extracted_keywords:
            for kw in extracted_keywords:
                st.markdown(f"- {kw}")
        else:
            st.write("추출된 키워드 없음.")

        st.subheader("✅ 날짜별 건수 상위 10")
        st.dataframe(df['날짜'].value_counts().head(10))

        with st.expander("✅ 전체 데이터 보기"):
            st.dataframe(df)



