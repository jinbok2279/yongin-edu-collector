import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
API = "https://open.neis.go.kr/hub/"
KEY = os.environ.get("NEIS_KEY", "")
OFFICE = "J10"            # 경기도교육청
AREA = "용인시"            # 주소에 이 글자가 들어간 학교만 (수지구·기흥구·처인구 전체)
DAYS_AHEAD = 60           # 오늘부터 며칠 뒤까지 일정을 모을지
SKIP_EVENTS = {"토요휴업일"}
PUBLIC_HOLIDAYS = {"한글날", "개천절", "추석", "설날", "성탄절", "기독탄신일", "신정",
                   "삼일절", "어린이날", "부처님오신날", "석가탄신일", "현충일", "광복절",
                   "대체공휴일", "선거일"}
RENAMED = {"남사면": "남사읍", "모현면": "모현읍", "이동면": "이동읍"}   # 읍으로 승격된 옛 주소
HIGHLIGHT_WORDS = ["재량휴업", "방학", "개학", "졸업", "입학", "체험", "기념일", "운동회",
                   "한마당", "발표회", "축제", "상담", "공개수업"]


def call(service, **params):
    """나이스 API를 한 번 부르고, 결과 목록(row)만 돌려준다. 데이터가 없으면 빈 목록."""
    params.update({"KEY": KEY, "Type": "json", "pIndex": 1, "pSize": 1000})
    url = API + service + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
    if service not in data:
        code = data.get("RESULT", {}).get("CODE", "")
        if code == "INFO-200":          # 해당하는 데이터가 없습니다
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
        detail = r.get("ORG_RDNDA") or ""
        if AREA in address:
            gu, dong = parse_area(address, detail)
            schools.append({
                "code": r["SD_SCHUL_CODE"],
                "name": r["SCHUL_NM"],
                "address": address,
                "gu": gu,
                "dong": dong,
            })
    return sorted(schools, key=lambda s: (s["gu"], s["name"]))


def parse_area(address, detail):
    """주소에서 구와 읍·면·동을 뽑는다. 예) 처인구 남사읍 / 기흥구 (구갈동)"""
    m = re.search(r"용인시\s+(\S+구)", address)
    gu = m.group(1) if m else "기타"
    rest = address.split(gu, 1)[-1].split()
    for t in rest[:2]:
        if re.fullmatch(r"\S+(읍|면)", t):
            return gu, RENAMED.get(t, t)
    m = re.search(r"\(([^,()]*?[0-9]?동)\s*[,)]", detail + " " + address)
    if m:
        return gu, m.group(1).strip()
    m = re.search(r"([가-힣]+[0-9]*동)(\s|$|,)", detail)
    return gu, (m.group(1) if m else "")


def school_events(code, start, end):
    rows = call("SchoolSchedule", ATPT_OFCDC_SC_CODE=OFFICE, SD_SCHUL_CODE=code,
                AA_FROM_YMD=start, AA_TO_YMD=end)
    events, publics = [], []
    for r in rows:
        name = (r.get("EVENT_NM") or "").strip()
        if not name or name in SKIP_EVENTS:
            continue
        ymd = r.get("AA_YMD", "")
        kind = (r.get("SBTR_DD_SC_NM") or "").strip()
        item = {"date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}", "name": name}
        if kind == "공휴일" or name in PUBLIC_HOLIDAYS:
            publics.append(item)          # 모든 학교 공통 공휴일은 따로 모음
            continue
        item["holiday"] = kind == "휴업일"
        events.append(item)
    return sorted(events, key=lambda e: e["date"]), publics


def main():
    if not KEY:
        raise SystemExit("NEIS_KEY가 없습니다. 저장소 Secrets에 NEIS_KEY를 넣어 주세요.")

    now = datetime.now(KST)
    start = now.strftime("%Y%m%d")
    end = (now + timedelta(days=DAYS_AHEAD)).strftime("%Y%m%d")

    schools = find_schools()
    print(f"{AREA} 초등학교 {len(schools)}곳 발견")

    highlights, public_map = [], {}
    for s in schools:
        try:
            s["events"], publics = school_events(s["code"], start, end)
        except Exception as e:          # 한 학교가 실패해도 나머지는 계속
            print(f"  {s['name']} 일정 가져오기 실패: {e}")
            s["events"], publics = [], []
        for p in publics:
            public_map[(p["date"], p["name"])] = p
        for ev in s["events"]:
            if ev["holiday"] or any(w in ev["name"] for w in HIGHLIGHT_WORDS):
                highlights.append({"school": s["name"], "gu": s["gu"], **ev})
        print(f"  {s['name']}: 학교 일정 {len(s['events'])}건")

    highlights.sort(key=lambda h: (h["date"], h["school"]))
    public_holidays = sorted(public_map.values(), key=lambda p: p["date"])

    result = {
        "region": AREA,
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "period": {"from": start, "to": end},
        "school_count": len(schools),
        "public_holidays": public_holidays,
        "highlights": highlights,
        "schools": schools,
        "source": "나이스 교육정보 개방포털 (학교기본정보, 학사일정)",
    }

    os.makedirs("output", exist_ok=True)
    with open("output/latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    write_summary(result)
    print(f"저장 완료: 주요 일정 {len(highlights)}건, 공휴일 {len(public_holidays)}건")


def write_summary(r):
    """사람이 보기 쉬운 요약 파일 (GitHub에서 표로 보임)"""
    lines = [
        f"# {r['region']} 초등학교 주요 일정",
        "",
        f"- 업데이트: {r['updated_at']} (한국시간)",
        f"- 대상 학교: {r['school_count']}곳 · 기간: 앞으로 {DAYS_AHEAD}일",
        "",
        "## 학교별 주요 일정",
        "",
    ]
    if r["highlights"]:
        lines += ["| 날짜 | 구 | 학교 | 일정 | 휴업 |", "|---|---|---|---|---|"]
        for h in r["highlights"]:
            lines.append(f"| {h['date']} | {h['gu']} | {h['school']} | {h['name']} | {'휴업' if h['holiday'] else ''} |")
    else:
        lines.append("등록된 주요 일정이 없습니다.")
    lines += ["", "## 공휴일 (모든 학교 공통)", ""]
    lines += [f"- {p['date']} {p['name']}" for p in r["public_holidays"]] or ["- 없음"]
    lines += ["", "## 지역별 학교 수", "", "| 구 | 읍·면·동 | 학교 수 | 일정 등록 |", "|---|---|---|---|"]
    areas = {}
    for s in r["schools"]:
        a = areas.setdefault((s["gu"], s["dong"] or "(동 미확인)"), [0, 0])
        a[0] += 1
        a[1] += 1 if s["events"] else 0
    for (gu, dong), (n, e) in sorted(areas.items()):
        lines.append(f"| {gu} | {dong} | {n} | {e} |")
    with open("output/summary.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
