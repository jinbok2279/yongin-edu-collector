"""전국 특목고·자사고 목록 수집기 (나이스 학교기본정보)

고등학교 구분(HS_SC_NM)과 특수목적고 계열(SPCLY_PURPS_HS_ORD_NM)로
자사고(전국단위/광역단위), 외국어고, 국제고, 과학고, 영재학교를 골라 output/elite.json 으로 저장한다.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
API = "https://open.neis.go.kr/hub/schoolInfo"
KEY = os.environ.get("NEIS_KEY", "")
OFFICES = {"B10": "서울", "C10": "부산", "D10": "대구", "E10": "인천", "F10": "광주", "G10": "대전",
           "H10": "울산", "I10": "세종", "J10": "경기", "K10": "강원", "M10": "충북", "N10": "충남",
           "P10": "전북", "Q10": "전남", "R10": "경북", "S10": "경남", "T10": "제주"}
# 전국단위 자사고 10곳 (2026학년도 기준)
NATIONAL = ["용인한국외국어대학교부설고등학교", "상산고등학교", "민족사관고등학교", "하나고등학교", "북일고등학교",
            "포항제철고등학교", "광양제철고등학교", "김천고등학교", "인천하늘고등학교", "현대청운고등학교"]
# 영재학교 8곳
GIFTED = ["서울과학고등학교", "경기과학고등학교", "대구과학고등학교", "대전과학고등학교", "광주과학고등학교",
          "한국과학영재학교", "세종과학예술영재학교", "인천과학예술영재학교"]
SHORT = {"용인한국외국어대학교부설고등학교": "외대부고"}


def page(office, idx):
    params = {"KEY": KEY, "Type": "json", "pIndex": idx, "pSize": 1000, "ATPT_OFCDC_SC_CODE": office}
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(3):
        try:
            with urllib.request.urlopen(url, timeout=40) as res:
                data = json.loads(res.read().decode("utf-8"))
            if "schoolInfo" not in data:
                code = data.get("RESULT", {}).get("CODE", "")
                if code == "INFO-200":
                    return [], 0
                raise RuntimeError(str(data.get("RESULT")))
            total, rows = 0, []
            for part in data["schoolInfo"]:
                if "head" in part:
                    total = part["head"][0].get("list_total_count", 0)
                if "row" in part:
                    rows = part["row"]
            return rows, total
        except Exception as e:
            print(f"  {office} {idx}쪽 다시 시도 {i + 1}/3: {e}")
            time.sleep(4)
    raise RuntimeError(f"{office} 접속 실패")


def kind_of(r):
    name = r.get("SCHUL_NM") or ""
    hs = r.get("HS_SC_NM") or ""
    line = r.get("SPCLY_PURPS_HS_ORD_NM") or ""
    fond = r.get("FOND_SC_NM") or ""
    if name in GIFTED:
        return "영재학교"
    if name in NATIONAL:
        return "자사고(전국)"
    if hs == "자율고" and fond == "사립":
        return "자사고(광역)"
    if hs == "특목고":
        if "외국어" in line:
            return "외고"
        if "국제" in line:
            return "국제고"
        if "과학" in line:
            return "과학고"
    return ""


def main():
    if not KEY:
        raise SystemExit("NEIS_KEY가 없습니다.")
    out, seen_kinds = [], {}
    for office, sido in OFFICES.items():
        idx, got = 1, 0
        while True:
            rows, total = page(office, idx)
            for r in rows:
                k = kind_of(r)
                if r.get("HS_SC_NM"):
                    seen_kinds[(r.get("HS_SC_NM"), r.get("SPCLY_PURPS_HS_ORD_NM") or "")] = seen_kinds.get((r.get("HS_SC_NM"), r.get("SPCLY_PURPS_HS_ORD_NM") or ""), 0) + 1
                if not k:
                    continue
                name = r.get("SCHUL_NM") or ""
                out.append({
                    "code": r.get("SD_SCHUL_CODE"), "office": office, "n": name,
                    "short": SHORT.get(name, name.replace("고등학교", "고").replace("학교", "")),
                    "kind": k, "sido": sido, "sigungu": (r.get("LCTN_SC_NM") or ""),
                    "addr": " ".join(((r.get("ORG_RDNMA") or "") + " " + (r.get("ORG_RDNDA") or "")).split()),
                    "fond": r.get("FOND_SC_NM") or "", "coedu": r.get("COEDU_SC_NM") or "",
                    "hp": (r.get("HMPG_ADRES") or "").strip(), "tel": r.get("ORG_TELNO") or "",
                    "term": r.get("ENE_BFE_SEHF_SC_NM") or "",
                })
            got += len(rows)
            if not rows or got >= total:
                break
            idx += 1
            time.sleep(0.3)
        print(f"{sido}: 학교 {got}곳 확인")
        time.sleep(0.3)
    names = {s["n"] for s in out}
    for g in GIFTED + NATIONAL:
        if g not in names:
            print("  나이스 목록에 없음(이름 확인 필요):", g)
    if len(out) < 50:
        print("고등학교 구분 값 예시:", sorted(seen_kinds.items(), key=lambda x: -x[1])[:15])
        raise SystemExit(f"특목·자사고가 {len(out)}곳뿐이라 저장하지 않습니다")
    order = ["영재학교", "과학고", "자사고(전국)", "외고", "국제고", "자사고(광역)"]
    out.sort(key=lambda s: (order.index(s["kind"]), s["sido"] != "경기", s["sido"], s["n"]))
    counts = {k: sum(1 for s in out if s["kind"] == k) for k in order}
    os.makedirs("output", exist_ok=True)
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
              "source": "나이스 교육정보 개방포털 학교기본정보", "counts": counts, "schools": out}
    with open("output/elite.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print("저장:", counts)
    print("고등학교 구분 값:", sorted(seen_kinds.items(), key=lambda x: -x[1])[:20])


if __name__ == "__main__":
    main()
