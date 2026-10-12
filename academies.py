"""용인시 학원·교습소 목록 수집기 (NEIS 학원교습소정보)

교육청에 등록된 용인시 학원·교습소 중 '개원' 상태인 곳만 모아
output/academies.json 으로 저장한다. 앱에서 아이의 학원을 고를 때 쓴다.
"""

import json
import os
import re
from collections import Counter, defaultdict
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
KEY = os.environ.get("NEIS_KEY", "")
URL = "https://open.neis.go.kr/hub/acaInsTiInfo"


def fetch_page(page):
    params = {"KEY": KEY, "Type": "json", "pIndex": page, "pSize": 1000,
              "ATPT_OFCDC_SC_CODE": "J10", "ADMST_ZONE_NM": "용인시"}
    url = URL + "?" + urllib.parse.urlencode(params)
    for i in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as res:
                data = json.loads(res.read().decode("utf-8"))
            if "acaInsTiInfo" not in data:
                code = data.get("RESULT", {}).get("CODE", "")
                if code == "INFO-200":
                    return 0, []
                raise RuntimeError(data)
            head, body = data["acaInsTiInfo"]
            return head["head"][0]["list_total_count"], body["row"]
        except Exception as e:
            print(f"  {page}쪽 다시 시도 {i + 1}/3: {e}")
            time.sleep(5)
    raise RuntimeError(f"{page}쪽을 가져오지 못했습니다")


def clean(s):
    s = (s or "").strip()
    return "" if s in ("null", "None") else " ".join(s.split())


DONG = re.compile(r"^([가-힣]{1,8}?\d{0,2}(?:동|가|읍|면))(?:\d[\d\-]*)?$")
NOT_DONG = re.compile(r"상가|빌딩|타워|프라자|플라자|센터|아파트|오피스텔|빌라|하우스|힐스|자이|래미안|푸르지오|아이파크|캐슬|단지|블럭|블록|마을")
NOT_DONG_EXACT = {"가동", "나동", "다동", "라동", "마동", "바동", "사동", "아동", "자동", "에이동", "비동", "씨동", "디동", "본동", "별동", "신관동", "구관동", "전면", "후면", "측면", "정면", "일부동", "전동", "상가동"}


def area(addr, detail):
    """주소에서 구·행정 동(읍·면) 이름만 뽑기 — 아파트·상가 '101동', '203호', 건물 이름은 버림"""
    gm = re.search(r"용인시\s*(\S+구)", addr)
    gu = gm.group(1) if gm else ""
    m = re.search(r"용인시\s*(?:\S+구\s+)?([가-힣]+[읍면])\s", addr + " ")   # 읍·면 지역은 읍·면 이름 우선
    dong = m.group(1) if m else ""
    if not dong:   # 도로명 주소 끝 괄호: (망포동, 건물이름) / (이의동1369-2, …)
        for grp in re.findall(r"\(([^()]*)", detail + " " + addr):
            for tok in re.split(r"[,\s]+", grp.replace("지번:", " ")):
                t = DONG.match(re.sub(r"^\d+(?=[가-힣])", "", tok.strip()))   # (0당수동 …) 처럼 앞에 숫자가 잘못 붙은 경우
                if t and t.group(1) not in NOT_DONG_EXACT and not NOT_DONG.search(t.group(1)):
                    dong = t.group(1)
                    break
            if dong:
                break
    if dong in ("남사면", "이동면", "모현면", "양지면"):   # 읍으로 바뀐 곳은 지금 이름으로
        dong = dong[:-1] + "읍"
    if not gu and dong.endswith(("읍", "면")):
        gu = "처인구"
    return gu, dong


def fees(text):
    """'영어 (중등):230000, 영어 (고등):300000' -> [["영어 (중등)", 230000], ...]"""
    out = []
    for part in re.split(r",\s*(?=[^,:]+:\s*\d)", clean(text)):
        name, _, amount = part.rpartition(":")
        amount = re.sub(r"\D", "", amount)
        if name.strip() and amount:
            out.append([name.strip(), int(amount)])
    return out


