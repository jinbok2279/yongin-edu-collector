import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
API = "https://open.neis.go.kr/hub/"
KEY = os.environ.get("NEIS_KEY", "")
OFFICE = "J10"            # 경기도교육청
AREA = "용인시 기흥구"      # 주소에 이 글자가 들어간 학교만
DAYS_AHEAD = 60           # 오늘부터 며칠 뒤까지 일정을 모을지
SKIP_EVENTS = {"토요휴업일"}
HIGHLIGHT_WORDS = ["재량휴업", "방학", "개학", "졸업", "입학", "체험학습", "운동회", "축제", "상담"]


def call(service, **params):
    params.update({"KEY": KEY, "Type": "json", "pIndex": 1, "pSize": 1000})
    url = API + service + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
    if service not in data:
        code = data.get("RESULT", {}).get("CODE", "")
        if code == "INFO-200":
            return []
        raise RuntimeError(f"{service} 오류: {data.get('RESULT')}")
    for part in data[service]:
        if "row" in part:
            return part["row"]
    return []


def find_schools():
    rows = call("schoolInfo", ATPT_OFCDC_SC_CODE=OFFICE, SCHUL_KND_SC_NM="초등학교")
    schools = []
    for r in rows:
        address = r.get("ORG_RDNMA") or ""
        if AREA in address:
            schools.append({
                "code": r["SD_SCHUL_CODE"],
                "name": r["SCHUL_NM"],
                "address": address,
            })
    return sorted(schools, key=lambda s: s["name"])


def school_events(code, start, end):
    rows = call("SchoolSchedule", ATPT_OFCDC_SC_CODE=OFFICE, SD_SCHUL_CODE=code,
                AA_FROM_YMD=start, AA_TO_YMD=end)
    events = []
    for r in rows:
        name = (r.get("EVENT_NM") or "").strip()
        if not name or name in SKIP_EVENTS:
            continue
        ymd = r.get("AA_YMD", "")
        events.append({
            "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
            "name": name,
            "holiday": (r.get("SBTR_DD_SC_NM") or "") == "휴업일",
        })
    return sorted(events, key=lambda e: e["date"])


def main():
    if not KEY:
        raise SystemExit("NEIS_KEY가 없습니다. 저장소 Secrets에 NEIS_KEY를 넣어 주세요.")

    now = datetime.now(KST)
    start = now.strftime("%Y%m%d")
    end = (now + timedelta(days=DAYS_AHEAD)).strftime("%Y%m%d")

    schools = find_schools()
    print(f"{AREA} 초등학교 {len(schools)}곳 발견")

    highlights = []
    for s in schools:
        try:
            s["events"] = school_events(s["code"], start, end)
        except Exception as e:
            print(f"  {s['name']} 일정 가져오기 실패: {e}")
            s["events"] = []
        for ev in s["events"]:
            if ev["holiday"] or any(w in ev["name"] for w in HIGHLIGHT_WORDS):
                highlights.append({"school": s["name"], **ev})
        print(f"  {s['name']}: 일정 {len(s['events'])}건")

    highlights.sort(key=lambda h: (h["date"], h["school"]))

    result = {
        "region": AREA,
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "period": {"from": start, "to": end},
        "school_count": len(schools),
        "highlights": highlights,
        "schools": schools,
        "source": "나이스 교육정보 개방포털 (학교기본정보, 학사일정)",
    }

    os.makedirs("output", exist_ok=True)
    with open("output/latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: 주요 일정 {len(highlights)}건")


if __name__ == "__main__":
    main()
