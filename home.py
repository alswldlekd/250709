import streamlit as st
from utils_favorites import load_favorites
from utils_alert_cache import load_alert_cache, update_alert_cache
import time
import pandas as pd
import os

# ✅ Anomaly.py의 크롤러/감지 함수 임포트
from pages.Anomaly2 import (
    crawl_naver_cafe,
    clean_date,
    standardize_date_format,
    detect_anomaly_dynamic
)

CHROMEDRIVER_PATH = r"C:\Users\조민지\Desktop\local ai\web\chromedriver-win64\chromedriver.exe"

st.set_page_config(page_title="내 분석 앱", page_icon="🩺")

st.title("🩺 텍스트 분석 & 이상 감지 & 광고 링크 진단코드")

st.markdown("### 👇 아래에서 원하는 기능을 선택하세요")
st.page_link("pages/Anomaly2.py", label="📈 이상 감지 페이지로 이동")
st.page_link("pages/Ads3.py", label="📈 병원 광고 링크 페이지로 이동")

st.divider()
st.header("⭐ 즐겨찾기 키워드 급증 알림")

# ✅ 즐겨찾기 로딩
favorites = load_favorites()
alert_cache = load_alert_cache()

if not favorites:
    st.info("👉 즐겨찾기에 등록된 키워드가 없습니다. Ads나 Anomaly 페이지에서 추가해주세요.")
else:
    # ✅ 저장된 캐시에서 알림 상태 보여주기
    for kw in favorites:
        info = alert_cache.get(kw)
        if info:
            st.subheader(f"✅ {kw}")
            st.markdown(f"- 상태: **{info['status']}**")
            st.markdown(f"- 마지막 검사: {info['last_checked']}")
            st.markdown(f"- 상세: {info['details']}")
            if info['status'] == "경고":
                st.error(f"❗ {kw} 급증 경고!")
            elif info['status'] == "주의":
                st.warning(f"⚠️ {kw} 주의 필요")
            else:
                st.success(f"✅ {kw} 양호")
            st.divider()
        else:
            st.subheader(f"✅ {kw}")
            st.warning("⚠️ 아직 검사 기록이 없습니다.")
            st.divider()

# ✅ 전부 재검사 버튼
if st.button("🔄 즐겨찾기 키워드 전부 재검사"):
    if not os.path.isfile(CHROMEDRIVER_PATH):
        st.error(f"❌ ChromeDriver 경로 오류\n```\n{CHROMEDRIVER_PATH}\n```")
    else:
        for idx, kw in enumerate(favorites, 1):
            with st.spinner(f"[{idx}/{len(favorites)}] '{kw}' 크롤링 중..."):
                try:
                    # ✅ 빠른 검사 모드: 페이지 수 5로 제한
                    df = crawl_naver_cafe(kw, 5, CHROMEDRIVER_PATH)
                    df['날짜'] = df['날짜'].apply(clean_date).apply(standardize_date_format)
                    anomalies, threshold_today, daily_counts_recent, k, attention_factor, recent_ratio = detect_anomaly_dynamic(df, recent_days=10)
                    
                    today_str = str(pd.Timestamp.today().date())
                    today_count = daily_counts_recent.get(pd.to_datetime(today_str), 0)

                    if threshold_today is not None:
                        if today_count <= threshold_today:
                            status = "양호"
                            details = f"오늘 건수 정상 범위 ({today_count}/{threshold_today:.1f})"
                        elif today_count <= threshold_today * attention_factor:
                            status = "주의"
                            details = f"오늘 건수 주의 단계 ({today_count}/{threshold_today:.1f})"
                        else:
                            status = "경고"
                            details = f"오늘 건수가 임계치 초과 ({today_count}/{threshold_today:.1f})"
                    else:
                        status = "양호"
                        details = "오늘 데이터가 없음"

                    update_alert_cache(kw, status, details)
                    time.sleep(1)

                except Exception as e:
                    update_alert_cache(kw, "오류", f"검사 실패: {e}")
                    st.error(f"❌ '{kw}' 검사 중 오류: {e}")

        st.success("✅ 전부 재검사 완료! 페이지 새로고침 후 최신 알림을 확인하세요.")
