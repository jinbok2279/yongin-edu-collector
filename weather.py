"""오늘 아침 체크용 날씨·미세먼지 수집기

1) 기상청_단기예보 조회서비스 (최저·최고 기온, 하늘, 비 올 확률)
2) 한국환경공단_에어코리아_대기오염정보 (오늘 미세먼지·초미세먼지 예보, 안 되면 실시간 측정값)
공공데이터포털 인증키 하나로 둘 다 쓴다 (GitHub Secret: WEATHER_KEY).
결과는 output/weather.json 으로 저장한다. 실패하면 이전 파일을 그대로 둔다.
"""

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
KEY = os.environ.get("WEATHER_KEY", "").strip()
CITY = os.environ.get("CITY", "용인").strip()

# 시청 위치 (위도, 경도), 에어코리아 측정소 이름 후보, 예보 권역
PLACES = {
    "용인": {"lat": 37.2411, "lon": 127.1776, "stations": ["김량장동", "삼가동", "기흥", "수지", "구성동", "신갈동", "모현읍", "백암면", "고림동", "상현동", "동천동"], "region": "경기남부"},
    "수원": {"lat": 37.2636, "lon": 127.0286, "stations": ["인계동", "광교동", "신풍동", "고색동", "천천동", "영통동", "호매실동", "우만동"], "region": "경기남부"},
}
FCST = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
AIR_FC = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMinuDustFrcstDspth"
AIR_NOW = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"


def key_param():
    # 공공데이터포털 '인코딩 키'(%가 들어 있음)도, '디코딩 키'도 받아 준다
    return KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")


def get_json(url, params, tries=3):
    full = url + "?serviceKey=" + key_param() + "&" + urllib.parse.urlencode(params)
    last = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0 (edu-collector weather)"})
            with urllib.request.urlopen(req, timeout=30) as res:
                raw = res.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except ValueError:
                last = raw[:200].replace(KEY, "***")
        except Exception as e:
            last = str(e).replace(KEY, "***")
        time.sleep(3 * (i + 1))
    print("  응답 오류:", last)
    return None


def items(js):
    try:
        head = js["response"]["header"]
        if str(head.get("resultCode")) not in ("00", "0"):
            print("  결과 코드:", head.get("resultCode"), head.get("resultMsg"))
            return []
        it = js["response"]["body"]["items"]
        if isinstance(it, dict):
            it = it.get("item", [])
        return it or []
    except Exception:
        return []


