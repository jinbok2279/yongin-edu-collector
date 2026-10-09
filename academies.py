"""용인시 학원·교습소 목록 수집기 (NEIS 학원교습소정보)

교육청에 등록된 용인시 학원·교습소 중 '개원' 상태인 곳만 모아
output/academies.json 으로 저장한다. 앱에서 아이의 학원을 고를 때 쓴다.
"""

import json
import os
import re
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


def area(addr, detail):
    gm = re.search(r"용인시\s*(\S+구)", addr)
    gu = gm.group(1) if gm else ""
    m = re.search(r"\(([^)]*?[동읍면])(?:[,)\s]|$)", detail + ")") or re.search(r"\(([^)]*?[동읍면])(?:[,)\s]|$)", addr + ")")
    if m:
        dong = m.group(1).split(",")[0].strip()
    else:
        m = re.search(r"\s(\S+[읍면])\s", addr + " ")
        dong = m.group(1) if m else ""
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
    lst = sorted(acas.values(), key=lambda a: a["n"])
    os.makedirs("output", exist_ok=True)
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
              "source": "NEIS 교육정보 개방 포털 (학원교습소정보)", "count": len(lst), "academies": lst}
    with open("output/academies.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    by_gu = {}
    for a in lst:
        by_gu[a["gu"] or "구 미상"] = by_gu.get(a["gu"] or "구 미상", 0) + 1
    print(f"개원 학원·교습소 {len(lst)}곳 저장:", by_gu)
    print("수강료 공개:", sum(1 for a in lst if a["f"]), "곳")


if __name__ == "__main__":
    main()
