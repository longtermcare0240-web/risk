from flask import Flask, request, jsonify, render_template_string, Response, send_file
import pandas as pd
from flask_compress import Compress
import os
import re
import time
import threading
import requests
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
import webbrowser
from urllib.parse import quote
import json
from datetime import date, datetime


def update_visitors():

    if not SUPABASE_URL or not SUPABASE_KEY:
        return {
            "total": 0,
            "today_count": 0
        }

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    url = f"{SUPABASE_URL}/rest/v1/visit_stats?id=eq.1"

    r = requests.get(url, headers=headers)

    rows = r.json()

    if not rows:
        return {
            "total": 0,
            "today_count": 0
        }

    row = rows[0]

    total = row["total_count"]
    today = row["today_date"]
    today_count = row["today_count"]

    now_day = str(date.today())

    total += 1

    if today == now_day:
        today_count += 1
    else:
        today = now_day
        today_count = 1

    update_data = {
        "total_count": total,
        "today_date": today,
        "today_count": today_count
    }

    requests.patch(
        url,
        headers=headers,
        json=update_data
    )

    return {
        "total": total,
        "today_count": today_count
    }

    requests.post(
        f"{SUPABASE_URL}/rest/v1/visit_logs",
        headers=headers,
        json={
            "ip": request.headers.get(
                "X-Forwarded-For",
                request.remote_addr
            )
        }
    )


def save_search_log(data):

    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "province": data.get("province", ""),
        "city": data.get("city", ""),
        "town": data.get("town", ""),
        "categories": data.get("categories", []),
        "result_count": data.get("result_count", 0),
        "ip": request.headers.get(
            "X-Forwarded-For",
            request.remote_addr
        )
    }

    requests.post(
        f"{SUPABASE_URL}/rest/v1/search_logs",
        headers=headers,
        json=payload
    )



app = Flask(__name__)
Compress(app)

app.json.ensure_ascii = False

KAKAO_KEY = os.environ.get("KAKAO_KEY")

@app.route("/search_place")
def search_place():

    query = request.args.get("q","")

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"

    headers = {
        "Authorization": f"KakaoAK {KAKAO_KEY}"
    }

    params = {
        "query": query
    }

    r = requests.get(url, headers=headers, params=params)

    return jsonify(r.json())

app.config["JSON_AS_ASCII"] = False
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = "mapdata_geocoded.xlsx"
DATA_CACHE = None


TYPE_COLORS = {
    "상습결빙지역": "#06b6d4",
    "공중화장실": "#f59e0b",
    "교통사고위험지역": "#ef4444"   # 추가
}

DEFAULT_CENTER = [34.85, 126.90]
DEFAULT_ZOOM = 9


def safe_str(v):
    if pd.isna(v):
        return ""
    return str(v).strip()


def extract_town_from_address(address):
    addr = safe_str(address)
    if not addr:
        return "읍면동없음"

    # 읍/면/동/가/리 추출
    found = re.findall(r'([가-힣0-9]+(?:읍|면|동))', addr)
    if found:
        for token in reversed(found):
            if token.endswith(("읍", "면", "동")):
                return token

    return "읍면동없음"


def sample_desc(category, city, town, address):

    if category == "상습결빙지역":
        return f"{city} {town} 일대는 겨울철 노면 결빙 위험이 높은 구간입니다."

    if category == "공중화장실":
        return f"{city} {town} 인근 공중화장실 위치입니다."

    if category == "교통사고위험지역":
        return f"{city} {town} 일대는 교통사고 발생률이 높은 구간입니다."

    return f"{city} {town} 위치 정보입니다."

def sample_date(category):

    m = {
        "상습결빙지역": "2025-12-28",
        "공중화장실": "2025-01-01",
        "교통사고위험지역": "2025-01-01"   # 추가
    }

    return m.get(category, "2025-01-01")
 

def build_photo_url(row):

    category = safe_str(row["구분"])

    if category == "공중화장실":
        return "/photo/111"

    if category == "상습결빙지역":
        return "/photo/222"

    if category == "교통사고위험지역":
        return "/photo/333"

    return "/photo/111"

def load_df():

    global DATA_CACHE

    if DATA_CACHE is not None:
        return DATA_CACHE

    if not os.path.exists(FILE_PATH):
        raise FileNotFoundError(f"{FILE_PATH} 파일이 없습니다.")

    df = pd.read_excel(FILE_PATH)
    
    required = ["순번", "구분", "시도", "시군구", "주소", "위도", "경도"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"엑셀에 '{col}' 열이 없습니다.")

    if "시도" not in df.columns:
        df["시도"] = ""

    if "읍면동" not in df.columns:
        df["읍면동"] = df["주소"].apply(extract_town_from_address)

    if "사고설명" not in df.columns:
        df["사고설명"] = ""

    if "날짜" not in df.columns:
        df["날짜"] = ""

    if "사진URL" not in df.columns:
        df["사진URL"] = ""

    for col in ["구분", "시도", "시군구", "주소", "읍면동", "사고설명", "날짜", "사진URL"]:
        df[col] = df[col].apply(safe_str)
    df["구분"] = df["구분"].str.strip()

    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")

    # 좌표 없는 건 자동 제외
    df = df[df["위도"].notna() & df["경도"].notna()].copy()

    DATA_CACHE = df
    return DATA_CACHE


def row_to_dict(row):
    category = safe_str(row["구분"])
    province = safe_str(row["시도"])
    city = safe_str(row["시군구"])
    town = safe_str(row["읍면동"])
    address = safe_str(row["주소"])

    desc = safe_str(row.get("사고설명", ""))
    if not desc:
        desc = sample_desc(category, city, town, address)

    date_value = safe_str(row.get("날짜", ""))
    if not date_value:
        date_value = sample_date(category)

    return {
        "시도": province,
        "순번": safe_str(row["순번"]),
        "구분": category,
        "시군구": city,
        "읍면동": town,
        "주소": address,
        "위도": float(row["위도"]),
        "경도": float(row["경도"]),
        "사고설명": desc,
        "날짜": date_value,
        "사진URL": build_photo_url(row),
        "마커색상": TYPE_COLORS.get(category, "#334155"),
    }


HTML = r"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>안전지도</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
*{box-sizing:border-box}
html,body{
  margin:0;
  padding:0;
  width:100%;
  height:100%;
  font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;
  background:#f8fafc;
  color:#0f172a;
}
.page{
  display:flex;
  flex-direction:row;
  width:100%;
  height:100vh;
  overflow:hidden;
}

.sidebar{
  width:360px;
  min-width:360px;
  background:#fff;
  border-right:1px solid #e5e7eb;
  padding:18px 16px;
  overflow-y:auto;
}
.brand{
  display:flex;
  align-items:center;
  gap:14px;
  margin-bottom:18px;
}

.brand-left{
  display:flex;
  flex-direction:column;
  width:100%;
}

.brand-title{
  display:flex;
  align-items:center;
  justify-content:space-between;
  width:100%;

  font-size:22px;
  font-weight:900;
  margin:0;
  line-height:1.2;
}

.brand-sub{
  font-size:13px;
  color:#64748b;
  margin-top:3px;
}

.ci-logo{
  height:48px;
  object-fit:contain;
  margin-left:12px;
  flex-shrink:0;
}

@media (max-width:900px){
  #locBtn{
    display:none !important;
  }
}

@media (max-width:900px){
  .ci-logo{
    height:44px;
  }
}

@media (max-width:900px){
  .top-badge{
    display:none;
  }
}

@media (max-width:900px){

  #locBtn{
    display:none !important;
  }

  .top-badge{
    display:none !important;
  }

}

.logo{
  width:48px;
  height:48px;
  border-radius:16px;
  display:flex;
  align-items:center;
  justify-content:center;
  color:#fff;
  font-size:24px;
  background:linear-gradient(135deg,#2563eb,#7c3aed);
  box-shadow:0 10px 24px rgba(37,99,235,.25);
}
.brand h1{
  margin:0;
  font-size:22px;
  line-height:1.2;
}
.brand p{
  margin:4px 0 0 0;
  font-size:13px;
  color:#64748b;
}
.card{
  background:#f8fafc;
  border:1px solid #e2e8f0;
  border-radius:18px;
  padding:15px;
  margin-bottom:14px;
}
.card h3{
  margin:0 0 12px 0;
  font-size:15px;
}
.label{
  display:block;
  margin:10px 0 6px;
  font-size:13px;
  font-weight:700;
  color:#334155;
}
.select, .btn{
  width:100%;
  min-height:46px;
  border-radius:12px;
  border:1px solid #cbd5e1;
  font-size:15px;
}
.select{
  background:#fff;
  padding:0 12px;
}
.check-grid{
  display:grid;
  grid-template-columns:1fr;
  gap:8px;
}
.check-item{
  display:flex;
  align-items:center;
  gap:10px;
  padding:10px 12px;
  border:1px solid #e2e8f0;
  background:#fff;
  border-radius:12px;
  font-size:14px;
}
.dot{
  width:12px;
  height:12px;
  border-radius:999px;
  flex:0 0 12px;
}
.btn-row{
display:grid;
grid-template-columns:1fr 1fr;
gap:14px;
margin-top:14px;
margin-bottom:6px;
}

.sidebar .btn{
  height:46px;
  font-size:14px;
  margin-top:8px;
}

.btn{
  cursor:pointer;
  font-weight:800;
}
.btn.primary{
  background:#2563eb;
  color:#fff;
  border:none;
}
.btn.secondary{
  background:#fff;
  color:#111827;
}

.btn.kakao{
  background:#FEE500;
  color:#191919;
  border:none;
}

.summary{
display:grid;
grid-template-columns:1fr 1fr;
gap:10px;
}

.admin-btn{
grid-column:1 / -1;
}

.summary-box{
  background:#fff;
  border:1px solid #e2e8f0;
  border-radius:14px;
  padding:14px;
}
.summary-box .num{
  font-size:24px;
  font-weight:900;
  margin-bottom:4px;
}
.summary-box .txt{
  font-size:12px;
  color:#64748b;
}


@media (max-width:900px){

.map-legend{
display:none;
}

}
.legend-item{
  display:flex;
  align-items:center;
  gap:8px;
  font-size:13px;
}
.notice{
  font-size:12px;
  line-height:1.6;
  color:#475569;
}
.map-wrap{
  position:relative;
  flex:1;
  min-width:0;
}
#map{
  width:100%;
  height:100vh;
}