def fill_dong(lst, city):
    """동을 못 찾은 곳 채우기: ① 괄호 안에 이미 아는 동 이름이 붙어 있으면 그것 ② 같은 길에 있는 다른 학원 대부분이 같은 동이면 그 동"""
    known = defaultdict(set)
    for a in lst:
        if a["dong"]:
            known[a["gu"]].add(a["dong"])
    for a in lst:
        if a["dong"]:
            continue
        m = re.search(city + r"시\s*\S+구\s+([가-힣]+\d{0,2}(?:동|가))\s+\d", a["a"])   # 지번 주소: … 기흥구 중동 874
        if m and m.group(1) in known[a["gu"]]:
            a["dong"] = m.group(1)
            continue
        text = "," + ",".join(re.findall(r"\(([^()]*)", a["a"])).replace(" ", "")
        for d in sorted(known[a["gu"]], key=len, reverse=True):
            after = r"" if len(d) >= 3 else r"(?![가-힣])"   # 두 글자 동(신동·하동)은 '신동아'처럼 붙은 이름과 헷갈리지 않게
            if re.search(r"[,(]" + re.escape(d) + after, text):
                a["dong"] = d
                break

    def road(addr):
        m = re.search(city + r"시\s*\S+구\s+(\S+?(?:로|길))\s*\d", addr) or re.search(city + r"시\s+(\S+?(?:로|길))\s*\d", addr)
        return m.group(1) if m else ""

    by_road = defaultdict(Counter)
    for a in lst:
        if a["dong"]:
            r = road(a["a"])
            if r:
                by_road[(a["gu"], r)][a["dong"]] += 1
                base = re.sub(r"\d+번?길$", "", r)
                if base != r:
                    by_road[(a["gu"], base + "*")][a["dong"]] += 1
    for a in lst:
        if a["dong"]:
            continue
        r = road(a["a"])
        if not r:
            continue
        for key in ((a["gu"], r), (a["gu"], re.sub(r"\d+번?길$", "", r) + "*")):
            c = by_road.get(key)
            if c:
                d, n = c.most_common(1)[0]
                if n >= 2 and n / sum(c.values()) >= 0.8:
                    a["dong"] = d
                    break
    return lst


def main():
    if not KEY:
        raise SystemExit("NEIS_KEY가 없습니다. 저장소 Secrets에 NEIS_KEY를 넣어 주세요.")
    rows, page = [], 1
    while True:
        total, got = fetch_page(page)
        rows += got
        print(f"{page}쪽: {len(got)}건 (전체 {total})")
        if not got or len(rows) >= total:
            break
        page += 1
    acas = {}
    for r in rows:
        if clean(r.get("REG_STTUS_NM")) != "개원":
            continue
        aid = clean(r.get("ACA_ASNUM"))
        if not aid:
            continue
        course = clean(r.get("LE_CRSE_LIST_NM")) or clean(r.get("LE_CRSE_NM"))
        if aid in acas:  # 같은 학원이 과정별로 여러 줄일 때 합치기
            a = acas[aid]
            if course and course not in a["c"]:
                a["c"].append(course)
            for f in fees(r.get("PSNBY_THCC_CNTNT") if clean(r.get("THCC_OTHBC_YN")) == "Y" else ""):
                if f not in a["f"]:
                    a["f"].append(f)
            continue
        addr, detail = clean(r.get("FA_RDNMA")), clean(r.get("FA_RDNDA"))
        gu, dong = area(addr, detail)
        acas[aid] = {
            "id": aid,
            "n": clean(r.get("ACA_NM")),
            "t": clean(r.get("ACA_INSTI_SC_NM")),
            "r": clean(r.get("REALM_SC_NM")),
            "c": [course] if course else [],
            "f": fees(r.get("PSNBY_THCC_CNTNT")) if clean(r.get("THCC_OTHBC_YN")) == "Y" else [],
            "gu": gu,
            "dong": dong,
            "a": (addr + " " + detail.lstrip(", ")).strip(),
            "cap": r.get("TOFOR_SMTOT") or 0,
            "tel": clean(r.get("FA_TELNO")),
        }
    lst = fill_dong(sorted(acas.values(), key=lambda a: a["n"]), "용인")
    os.makedirs("output", exist_ok=True)
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
              "source": "NEIS 교육정보 개방 포털 (학원교습소정보)", "count": len(lst), "academies": lst}
    with open("output/academies.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    by_gu = {}
    for a in lst:
        by_gu[a["gu"] or "구 미상"] = by_gu.get(a["gu"] or "구 미상", 0) + 1
    print(f"개원 학원·교습소 {len(lst)}곳 저장:", by_gu)
    print("동 모름:", sum(1 for a in lst if not a["dong"]), "곳")
    print("수강료 공개:", sum(1 for a in lst if a["f"]), "곳")


if __name__ == "__main__":
    main()