def to_grid(lat, lon):
    """기상청 격자(nx, ny) 변환 (기상청 공식 람베르트 투영 공식)"""
    RE, GRID, SLAT1, SLAT2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    D = math.pi / 180.0
    re = RE / GRID
    s1, s2, olon, olat = SLAT1 * D, SLAT2 * D, OLON * D, OLAT * D
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(math.tan(math.pi * 0.25 + s2 * 0.5) / math.tan(math.pi * 0.25 + s1 * 0.5))
    sf = math.tan(math.pi * 0.25 + s1 * 0.5) ** sn * math.cos(s1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn
    ra = re * sf / math.tan(math.pi * 0.25 + lat * D * 0.5) ** sn
    th = lon * D - olon
    th = (th + 2 * math.pi) % (2 * math.pi)
    if th > math.pi:
        th -= 2 * math.pi
    th *= sn
    return int(ra * math.sin(th) + XO + 0.5), int(ro - ra * math.cos(th) + YO + 0.5)


def latest_base(now):
    """발표 시각(02,05,08,...,23시) 중 지금 받을 수 있는 가장 최근 것 (발표 후 15분 여유)"""
    t = now - timedelta(minutes=15)
    for h in (23, 20, 17, 14, 11, 8, 5, 2):
        if t.hour >= h:
            return t.strftime("%Y%m%d"), f"{h:02d}00"
    y = t - timedelta(days=1)
    return y.strftime("%Y%m%d"), "2300"


def forecast(nx, ny, base_date, base_time):
    js = get_json(FCST, {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON", "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny})
    return items(js) if js else []


SKY = {"1": ("맑음", "☀️"), "3": ("구름 많음", "⛅"), "4": ("흐림", "☁️")}
PTY = {"1": ("비", "🌧️"), "2": ("비 또는 눈", "🌨️"), "3": ("눈", "❄️"), "4": ("소나기", "🌦️")}


def summarize(today, rows_latest, rows_early):
    """오늘 낮(7~19시) 기준 하늘·비 확률, 최저·최고 기온"""
    by = {}
    for r in rows_latest + rows_early:
        if r.get("fcstDate") != today:
            continue
        by.setdefault(r["category"], {})
        by[r["category"]].setdefault(r["fcstTime"], r["fcstValue"])  # 최신 발표를 먼저 넣었으므로 최신 값이 우선
    day = lambda cat: [(t, v) for t, v in sorted(by.get(cat, {}).items()) if "0700" <= t <= "1900"]
    num = lambda v: float(str(v).replace("℃", "").strip())

    tmp = [num(v) for _, v in sorted(by.get("TMP", {}).items())]
    first = lambda cat: num(next(iter(by[cat].values()))) if by.get(cat) else None
    lo, hi = first("TMN"), first("TMX")
    if lo is None and tmp:
        lo = min(tmp)
    if hi is None and tmp:
        hi = max(tmp)
    if lo is None or hi is None:
        return None

    pops = [int(num(v)) for _, v in day("POP")]
    pty = [v for _, v in day("PTY") if str(v) != "0"]
    sky = [v for _, v in day("SKY")]
    if pty:
        code = max(set(pty), key=pty.count)
        label, icon = PTY.get(str(code), ("비", "🌧️"))
    else:
        code = max(set(sky), key=sky.count) if sky else "1"
        label, icon = SKY.get(str(code), ("맑음", "☀️"))
    return {"sky": label, "icon": icon, "lo": round(lo), "hi": round(hi), "pop": max(pops) if pops else 0}


def grade_pm10(v):
    return "좋음" if v <= 30 else "보통" if v <= 80 else "나쁨" if v <= 150 else "매우 나쁨"


def grade_pm25(v):
    return "좋음" if v <= 15 else "보통" if v <= 35 else "나쁨" if v <= 75 else "매우 나쁨"


def air_forecast(today, region):
    """오늘 미세먼지 예보 (권역별 등급). 'PM10' / 'PM25' 각각"""
    out = {}
    for code, k in (("PM10", "pm10"), ("PM25", "pm25")):
        js = get_json(AIR_FC, {"returnType": "json", "numOfRows": 100, "pageNo": 1, "searchDate": today, "InformCode": code})
        for it in items(js) if js else []:
            if it.get("informData") != today:
                continue
            for part in str(it.get("informGrade", "")).split(","):
                if ":" in part:
                    name, g = [x.strip() for x in part.split(":", 1)]
                    if name == region and g:
                        out[k] = g.replace("매우나쁨", "매우 나쁨")
            if k in out:
                break
    return out


def air_now(stations):
    """실시간 측정값 평균으로 등급 (예보가 없을 때)"""
    js = get_json(AIR_NOW, {"returnType": "json", "numOfRows": 200, "pageNo": 1, "sidoName": "경기", "ver": "1.3"})
    p10, p25 = [], []
    for it in items(js) if js else []:
        if it.get("stationName") not in stations:
            continue
        for arr, f in ((p10, "pm10Value"), (p25, "pm25Value")):
            try:
                arr.append(float(it.get(f)))
            except (TypeError, ValueError):
                pass
    out = {}
    if p10:
        out["pm10"] = grade_pm10(sum(p10) / len(p10))
    if p25:
        out["pm25"] = grade_pm25(sum(p25) / len(p25))
    return out


def main():
    if not KEY:
        print("WEATHER_KEY 없음: 날씨 수집 건너뜀 (GitHub Secrets에 공공데이터포털 인증키를 WEATHER_KEY로 넣어 주세요)")
        return 0
    place = PLACES.get(CITY)
    if not place:
        print("모르는 도시:", CITY)
        return 1
    now = datetime.now(KST)
    today = now.strftime("%Y%m%d")
    nx, ny = to_grid(place["lat"], place["lon"])
    print(f"{CITY} 격자 nx={nx} ny={ny}")

    bd, bt = latest_base(now)
    latest = forecast(nx, ny, bd, bt)
    print(f"  단기예보 {bd} {bt}: {len(latest)}건")
    early = []
    if not (bd == today and bt == "0200") and now.hour >= 2:
        early = forecast(nx, ny, today, "0200")  # 오늘 최저·최고 기온이 들어 있는 새벽 발표
        print(f"  단기예보 {today} 0200: {len(early)}건")
    w = summarize(today, latest, early)
    if not w:
        print("날씨를 만들지 못했어요. 이전 파일을 그대로 둡니다.")
        return 0

    ymd = now.strftime("%Y-%m-%d")
    air = air_forecast(ymd, place["region"])
    if not air.get("pm10"):
        air = {**air_now(place["stations"]), **air}
    print("  날씨:", w, "미세먼지:", air)

    out = {"city": CITY, "date": ymd, "updated": now.strftime("%Y-%m-%d %H:%M"), "now": w}
    if air.get("pm10") or air.get("pm25"):
        out["air"] = {"pm10": air.get("pm10", air.get("pm25")), "pm25": air.get("pm25", "")}
    os.makedirs("output", exist_ok=True)
    with open("output/weather.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("저장: output/weather.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