.top-badge{
  position:absolute;
  top:14px;
  right:14px;
  z-index:999;
  background:rgba(255,255,255,.96);
  border:1px solid #e5e7eb;
  border-radius:14px;
  padding:10px 12px;
  font-size:13px;
  box-shadow:0 8px 24px rgba(15,23,42,.08);
}

.map-legend{
  position:absolute;
  top:20px;
  right:20px;
  bottom:auto;
  background:white;
  padding:10px 12px;
  border-radius:12px;
  box-shadow:0 6px 18px rgba(0,0,0,0.18);
  font-size:13px;
  z-index:999;
}

.map-legend-item{
  display:flex;
  align-items:center;
  gap:6px;
  margin-bottom:4px;
}

.map-legend-dot{
  width:18px;
  height:18px;
  border-radius:50%;
  flex-shrink:0;
  display:inline-block;
}

.loading{
  position:absolute;
  left:50%;
  top:50%;
  transform:translate(-50%,-50%);
  z-index:1000;
  background:rgba(15,23,42,.86);
  color:#fff;
  padding:12px 16px;
  border-radius:14px;
  font-size:14px;
  display:none;
}
.custom-marker{
  width:18px;
  height:18px;
  border-radius:999px;
  border:3px solid #fff;
  box-shadow:0 2px 8px rgba(0,0,0,.25);
}
.popup-wrap{
  width:245px;
}
.popup-img{
  width:100%;
  height:160px;
  object-fit:contain;
  border-radius:12px;
  border:1px solid #e5e7eb;
  margin-bottom:10px;
  background:#f1f5f9;
}

.popup-title{
  font-size:16px;
  font-weight:900;
  margin-bottom:6px;
  line-height:1.35;
}
.popup-meta{
  font-size:12px;
  color:#64748b;
  line-height:1.5;
  margin-bottom:8px;
}
.popup-desc{
  font-size:13px;
  line-height:1.55;
}
@media (max-width: 900px){
  .page{
    display:block;
    height:auto;
    min-height:100vh;
  }

  .sidebar{
    width:100%;
    min-width:0;
    border-right:none;
    border-bottom:none;
    padding:15px 14px;
  }

  .map-wrap{
    display:block;
    position:static;
    width:100%;
    height:0;
    overflow:visible;
  }

  #map{
    display:none;
  }

  
}

.mobile-map-popup{
  position:fixed;
  inset:0;
  background:#ffffff;
  z-index:2000;
  display:none;
  flex-direction:column;
}

.mobile-map-header{
  height:56px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:0 16px;
  border-bottom:1px solid #e5e7eb;
  font-weight:700;
}

.mobile-map-close{
  border:none;
  background:#ef4444;
  color:#ffffff;
  padding:6px 10px;
  border-radius:6px;
}

@media (min-width:901px){

  .mobile-map-popup{
    display:none !important;
  }

}

.mobile-map{
  flex:1;
}

@media(min-width:901px){
  .mobile-map-popup{
    display:none !important;
  }
}

#locBtn{
position:absolute;
bottom:20px;
right:20px;
z-index:1000;

width:46px;
height:46px;

border-radius:50%;
border:none;

background:#ffffff;
color:#2563eb;

font-size:20px;

display:flex;
align-items:center;
justify-content:center;

box-shadow:0 6px 16px rgba(0,0,0,0.25);

cursor:pointer;
}


@media (max-width:900px){

.map-legend{
  top:auto;
  bottom:80px;
  right:10px;
  font-size:11px;
  padding:8px;
}

.map-legend-dot{
  width:16px;
  height:16px;
}

}
.mobile-map-popup .map-legend{
  position:absolute;
  top:70px;
  right:6px;
  bottom:auto;
  z-index:3000;
}

.user-marker-wrap{
  position:relative;
  width:28px;
  height:28px;
}

.user-pin{
  position:relative;
  width:34px;
  height:34px;
}

.user-pin::before{
  content:"";
  position:absolute;
  left:50%;
  top:50%;
  width:18px;
  height:18px;
  background:#22c55e;
  border-radius:50%;
  border:3px solid #ffffff;
  transform:translate(-50%,-50%);
  box-shadow:0 4px 12px rgba(0,0,0,.35);
}

.user-pin::after{
  content:"";
  position:absolute;
  left:50%;
  top:50%;
  width:34px;
  height:34px;
  border-radius:50%;
  background:rgba(34,197,94,0.25);
  transform:translate(-50%,-50%);
  animation:userPulse 1.8s infinite;
}

.user-marker-pulse{
  position:absolute;
  left:50%;
  top:50%;
  width:28px;
  height:28px;
  transform:translate(-50%,-50%);
  border-radius:50%;
  background:rgba(37,99,235,0.22);
  animation:userPulse 1.8s ease-out infinite;
}

.user-marker-dot{
  position:absolute;
  left:50%;
  top:50%;
  width:14px;
  height:14px;
  transform:translate(-50%,-50%);
  border-radius:50%;
  background:#2563eb;
  border:3px solid #ffffff;
  box-shadow:0 2px 8px rgba(0,0,0,.25);
}

@keyframes userPulse{
  0%{
    transform:translate(-50%,-50%) scale(0.7);
    opacity:0.9;
  }
  100%{
    transform:translate(-50%,-50%) scale(1.8);
    opacity:0;
  }
}

.location-box{
  margin-top:12px;
  padding:12px;
  border:1px solid #e2e8f0;
  border-radius:16px;
  background:#f8fafc;
}

.location-row{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
  margin-top:8px;
}

.location-box .btn{
  background:#ffffff;
  color:#111827;
  border:1px solid #cbd5e1;
}

.mobile-result-panel{
  position:absolute;
  left:0;
  right:0;
  bottom:0;
  width:100%;
  height:180px;
  max-height:40%;
  background:white;
  border-top-left-radius:16px;
  border-top-right-radius:16px;
  box-shadow:0 -6px 20px rgba(0,0,0,.15);
  z-index:3000;
  display:none;
  flex-direction:column;
}

@media (max-width:900px){
  .mobile-result-panel{
    position:fixed;
  }
}

.mobile-result-header{
  padding:10px 14px;
  font-weight:700;
  border-bottom:1px solid #e5e7eb;
}

.mobile-result-list{
  overflow:auto;
  flex:1;
}

.mobile-result-item{
  padding:10px 14px;
  border-bottom:1px solid #f1f5f9;
  font-size:13px;
  cursor:pointer;
}

.mobile-result-item:hover{
  background:#f8fafc;
}

.mobile-result-distance{
  font-size:12px;
  color:#2563eb;
}

#mobileLocBtn{
position:absolute;
bottom:20px;
right:20px;
z-index:4000;

width:52px;
height:52px;

border-radius:50%;
border:none;

background:#2563eb;
color:white;

font-size:22px;

display:flex;
align-items:center;
justify-content:center;

box-shadow:0 6px 16px rgba(0,0,0,0.25);

cursor:pointer;
}

.sexoffender-btn{
display:block;
background:#ffffff;
color:#111827;
}

@media (max-width:900px){
.sexoffender-btn{
display:block;
}
}

@media (min-width:901px){
.sexoffender-btn{
display:block;
}
}


.sidebar .btn{
height:46px;
font-size:14px;
margin-top:8px;
}

@keyframes floatChar{
0%{transform:translateY(0);}
50%{transform:translateY(-6px);}
100%{transform:translateY(0);}
}

.char{
width:80px;
animation:floatChar 2.2s ease-in-out infinite;
}

.loading-dots::after{
content:"";
animation:dots 1.4s steps(3,end) infinite;
}

@keyframes dots{
0%{content:"";}
33%{content:".";}
66%{content:"..";}
100%{content:"...";}
}

.visitor-box{
display:flex;
gap:15px;
margin-top:15px;
}

.visitor-card{
flex:1;
background:#f1f5f9;
border-radius:14px;
padding:12px;
text-align:center;
}

.visitor-title{
font-size:13px;
color:#666;
}

.visitor-count{
font-size:22px;
font-weight:700;
margin-top:4px;
}

</style>
</head>
<body>

<div class="page">
  <aside class="sidebar">
<div class="brand">

  <div class="brand-left">
    <div class="brand-title">
      <span>안전지도</span>
      <img src="/ci" class="ci-logo">
    </div>

    <div class="brand-sub">자료제공: 행정안전부(생활안전지도)</div>
  </div>

</div>    

<div class="card">
      <h3>조회 조건</h3>

      <label class="label">시도</label>
      <select id="province" class="select">
      <option value="">전체</option>
      </select>

      <label class="label">시군구</label>
      <select id="city" class="select">
        <option value="">전체</option>
      </select>

      <label class="label">읍면동</label>
      <select id="town" class="select">
        <option value="">전체</option>
      </select>

      <label class="label">구분</label>
      <div class="check-grid" id="categoryBox"></div>

            <div class="btn-row">
  <button class="btn primary" onclick="loadData()">조회</button>
  <button class="btn secondary" onclick="resetFilters()">필터 초기화</button>
</div>

<button class="btn kakao" onclick="openRouteSearch()">
경로 주변 위험지역 찾기
</button>


<button class="btn secondary" onclick="findNearestToilet()">
내 주변 화장실 찾기
</button>


<button class="btn secondary" onclick="findNearestDanger()">
내 주변 위험지역 찾기
</button>

<button class="btn secondary sexoffender-btn" onclick="openSexOffenderApp()">
성범죄자 알림e
</button>

</div>

<div class="card">
      <h3>방문자 수</h3>
      <div class="summary">

<div class="summary-box">
<div class="num">{{total_visit}}</div>
<div class="txt">총 방문자</div>
</div>

<div class="summary-box">
<div class="num">{{today_visit}}</div>
<div class="txt">오늘 방문자</div>
</div>


<button class="btn secondary admin-btn" onclick="openAdminStats()">
관리자 통계
</button>

</div>
</div>

  </aside>

  <main class="map-wrap">
  <div id="map"></div>

  <div class="mobile-result-panel" id="mobileResultPanel">
    <div class="mobile-result-header">
      검색 결과 <span id="mobileResultCount">0</span>건
    </div>
    <div class="mobile-result-list" id="mobileResultList"></div>
  </div>

  </main>

  <button id="locBtn">📍</button>
  <div class="top-badge">모바일 / PC 지원</div>
  <div class="map-legend">
  
    <div class="map-legend-item">
      <span class="map-legend-dot" style="background:#06b6d4"></span>
      상습결빙지역
    </div>

    <div class="map-legend-item">
      <span class="map-legend-dot" style="background:#f59e0b"></span>
      공중화장실
    </div>

    <div class="map-legend-item">
      <span class="map-legend-dot" style="background:#ef4444"></span>
      교통사고위험지역
    </div>

    <div class="map-legend-item">
      <span class="map-legend-dot" style="background:#2563eb"></span>
      내 위치
    </div>
  </div>

  <div class="loading" id="loadingBox">데이터를 불러오는 중입니다...</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

<script>
let ALL_DATA_CACHE = null;


const CATEGORY_COLORS = {
  "상습결빙지역": "#06b6d4",
  "공중화장실": "#f59e0b",
  "교통사고위험지역": "#ef4444"
};

const CATEGORY_LIST = [
  "상습결빙지역",
  "공중화장실",
  "교통사고위험지역"
];


const map = L.map("map", { zoomControl:true }).setView([34.85, 126.90], 9);

setTimeout(()=>{
  map.invalidateSize();
},500);

let userLat = null;
let userLng = null;
function showMsg(text){

  const modal = document.getElementById("msgModal");
  const txt = document.getElementById("msgText");
  const btn = document.getElementById("msgBtn");

  if(!modal || !txt) return;

  txt.innerText = text;

  if(btn){
    btn.style.display = "inline-block";
  }

  modal.style.display = "flex";

}

function showLoadingLocation(){

  loadingStartTime = Date.now();

  const modal = document.getElementById("msgModal");
  const txt = document.getElementById("msgText");
  const btn = document.getElementById("msgBtn");

  if(!modal || !txt) return;

  txt.innerHTML = `
  <div style="
  display:flex;
  align-items:center;
  justify-content:center;
  gap:18px;
  ">

  <img src="/char_left" class="char">

  <div style="
  font-size:16px;
  font-weight:700;
  padding:10px 14px;
  white-space:nowrap;
  ">
  📍 위치 확인 중<span class="loading-dots"></span>
  </div>

  <img src="/char_right" class="char">

  </div>
<div style="
margin-top:10px;
font-size:13px;
color:#64748b;
">
※ 최초 검색 시 위치 정보를 찾는데 시간이 조금 걸릴 수 있습니다.
</div>
  `;

  if(btn){
    btn.style.display = "none";
  }

  modal.style.display = "flex";
}

function preloadLocation(){
  if(!navigator.geolocation){
    return;
  }

navigator.geolocation.getCurrentPosition(

  function(pos){

    userLat = pos.coords.latitude;
    userLng = pos.coords.longitude;
    console.log("사전 위치:", userLat, userLng, "정확도:", pos.coords.accuracy);

  },

  function(err){
    console.log("위치 사전 요청 실패", err);
  },

  {
    enableHighAccuracy:true,
    timeout:10000,
    maximumAge:0
  }

);}


L.tileLayer(
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap"
  }
).addTo(map);

let markerGroup = L.markerClusterGroup({
  showCoverageOnHover:false,
  spiderfyOnMaxZoom:true,
  disableClusteringAtZoom:15,
  chunkedLoading:true
});

let routeLine = null;
map.addLayer(markerGroup);

function clearRoute(){

  if(routeLine){
    map.removeLayer(routeLine);
    routeLine = null;
  }

  if(window.mobileRouteLine && window.mobileLeafletMap){
    window.mobileLeafletMap.removeLayer(window.mobileRouteLine);
    window.mobileRouteLine = null;
  }

}

function setLoading(show){
  document.getElementById("loadingBox").style.display = show ? "block" : "none";
}

function calcDistance(lat1, lng1, lat2, lng2){

  const R = 6371000;

  const dLat = (lat2-lat1) * Math.PI/180;
  const dLng = (lng2-lng1) * Math.PI/180;

  const a =
    Math.sin(dLat/2)*Math.sin(dLat/2) +
    Math.cos(lat1*Math.PI/180) *
    Math.cos(lat2*Math.PI/180) *
    Math.sin(dLng/2)*Math.sin(dLng/2);

  const c = 2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));

  return R*c;

}


function closeMsg(){
  const modal = document.getElementById("msgModal");
  if(modal){
    modal.style.display = "none";
  }
}

function showMobileResults(items, userLat, userLng){
  history.pushState({mobileResult:true}, "");

  const panel = document.getElementById("mobileResultPanel");
  const list = document.getElementById("mobileResultList");

  if(!panel || !list) return;

  panel.style.display = "flex";
  list.innerHTML = "";

  items.forEach(item => {
    let distText = "";

    if(userLat !== null && userLng !== null){
      const dist = Math.round(
        calcDistance(userLat, userLng, item.위도, item.경도)
      );
      distText = `<span class="mobile-result-distance">${dist} m</span>`;
    }

    const el = document.createElement("div");
    el.className = "mobile-result-item";
    el.innerHTML = `
      <b>${item.구분}</b><br>
      ${item.시군구} ${item.읍면동}<br>
      ${distText}
    `;

    el.onclick = function(){

  if(window.mobileLeafletMap){

    window.mobileLeafletMap.flyTo(
      [item.위도,item.경도],
      16,
      {
        duration:1.2,
        easeLinearity:0.25
      }
    );

    window.mobileLeafletMap.once("moveend", function(){

      if(window.mobileMarkerGroup){

        window.mobileMarkerGroup.eachLayer(function(layer){

          if(layer.itemData && layer.itemData.순번 === item.순번){
            layer.openPopup();
          }

        });

      }

    });

  }

};

    list.appendChild(el);
  });

  document.getElementById("mobileResultCount").textContent = items.length;
}

function createCategoryChecks(){
  const box = document.getElementById("categoryBox");
  box.innerHTML = "";
  CATEGORY_LIST.forEach(cat => {
    const color = CATEGORY_COLORS[cat] || "#334155";
    const item = document.createElement("label");
    item.className = "check-item";
    item.innerHTML = `
      <input type="checkbox" class="category-check" value="${cat}">
      <span class="dot" style="background:${color}"></span>
      <span>${cat}</span>
    `;
    box.appendChild(item);
  });
}

function fillProvinces(provinces){

  const select = document.getElementById("province");

  select.innerHTML = '<option value="">전체</option>';

  provinces.forEach(p=>{

    const op = document.createElement("option");

    op.value = p;

    op.textContent = p;

    select.appendChild(op);

  });

}

function fillCities(cities){
  const select = document.getElementById("city");
  const current = select.value;
  select.innerHTML = '<option value="">전체</option>';
  cities.forEach(city => {
    const op = document.createElement("option");
    op.value = city;
    op.textContent = city;
    select.appendChild(op);
  });
  if(cities.includes(current)) select.value = current;
}

function fillTowns(towns){
  const select = document.getElementById("town");
  const current = select.value;
  select.innerHTML = '<option value="">전체</option>';
  towns.forEach(town => {
    const op = document.createElement("option");
    op.value = town;
    op.textContent = town;
    select.appendChild(op);
  });
  if(towns.includes(current)) select.value = current;
}

function getCheckedCategories(){
  return Array.from(document.querySelectorAll(".category-check:checked")).map(el => el.value);
}

function buildMarkerIcon(color){
  return L.divIcon({
    className: "",
    html: `<div class="custom-marker" style="background:${color};"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -8]
  });
}

function buildUserIcon(){
  return L.divIcon({
    className:"",
    html:`
      <div class="user-marker-wrap">
        <div class="user-marker-pulse"></div>
        <div class="user-marker-dot"></div>
      </div>
    `,
    iconSize:[28,28],
    iconAnchor:[14,14]
  });
}

function drawUserLocation(lat,lng){

  // 기존 위치 마커 제거
  if(window.userCircle){
    map.removeLayer(window.userCircle);
  }

  if(window.userMarker){
    map.removeLayer(window.userMarker);
  }

  // 내 위치 원 (크게)
  window.userCircle = L.circle(
    [lat,lng],
    {
      radius:180,        // ⭐ 크기 (미터)
      color:"#22c55e",
      fillColor:"#22c55e",
      fillOpacity:0.25,
      weight:2
    }
  ).addTo(map);

  // 내 위치 점
  window.userMarker = L.marker(
    [lat,lng],
    { icon: buildUserIcon() }
  ).addTo(map);

}




function escapeHtml(text){
  if(text === null || text === undefined) return "";
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadMeta(){
  const res = await fetch("/meta");
  const data = await res.json();
  fillProvinces(data.provinces || []);
  fillCities(data.cities || []);
  fillTowns(data.towns || []);
}

async function updateCities(){

  const province = document.getElementById("province").value;

  const res = await fetch(
    "/cities?province=" + encodeURIComponent(province)
  );

  const data = await res.json();

  fillCities(data.cities || []);

  // 시군구 바뀌면 읍면동도 다시 로드
  updateTowns();

}

async function updateTowns(){
  const province = document.getElementById("province").value;
  const city = document.getElementById("city").value;
  const res = await fetch(`/towns?province=${encodeURIComponent(province)}&city=${encodeURIComponent(city)}`);
  const data = await res.json();
  fillTowns(data.towns || []);
}

async function loadAllMarkers(){

  if(!ALL_DATA_CACHE){
  const res = await fetch("/data");
  const result = await res.json();
  ALL_DATA_CACHE = result.data;
}

const data = ALL_DATA_CACHE;

  markerGroup.clearLayers();

  const bounds = [];

  data.forEach(item=>{

    const icon = buildMarkerIcon(item.마커색상);

    const marker = L.marker([item.위도,item.경도],{icon});
    marker.itemData = item;
    const popupHtml = `
<div class="popup-wrap">

<img class="popup-img" src="${item.사진URL}">

<div class="popup-title">${escapeHtml(item.구분)}</div>

<div class="popup-meta">
시군구: ${escapeHtml(item.시군구)}<br>
읍면동: ${escapeHtml(item.읍면동)}<br>
주소: ${escapeHtml(item.주소)}
</div>

<div class="popup-desc">
${escapeHtml(item.사고설명)}
</div>

<div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:6px;">

<a 
href="https://map.naver.com/v5/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#03C75A;
color:#ffffff;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
네이버 길찾기
</a>

<a 
href="https://map.kakao.com/link/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#FEE500;
color:#191919;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
카카오 길찾기
</a>

</div>

</div>
`;

    marker.bindPopup(popupHtml,{maxWidth:290});

    markerGroup.addLayer(marker);

    bounds.push([item.위도,item.경도]);

  });

  if(bounds.length>0){
    map.setView([34.85,126.90],9);
}

}

async function loadData(){

  clearRoute();

  if(isMobile()){
    openMobileMap();
  }

  setLoading(true);

map.once("moveend", () => {
  setLoading(false);
});

    markerGroup.clearLayers();

  const province = document.getElementById("province").value;
  const city = document.getElementById("city").value;
  const town = document.getElementById("town").value;
  const categories = getCheckedCategories();

  const params = new URLSearchParams();
  if(province) params.append("province", province);
  if(city) params.append("city", city);
  if(town) params.append("town", town);
  categories.forEach(cat => params.append("category", cat));

  try{

    const res = await fetch("/data?" + params.toString());
    const result = await res.json();
    const data = result.data;
    const total = result.total;

fetch("/log_search", {
  method:"POST",
  headers:{
    "Content-Type":"application/json"
  },
  body:JSON.stringify({
    province:province,
    city:city,
    town:town,
    categories:categories,
    result_count:total
  })
});

    const bounds = [];

    data.forEach(item => {

  
    const icon = buildMarkerIcon(item.마커색상);
    const marker = L.marker([item.위도, item.경도], { icon });
    marker.itemData = item;
      const popupHtml = `
        <div class="popup-wrap">

          <img class="popup-img" src="${item.사진URL}">

          <div class="popup-title">${escapeHtml(item.구분)}</div>

          <div class="popup-meta">
            시군구: ${escapeHtml(item.시군구)}<br>
            읍면동: ${escapeHtml(item.읍면동)}<br>
            주소: ${escapeHtml(item.주소)}
          </div>

          <div class="popup-desc">
            ${escapeHtml(item.사고설명)}
          </div>

          
<div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:6px;">

<a 
href="https://map.naver.com/v5/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#03C75A;
color:#ffffff;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
네이버 길찾기
</a>

<a 
href="https://map.kakao.com/link/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#FEE500;
color:#191919;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
카카오 길찾기
</a>

</div>
                  </div>
      `;

      marker.bindPopup(popupHtml, { maxWidth: 290 });
      markerGroup.addLayer(marker);
bounds.push([item.위도, item.경도]);

});


  if(bounds.length > 0){
    map.fitBounds(bounds, { padding:[40,40] });
    map.once("moveend", closeMsg);
  }else{
    map.setView([34.85, 126.90], 9);
    showMsg("조건에 맞는 데이터가 없습니다.");
  }


if(isMobile()){
  syncToMobileMap(data);
}

// 조회 결과 목록 표시 (최대 10개)
// 결과가 5000개 미만일 때만 목록 표시
// 조회 결과 목록 표시 (5000개 미만일 때만)
// 조회 결과 목록 표시 (5000개 미만일 때만)
if(!isMobile()){
  if(total < 5000){
    showResultList(data, userLat, userLng);
  }else{
    const panel = document.getElementById("mobileResultPanel");
    if(panel){
      panel.style.display = "none";
    }
  }
}  }catch(e){
    showMsg("데이터를 불러오는 중 오류가 발생했습니다.");
    console.error(e);


  }finally{
  }
}

function resetFilters(){

  // 시군구 초기화
  document.getElementById("city").value = "";

  // 읍면동 초기화
  document.getElementById("town").value = "";

  // 구분 체크 해제
  document.querySelectorAll(".category-check")
  .forEach(el => el.checked = false);


  // PC 지도 마커 삭제
  if(markerGroup){
    markerGroup.clearLayers();
  }

  // 모바일 지도 마커 삭제
  if(window.mobileMarkerGroup){
    window.mobileMarkerGroup.clearLayers();
  }

  // 지도 위치 초기화
  map.setView([34.85,126.90],9);

  // ⭐ 경로선 삭제
  if(routeLine){
    map.removeLayer(routeLine);
    routeLine = null;
  }

  // 모바일 결과 패널 닫기
  const result = document.getElementById("mobileResultPanel");
  if(result){
    result.style.display = "none";
  }

  // 전체 마커 다시 표시
  loadAllMarkers();

}

window.addEventListener("load", function(){
  setTimeout(()=>{
    map.invalidateSize();
  },1000);
});

window.addEventListener("DOMContentLoaded", function(){

  preloadLocation();

  createCategoryChecks();

  loadMeta().then(()=>{
    document.getElementById("city").addEventListener("change", updateTowns);
    document.getElementById("province").addEventListener("change", updateCities);
    loadAllMarkers();
  });

  const destInput = document.getElementById("destInput");

if(destInput){
  destInput.addEventListener(
  "input",
  debounce(function(){
    searchPlaceSuggestions(this.value, "destInput");
  }, 400)
);
}

const startInput = document.getElementById("startInput");

if(startInput){
  startInput.addEventListener(
  "input",
  debounce(function(){
    searchPlaceSuggestions(this.value, "startInput");
  }, 400)
);
}


});


function openAdminStats(){

  const modal = document.getElementById("adminPwModal");
  const input = document.getElementById("adminPwInput");
  const msg = document.getElementById("adminPwMsg");

  if(!modal || !input){
    return;
  }

  input.value = "";
  msg.textContent = "";
  modal.style.display = "flex";

  setTimeout(()=>{
    input.focus();
  },100);

}
function closeAdminPwModal(){

  const modal = document.getElementById("adminPwModal");

  if(modal){
    modal.style.display = "none";
  }

}

function submitAdminPw(){

  const input = document.getElementById("adminPwInput");
  const msg = document.getElementById("adminPwMsg");

  if(!input){
    return;
  }

  if(input.value !== "1234"){
    if(msg){
      msg.textContent = "암호가 틀렸습니다.";
    }
    input.focus();
    return;
  }

  window.location.href = "/stats";

}

function isMobile(){
  return window.innerWidth < 900;
}

function openSexOffenderApp(){

  const ua = navigator.userAgent || "";
  const isAndroid = /Android/i.test(ua);
  const isIOS = /iPhone|iPad|iPod/i.test(ua);

  const pcUrl = "https://www.sexoffender.go.kr";
  const playStoreUrl = "https://play.google.com/store/apps/details?id=com.mogef_android1.app";
  const appStoreUrl = "https://apps.apple.com/kr/app/%EC%84%B1%EB%B2%94%EC%A3%84%EC%9E%90-%EC%95%8C%EB%A6%BCe/id896534884";

  if(!isAndroid && !isIOS){
    window.open(pcUrl, "_blank");
    return;
  }

  if(isAndroid){

    const intentUrl =
      "intent://#Intent;"
      + "scheme=sexoffender;"
      + "package=com.mogef_android1.app;"
      + "S.browser_fallback_url=" + encodeURIComponent(playStoreUrl) + ";"
      + "end";

    window.location.href = intentUrl;
    return;
  }

  if(isIOS){
    window.location.href = appStoreUrl;
    return;
  }
}

function openMobileMap(){

  if(!history.state || !history.state.mobileMap){
    history.pushState({mobileMap:true}, "");
  }

  if(!isMobile()) return;

  const popup = document.getElementById("mobileMapPopup");
  popup.style.display = "flex";

  const mapDiv = document.getElementById("mobileMap");

  if(!window.mobileLeafletMap){

    

    window.mobileLeafletMap = L.map(mapDiv).setView([34.85, 126.90], 9);

    L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { maxZoom: 19 }
    ).addTo(window.mobileLeafletMap);

    window.mobileMarkerGroup = L.markerClusterGroup({
      showCoverageOnHover:false,
      spiderfyOnMaxZoom:true,
      disableClusteringAtZoom:15,
      chunkedLoading:true
    });

    window.mobileLeafletMap.addLayer(window.mobileMarkerGroup);
  }

  setTimeout(()=>{
    window.mobileLeafletMap.invalidateSize();
  }, 200);
}

function closeMobileMap(){

  document.getElementById("mobileMapPopup").style.display = "none";

  const result = document.getElementById("mobileResultPanel");

  if(result){
    result.style.display = "none";
  }

}


function syncToMobileMap(items, userLat=null, userLng=null, radiusMeter=null){

  if(!isMobile()) return;

  if(userLat && userLng){

    items.sort((a,b)=>{

      const da = calcDistance(userLat,userLng,a.위도,a.경도);
      const db = calcDistance(userLat,userLng,b.위도,b.경도);

      return da-db;

    });

  }




  openMobileMap();

  window.mobileMarkerGroup.clearLayers();


  const bounds = [];

  if(userLat !== null && userLng !== null){

  const userCircle = L.circle(
    [userLat, userLng],
    {
      radius: 160,
      color:"#22c55e",
      fillColor:"#22c55e",
      fillOpacity:0.28,
      weight:3
    }
  );

  const userMarker = L.marker(
    [userLat, userLng],
    { icon: buildUserIcon() }
  );

  window.mobileMarkerGroup.addLayer(userCircle);
  window.mobileMarkerGroup.addLayer(userMarker);

  bounds.push([userLat, userLng]);

  if(radiusMeter){
    const circle = L.circle(
      [userLat, userLng],
      {
        radius: radiusMeter,
        color:"#2563eb",
        fillColor:"#2563eb",
        fillOpacity:0.08
      }
    );
    window.mobileMarkerGroup.addLayer(circle);
  }
}

items.forEach(item=>{

  const icon = buildMarkerIcon(item.마커색상);

  const marker = L.marker([item.위도,item.경도],{icon});
  marker.itemData = item;

  const popupHtml = `
  <div class="popup-wrap">

  <img class="popup-img" src="${item.사진URL}">

  <div class="popup-title">${escapeHtml(item.구분)}</div>

  <div class="popup-meta">
  시군구: ${escapeHtml(item.시군구)}<br>
  읍면동: ${escapeHtml(item.읍면동)}<br>
  주소: ${escapeHtml(item.주소)}
  </div>

  <div class="popup-desc">
  ${escapeHtml(item.사고설명)}
  </div>

  <div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:6px;">

  <a 
  href="https://map.naver.com/v5/search/${encodeURIComponent(item.주소)}"
  target="_blank"
  style="
  display:block;
  text-align:center;
  background:#03C75A;
  color:#ffffff;
  font-weight:700;
  padding:8px;
  border-radius:8px;
  text-decoration:none;
  font-size:13px;
  ">
  네이버 길찾기
  </a>

  <a 
  href="https://map.kakao.com/link/search/${encodeURIComponent(item.주소)}"
  target="_blank"
  style="
  display:block;
  text-align:center;
  background:#FEE500;
  color:#191919;
  font-weight:700;
  padding:8px;
  border-radius:8px;
  text-decoration:none;
  font-size:13px;
  ">
  카카오 길찾기
  </a>

  </div>

  </div>
  `;

  marker.bindPopup(popupHtml,{maxWidth:290});

  window.mobileMarkerGroup.addLayer(marker);

  bounds.push([item.위도,item.경도]);

});


  setTimeout(()=>{
    window.mobileLeafletMap.invalidateSize();

    if(bounds.length > 0){
      window.mobileLeafletMap.fitBounds(bounds, { padding:[40,40] });
    }else{
      window.mobileLeafletMap.flyTo(
  [34.85,126.90],
  9,
  {
    duration:1.2,
    easeLinearity:0.25
  }
);
    }

  }, 250);


// 🔵 여기 추가
showMobileResults(items,userLat,userLng);
}

async function findNearestToilet(){

  clearRoute();   // ⭐ 추가

  showLoadingLocation();   // 추가

  if(!navigator.geolocation){
    showMsg("GPS를 지원하지 않는 기기입니다.");
    return;
  }

  navigator.geolocation.getCurrentPosition(

    pos=>{

      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;

      userLat = lat;
      userLng = lng;

      runNearestSearch(lat,lng,"공중화장실");

    },

    err=>{
      closeMsg();
      showMsg("위치를 가져올 수 없습니다.");
    },

    {
      enableHighAccuracy:true,
      timeout:10000,
      maximumAge:0
    }

  );

}



async function findNearestDanger(){

  clearRoute();   // ⭐ 추가

  showLoadingLocation();

  if(!navigator.geolocation){
    showMsg("GPS를 지원하지 않는 기기입니다.");
    return;
  }

  navigator.geolocation.getCurrentPosition(

    pos=>{

      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;

      userLat = lat;
      userLng = lng;

      runNearestSearch(lat,lng,"상습결빙지역");

    },

    err=>{
      closeMsg();
      showMsg("위치를 가져올 수 없습니다.");
    },

    {
      enableHighAccuracy:true,
      timeout:10000,
      maximumAge:0
    }

  );

}

async function runNearestSearch(lat,lng,targetType){

  if(!ALL_DATA_CACHE){
  const res = await fetch("/data");
  const result = await res.json();
  ALL_DATA_CACHE = result.data;
}

const data = ALL_DATA_CACHE;

  const radius = 5000;

  const filtered = [];

  data.forEach(item=>{
    
    console.log(item.구분,targetType);

    if(item.구분 !== targetType) return;

    const dist = map.distance(
      [lat,lng],
      [item.위도,item.경도]
    );

    if(dist <= radius){

      item._dist = dist;

      filtered.push(item);

    }

  });

  filtered.sort((a,b)=>a._dist-b._dist);
  filtered.splice(10);

  if(filtered.length === 0){
    closeMsg();   // ⭐ 추가
    showMsg("주변에 데이터가 없습니다.");

    return;

  }

if(isMobile()){
  syncToMobileMap(filtered,lat,lng,5000);
  closeMsg();   // ⭐ 이거 추가
  return;
}

const bounds = [];

bounds.push([lat,lng]);

filtered.forEach(item=>{
  bounds.push([item.위도,item.경도]);
});

map.fitBounds(bounds,{
  padding:[60,60]
});

map.once("moveend", closeMsg);

// ⭐ moveend 안 생길 경우 대비
setTimeout(closeMsg, 800);

markerGroup.clearLayers();

drawUserLocation(lat, lng);
L.circle(
  [lat,lng],
  {
    radius: radius,
    color:"#2563eb",
    fillColor:"#2563eb",
    fillOpacity:0.08
  }
).addTo(markerGroup);

filtered.forEach(item=>{

  const icon = buildMarkerIcon(item.마커색상);

const marker = L.marker(
  [item.위도,item.경도],
  {icon}
);
marker.itemData = item;

const popupHtml = `

<div class="popup-wrap">

<img class="popup-img" src="${item.사진URL}">

<div class="popup-title">${item.구분}</div>

<div class="popup-meta">
시군구: ${item.시군구}<br>
읍면동: ${item.읍면동}<br>
주소: ${item.주소}
</div>

<div class="popup-desc">
${item.사고설명}
</div>

<div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:6px;">

<a 
href="https://map.naver.com/v5/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#03C75A;
color:#ffffff;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
네이버 길찾기
</a>

<a 
href="https://map.kakao.com/link/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#FEE500;
color:#191919;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
카카오 길찾기
</a>

</div>

</div>
`;

marker.bindPopup(popupHtml,{maxWidth:290});

markerGroup.addLayer(marker);


});

showResultList(filtered,lat,lng);

}



async function findRadius(km){

  if(userLat && userLng){
    runRadius(userLat,userLng,km);
    return;
  }

  if(!navigator.geolocation){
    showMsg("GPS를 지원하지 않는 기기입니다.");
    return;
  }

  navigator.geolocation.getCurrentPosition(

    pos=>{

      closeMsg();
      userLat = pos.coords.latitude;
      userLng = pos.coords.longitude;

      runRadius(userLat,userLng,km);

    },

    err=>{
     closeMsg();   // ⭐ 추가

      showMsg("위치를 가져올 수 없습니다.");
    },

    {
      enableHighAccuracy:true,
      timeout:10000,
      maximumAge:0
    }

  );

}


function showResultList(items, userLat, userLng){

  const panel = document.getElementById("mobileResultPanel");
  const list = document.getElementById("mobileResultList");

  panel.style.display = "flex";
  list.innerHTML = "";

  items.forEach(item=>{

    let distText = "";

    if(userLat && userLng){
      const dist = Math.round(
        calcDistance(userLat,userLng,item.위도,item.경도)
      );
      distText = dist + " m";
    }

    const el = document.createElement("div");

    el.className = "mobile-result-item";

    el.innerHTML = `
      <b>${item.구분}</b><br>
      ${item.시군구} ${item.읍면동}<br>
      <span class="mobile-result-distance">${distText}</span>
    `;
    el.onclick = function(){

  map.flyTo([item.위도,item.경도],16);

  map.once("moveend", function(){

    markerGroup.eachLayer(function(layer){

      if(layer.itemData && layer.itemData.순번 === item.순번){
        layer.openPopup();
      }

    });

  });

  if(window.mobileLeafletMap){

    window.mobileLeafletMap.flyTo(
      [item.위도,item.경도],
      16,
      {
        duration:1.2,
        easeLinearity:0.25
      }
    );

    window.mobileLeafletMap.once("moveend", function(){

      if(window.mobileMarkerGroup){

        window.mobileMarkerGroup.eachLayer(function(layer){

          if(layer.itemData && layer.itemData.순번 === item.순번){
            layer.openPopup();
          }

        });

      }

    });

  }

};


    list.appendChild(el);

  });

  document.getElementById("mobileResultCount").textContent = items.length;

}

async function runRadius(lat,lng,km){

  if(!ALL_DATA_CACHE){
  const res = await fetch("/data");
  const result = await res.json();
  ALL_DATA_CACHE = result.data;
}

const data = ALL_DATA_CACHE;

  markerGroup.clearLayers();

  const radiusMeter = km * 1000;

  drawUserLocation(lat,lng);

  L.circle(
    [lat,lng],
    {
      radius: radiusMeter,
      color:"#2563eb",
      fillColor:"#2563eb",
      fillOpacity:0.08
    }
  ).addTo(markerGroup);

  const filtered = [];

  data.forEach(item=>{

    const dist = map.distance(
      [lat,lng],
      [item.위도,item.경도]
    );

    if(dist <= radiusMeter){
      filtered.push(item);
    }

  });

  if(filtered.length === 0){
    showMsg(`${km}km 안에 위험지역이 없습니다.`);
    return;
  }

  if(isMobile()){
    syncToMobileMap(filtered,lat,lng,radiusMeter);
  }

}

window.addEventListener("DOMContentLoaded", function(){

  const locBtn = document.getElementById("locBtn");

  if(locBtn){
    locBtn.onclick = function(){

      if(!navigator.geolocation){
        showMsg("GPS를 지원하지 않는 기기입니다.");
        return;
      }

navigator.geolocation.getCurrentPosition(

pos=>{

const lat = pos.coords.latitude;
const lng = pos.coords.longitude;

userLat = lat;
userLng = lng;

console.log("내 위치 버튼:", lat, lng, "정확도:", pos.coords.accuracy);

markerGroup.clearLayers();

map.flyTo([lat, lng], 17);

// ⭐ 내 위치 표시
drawUserLocation(lat,lng);

if(window.mobileLeafletMap){
  window.mobileLeafletMap.flyTo(
  [lat,lng],
  17,
  {
    duration:1.2,
    easeLinearity:0.25
  }
);
}

if(window.mobileMarkerGroup){
  window.mobileMarkerGroup.clearLayers();

  const userCircle = L.circle(
    [lat, lng],
    {
      radius:180,
      color:"#22c55e",
      fillColor:"#22c55e",
      fillOpacity:0.28,
      weight:3
    }
  );

  const userMarker = L.marker(
    [lat, lng],
    { icon: buildUserIcon() }
  );

  window.mobileMarkerGroup.addLayer(userCircle);
  window.mobileMarkerGroup.addLayer(userMarker);
}
},

err=>{
  showMsg("위치를 가져올 수 없습니다.");
},

{
  enableHighAccuracy:true,
  timeout:10000,
  maximumAge:0
}

);

    };
  }

});
window.addEventListener("popstate", function(){
clearRoute();   // ⭐ 추가

const popup = document.getElementById("mobileMapPopup");
const result = document.getElementById("mobileResultPanel");

if(result){
  result.style.display = "none";
}

if(popup){
  popup.style.display = "none";
}

});


window.addEventListener("DOMContentLoaded", function(){

const mobileBtn = document.getElementById("mobileLocBtn");

if(mobileBtn){

mobileBtn.onclick = function(){

if(!navigator.geolocation){
  alert("GPS를 지원하지 않습니다.");
  return;
}

navigator.geolocation.getCurrentPosition(

pos=>{
const lat = pos.coords.latitude;
const lng = pos.coords.longitude;

userLat = lat;
userLng = lng;

console.log("모바일 위치 버튼:", lat, lng, "정확도:", pos.coords.accuracy);

if(window.mobileLeafletMap){

  window.mobileLeafletMap.flyTo(
  [lat,lng],
  17,
  {
    duration:1.2,
    easeLinearity:0.25
  }
);

  if(window.mobileMarkerGroup){
  window.mobileMarkerGroup.clearLayers();

  const userCircle = L.circle(
    [lat, lng],
    {
      radius: 160,
      color:"#22c55e",
      fillColor:"#22c55e",
      fillOpacity:0.28,
      weight:3
    }
  );

  const userMarker = L.marker(
    [lat, lng],
    { icon: buildUserIcon() }
  );

  window.mobileMarkerGroup.addLayer(userCircle);
  window.mobileMarkerGroup.addLayer(userMarker);
}

}},

err=>{
  closeMsg();
  showMsg("위치를 가져올 수 없습니다.");
},

{
  enableHighAccuracy:true,
  timeout:10000,
  maximumAge:0
}

);
};

}

});

let loadingStartTime = 0;

function openRouteSearch(){
  document.getElementById("routePopup").style.display="flex";
}

function closeRoutePopup(){
  document.getElementById("routePopup").style.display="none";

  const box = document.getElementById("destSuggestBox");
  if(box){
    box.style.display = "none";
    box.innerHTML = "";
  }
}


document.addEventListener("click", function(e){

  const input = document.getElementById("destInput");
  const box = document.getElementById("destSuggestBox");

  if(!input || !box){
    return;
  }


  if(e.target !== input && !box.contains(e.target)){
    box.style.display = "none";
  }

});


async function searchPlaceSuggestions(query, inputId){

  const box = document.getElementById("destSuggestBox");

  if(!box){
    return;
  }

  query = query.trim();

  if(query.length < 3){
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  try{

    const res = await fetch("/search_place?q=" + encodeURIComponent(query));
    const data = await res.json();

    box.innerHTML = "";

    if(!data.documents || data.documents.length === 0){
      box.innerHTML = `
        <div style="padding:12px;font-size:13px;color:#64748b;">
          검색 결과가 없습니다.
        </div>
      `;
      box.style.display = "block";
      return;
    }

    data.documents.slice(0,5).forEach(place=>{

      const item = document.createElement("div");

      item.style.padding="10px 12px";
      item.style.borderBottom="1px solid #f1f5f9";
      item.style.cursor="pointer";
      item.style.fontSize="13px";
      item.style.lineHeight="1.45";

      item.innerHTML=`
        <div style="font-weight:700;color:#111827;">
          ${escapeHtml(place.place_name || "")}
        </div>
        <div style="color:#64748b;font-size:12px;">
          ${escapeHtml(place.address_name || "")}
        </div>
      `;

      item.onclick=function(){

        const input=document.getElementById(inputId);

        if(input){
          input.value=place.place_name || "";
        }

        box.style.display="none";
        box.innerHTML="";
      };

      box.appendChild(item);

    });

    box.style.display="block";

  }catch(err){

    console.error("자동완성 검색 오류:",err);
    box.style.display="none";
    box.innerHTML="";

  }

}

async function geocodeAddress(query){

  query = query.trim();

  if(!query){
    return null;
  }

  const res = await fetch("/search_place?q=" + encodeURIComponent(query));
  const data = await res.json();

  if(data.documents && data.documents.length > 0){
    return {
      lat: parseFloat(data.documents[0].y),
      lng: parseFloat(data.documents[0].x)
    };
  }

  return null;

}


function distancePointToLine(px,py,x1,y1,x2,y2){

  const A = px-x1;
  const B = py-y1;
  const C = x2-x1;
  const D = y2-y1;

  const dot = A*C + B*D;
  const len = C*C + D*D;

  let param = -1;

  if(len!==0){
    param = dot/len;
  }

  let xx,yy;

  if(param<0){
    xx=x1;
    yy=y1;
  }else if(param>1){
    xx=x2;
    yy=y2;
  }else{
    xx=x1 + param*C;
    yy=y1 + param*D;
  }

  return calcDistance(px,py,xx,yy);

}


async function getRoadRoute(startLat,startLng,endLat,endLng){

  const url =
  "https://router.project-osrm.org/route/v1/driving/"
  + startLng + "," + startLat + ";"
  + endLng + "," + endLat
  + "?overview=full&geometries=geojson";

  const res = await fetch(url);
  const data = await res.json();

  if(!data.routes || data.routes.length === 0){
    return null;
  }

  return data.routes[0].geometry.coordinates;

}

function distancePointToRoute(lat, lng, routeLatLngs){

  let minDist = Infinity;

  for(let i = 0; i < routeLatLngs.length - 1; i++){

    const p1 = routeLatLngs[i];
    const p2 = routeLatLngs[i + 1];

    const dist = distancePointToLine(
      lng, lat,
      p1[1], p1[0],
      p2[1], p2[0]
    );

    if(dist < minDist){
      minDist = dist;
    }

  }

  return minDist;
}

async function runRouteSearch(){
  showLoadingLocation();   // ⭐ 추가

  closeRoutePopup();   // ⭐ 여기 추가


  clearRoute();

  if(isMobile()){
    openMobileMap();
    await new Promise(r => setTimeout(r,300));
  }

  const start = document.getElementById("startInput").value.trim();
  const dest = document.getElementById("destInput").value.trim();

  if(!dest){
    showMsg("도착지를 입력하세요.");
    return;
  }

  let startLat = userLat;
  let startLng = userLng;

  if(start){
    const startGeo = await geocodeAddress(start);

    if(!startGeo){
      showMsg("출발지를 찾을 수 없습니다.");
      return;
    }

    startLat = startGeo.lat;
    startLng = startGeo.lng;
  }else{
    if(userLat === null || userLng === null){
      showMsg("출발지를 입력하거나 내 위치를 먼저 확인해주세요.");
      return;
    }
  }

  const endGeo = await geocodeAddress(dest);

  if(!endGeo){
    showMsg("도착지를 찾을 수 없습니다.");
    return;
  }

  const endLat = endGeo.lat;
  const endLng = endGeo.lng;
  const road = await getRoadRoute(startLat,startLng,endLat,endLng);

let routeLatLngs = [];

if(road){
  routeLatLngs = road.map(c => [c[1], c[0]]);
}else{
  routeLatLngs = [
    [startLat, startLng],
    [endLat, endLng]
  ];
}

 if(!ALL_DATA_CACHE){
  const res = await fetch("/data");
  const result = await res.json();
  ALL_DATA_CACHE = result.data;
}

const data = ALL_DATA_CACHE;

const radius = 50;

const filtered = [];

data.forEach(item=>{

  const dist = distancePointToRoute(
    item.위도,
    item.경도,
    routeLatLngs
  );
  
  if(dist <= radius){
    filtered.push(item);
  }

});

  markerGroup.clearLayers();

  filtered.forEach(item=>{
    const icon = buildMarkerIcon(item.마커색상);
    const marker = L.marker([item.위도, item.경도], {icon});
    marker.itemData = item;

    const popupHtml = `
<div class="popup-wrap">

<img class="popup-img" src="${item.사진URL}">

<div class="popup-title">${item.구분}</div>

<div class="popup-meta">
${item.시군구} ${item.읍면동}<br>
${item.주소}
</div>

<div class="popup-desc">
${item.사고설명}
</div>

<div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:6px;">

<a 
href="https://map.naver.com/v5/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#03C75A;
color:#ffffff;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
네이버 길찾기
</a>

<a 
href="https://map.kakao.com/link/search/${encodeURIComponent(item.주소)}"
target="_blank"
style="
display:block;
text-align:center;
background:#FEE500;
color:#191919;
font-weight:700;
padding:8px;
border-radius:8px;
text-decoration:none;
font-size:13px;
">
카카오 길찾기
</a>

</div>

</div>
`;

    marker.bindPopup(popupHtml,{maxWidth:290});
    markerGroup.addLayer(marker);
  });

  if(routeLine){
    map.removeLayer(routeLine);
  }

routeLine = L.polyline(
  routeLatLngs,
  {color:"#2563eb", weight:5}
).addTo(map);

if(isMobile() && window.mobileLeafletMap){

  if(window.mobileRouteLine){
    window.mobileLeafletMap.removeLayer(window.mobileRouteLine);
  }

  window.mobileRouteLine = L.polyline(
    routeLatLngs,
    {color:"#2563eb", weight:5}
  ).addTo(window.mobileLeafletMap);

}

  map.fitBounds(
    [
      [startLat, startLng],
      [endLat, endLng]
    ],
    {padding:[60,60]}
  );

  // map.once("moveend", closeMsg);
  // setTimeout(closeMsg,800);

  const toiletCount = filtered.filter(x=>x.구분==="공중화장실").length;
  const iceCount = filtered.filter(x=>x.구분==="상습결빙지역").length;
  const accidentCount = filtered.filter(x=>x.구분==="교통사고위험지역").length;

  showMsg(
      `경로 주변 시설\n\n🚻 공중화장실 ${toiletCount}개\n⚠️ 상습결빙지역 ${iceCount}개\n🚗 교통사고위험지역${accidentCount}개`
  );

  showResultList(filtered, startLat, startLng);

  if(isMobile()){
  syncToMobileMap(filtered,startLat,startLng);
}





  if(isMobile()){
  document.getElementById("mobileResultPanel").style.display="flex";
}


}


function debounce(fn, delay){

  let timer;

  return function(...args){

    clearTimeout(timer);

    timer = setTimeout(()=>{
      fn.apply(this, args);
    }, delay);

  };

}

</script>



<div class="mobile-map-popup" id="mobileMapPopup">

  <div class="mobile-map-header">
  지도 보기

  <div style="display:flex; gap:6px;">

    
    <button class="mobile-map-close" onclick="closeMobileMap()">
    닫기
    </button>

  </div>

</div>

  <div id="mobileMap" class="mobile-map"></div>
  <button id="mobileLocBtn">📍</button>

  <div class="map-legend">


    <div class="map-legend-item">
      <span class="map-legend-dot" style="background:#06b6d4"></span>
      상습결빙지역
    </div>

    <div class="map-legend-item">
      <span class="map-legend-dot" style="background:#f59e0b"></span>
      공중화장실
    </div>

<div class="map-legend-item">
  <span class="map-legend-dot" style="background:#ef4444"></span>
  교통사고위험지역
</div>

<div class="map-legend-item">
  <span class="map-legend-dot" style="background:#2563eb"></span>
  내 위치
</div>


  </div>

</div>



<div id="msgModal" style="
position:fixed;
inset:0;
background:rgba(0,0,0,0.45);
display:none;
align-items:center;
justify-content:center;
z-index:5000;
">

<div id="msgBox" style="
background:#ffffff;
padding:24px 22px;
border-radius:18px;
min-width:320px;
max-width:90vw;
text-align:center;
box-shadow:0 18px 40px rgba(0,0,0,0.18);
">

<div id="msgText" style="
font-size:16px;
margin-bottom:18px;
line-height:1.7;
white-space:pre-line;
color:#0f172a;
font-weight:700;
"></div>

<button id="msgBtn" onclick="closeMsg()" style="
background:#2563eb;
border:none;
color:white;
padding:8px 16px;
border-radius:8px;
font-weight:700;
cursor:pointer;
">
확인
</button>

</div>
</div>

<div id="routePopup" style="
position:fixed;
inset:0;
background:rgba(0,0,0,.4);
display:none;
align-items:center;
justify-content:center;
z-index:6000;
">

<div style="
background:white;
padding:20px;
border-radius:14px;
width:340px;
">

<h3 style="margin-top:0">경로 설정</h3>

<input id="startInput"
placeholder="출발지 입력 (예: 광주전라제주지역본부)"
style="
width:100%;
height:40px;
padding:0 10px;
border:1px solid #cbd5e1;
border-radius:8px;
margin-bottom:10px;
">
<input id="destInput"
placeholder="도착지 입력 (예: 전라남도청)"
style="
width:100%;
height:40px;
padding:0 10px;
border:1px solid #cbd5e1;
border-radius:8px;
margin-bottom:12px;
">

<div id="destSuggestBox" style="
display:none;
width:100%;
height:180px;
overflow-y:auto;
border:1px solid #e5e7eb;
border-radius:10px;
background:#ffffff;
margin-bottom:12px;
box-shadow:0 4px 14px rgba(0,0,0,0.08);
"></div>

<button type="button" class="btn primary" onclick="runRouteSearch()">
경로 조회
</button>

<button class="btn secondary" onclick="closeRoutePopup()">
닫기
</button>

</div>
</div>

<div id="adminPwModal" style="
display:none;
position:fixed;
inset:0;
background:rgba(15,23,42,0.45);
z-index:5000;
align-items:center;
justify-content:center;
padding:20px;
">
  <div style="
  width:100%;
  max-width:360px;
  background:#ffffff;
  border-radius:18px;
  padding:22px;
  box-shadow:0 18px 45px rgba(0,0,0,0.25);
  ">
    <div style="
    font-size:18px;
    font-weight:900;
    margin-bottom:8px;
    color:#111827;
    ">
    관리자 통계
    </div>

    <div style="
    font-size:13px;
    color:#64748b;
    margin-bottom:14px;
    ">
    관리자 암호를 입력하세요.
    </div>

    <input id="adminPwInput" type="password" onkeydown="if(event.key==='Enter'){submitAdminPw();}" style="
    width:100%;
    height:44px;
    border:1px solid #cbd5e1;
    border-radius:12px;
    padding:0 12px;
    font-size:16px;
    outline:none;
    ">

    <div id="adminPwMsg" style="
    min-height:20px;
    margin-top:8px;
    font-size:13px;
    color:#ef4444;
    "></div>

    <div style="
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:10px;
    margin-top:14px;
    ">
      <button onclick="closeAdminPwModal()" style="
      height:42px;
      border:1px solid #cbd5e1;
      border-radius:12px;
      background:#ffffff;
      font-weight:800;
      cursor:pointer;
      ">
      취소
      </button>

      <button onclick="submitAdminPw()" style="
      height:42px;
      border:none;
      border-radius:12px;
      background:#2563eb;
      color:#ffffff;
      font-weight:800;
      cursor:pointer;
      ">
      확인
      </button>
    </div>
  </div>
</div>

</body>
</html>
"""

@app.route("/char_left")
def char_left():
    return send_file("left.png", mimetype="image/png")

@app.route("/char_right")
def char_right():
    return send_file("right.png", mimetype="image/png")

@app.route("/ci")
def ci():
    return send_file("ci.png", mimetype="image/png")

@app.route("/photo/111")
def photo_toilet():
    return send_file("111.png", mimetype="image/png")

@app.route("/photo/222")
def photo_ice():
    return send_file("222.png", mimetype="image/png")

@app.route("/photo/333")
def photo_accident():
    return send_file("333.png", mimetype="image/png")

@app.route("/")
def index():

    visitor = update_visitors()

    return render_template_string(
        HTML,
        total_visit=visitor["total"],
        today_visit=visitor["today_count"]
    )


@app.route("/log_search", methods=["POST"])
def log_search():

    data = request.get_json() or {}

    save_search_log(data)

    return jsonify({"ok": True})


@app.route("/stats")
def stats():

    if not SUPABASE_URL or not SUPABASE_KEY:
        return """
        <h2>조회 통계</h2>
        <p>로컬 실행 중이라 Supabase 통계를 불러오지 않습니다.</p>
        <p><a href="/">돌아가기</a></p>
        """

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/search_logs?select=*&order=created_at.desc&limit=10000",
        headers=headers
    )

    logs = res.json()

    df = pd.DataFrame(logs)

    if df.empty:
        return """
        <h2>조회 통계</h2>
        <p>아직 조회 기록이 없습니다.</p>
        <p><a href="/">돌아가기</a></p>
        """

    df["day"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")

    region_stats = (
        df.groupby(["day", "province", "city", "town"], dropna=False)
        .size()
        .reset_index(name="조회수")
        .sort_values(["day", "조회수"], ascending=[False, False])
    )

    region_stats.columns = ["날짜", "시도", "시군구", "읍면동", "조회수"]

    category_rows = []

    for _, row in df.iterrows():
        categories = row.get("categories", [])

        if not categories:
            category_rows.append({
                "day": row.get("day", ""),
                "category": "전체",
                "search_count": 1
            })
        else:
            for cat in categories:
                category_rows.append({
                    "day": row.get("day", ""),
                    "category": cat,
                    "search_count": 1
                })

    category_df = pd.DataFrame(category_rows)

    category_stats = (
        category_df.groupby(["day", "category"], dropna=False)["search_count"]
        .sum()
        .reset_index()
        .sort_values(["day", "search_count"], ascending=[False, False])
    )

    category_stats.columns = ["날짜", "위험지역 구분", "체크 수"]

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
    <meta charset="UTF-8">
    <title>조회 통계</title>
    <style>
    body{font-family:Malgun Gothic,sans-serif;padding:24px;background:#f8fafc;}
    table{border-collapse:collapse;width:100%;background:white;margin-bottom:30px;}
    th,td{border:1px solid #ddd;padding:8px;font-size:14px;text-align:left;}
    th{background:#e5e7eb;}
    .btn{display:inline-block;padding:10px 14px;background:#2563eb;color:white;text-decoration:none;border-radius:8px;margin-bottom:18px;}
    </style>
    </head>
    <body>
    <h2>조회 통계</h2>
    <a class="btn" href="/">돌아가기</a>

    <h3>날짜별·지역별 조회 수</h3>
    {{ region_table|safe }}

    <h3>날짜별·위험지역 체크 수</h3>
    {{ category_table|safe }}
    </body>
    </html>
    """,
    region_table=region_stats.to_html(index=False),
    category_table=category_stats.to_html(index=False)
    )

@app.route("/meta")
def meta():
    df = load_df()

    provinces = sorted(df["시도"].dropna().astype(str).unique().tolist())
    cities = sorted(df["시군구"].dropna().astype(str).unique().tolist())
    towns = sorted(df["읍면동"].dropna().astype(str).unique().tolist())

    return jsonify({
        "provinces": provinces,
        "cities": cities,
        "towns": towns
    })

@app.route("/cities")
def cities():

    province = safe_str(request.args.get("province",""))

    df = load_df()

    if province:
        df = df[df["시도"] == province]

    cities = sorted(df["시군구"].dropna().astype(str).unique().tolist())

    return jsonify({"cities":cities})


@app.route("/towns")
def towns():

    province = safe_str(request.args.get("province",""))
    city = safe_str(request.args.get("city",""))

    df = load_df()

    if province:
        df = df[df["시도"] == province]

    if city:
        df = df[df["시군구"] == city]

    towns = sorted(df["읍면동"].dropna().astype(str).unique().tolist())

    return jsonify({"towns": towns})



@app.route("/data")
def data():

    province = safe_str(request.args.get("province",""))
    city = safe_str(request.args.get("city",""))
    town = safe_str(request.args.get("town",""))
    categories = request.args.getlist("category")

    df = load_df()

    if province:
        df = df[df["시도"] == province]

    if city:
        df = df[df["시군구"] == city]

    if town:
        df = df[df["읍면동"] == town]

    if categories:
        df = df[df["구분"].isin(categories)]

    total_count = len(df)

    records = df.apply(row_to_dict, axis=1).tolist()

    return jsonify({
        "total": total_count,
        "data": records
    })

@app.route("/sample-image")
def sample_image():
    category = safe_str(request.args.get("category", "위험지역"))
    city = safe_str(request.args.get("city", ""))
    town = safe_str(request.args.get("town", ""))

    color = TYPE_COLORS.get(category, "#334155")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="{color}"/>
        <stop offset="100%" stop-color="#0f172a"/>
      </linearGradient>
    </defs>
    <rect width="800" height="450" fill="url(#g)"/>
    <rect x="30" y="30" width="740" height="390" rx="24" fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.2)"/>
    <text x="50%" y="42%" text-anchor="middle" fill="white" font-size="42" font-family="Arial" font-weight="700">{category}</text>
    <text x="50%" y="54%" text-anchor="middle" fill="white" font-size="24" font-family="Arial">{city} {town}</text>
    <text x="50%" y="70%" text-anchor="middle" fill="white" font-size="18" font-family="Arial">샘플 이미지</text>
    </svg>"""
    return Response(svg, mimetype="image/svg+xml")



def open_preferred_browser(url):
    time.sleep(1.5)

    candidates = [
        r"C:\Program Files\Naver\Naver Whale\Application\whale.exe",
        r"C:\Program Files (x86)\Naver\Naver Whale\Application\whale.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                webbrowser.register("preferred_browser", None, webbrowser.BackgroundBrowser(path))
                webbrowser.get("preferred_browser").open(url)
                return
            except Exception:
                pass

    webbrowser.open(url)


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port, debug=False)