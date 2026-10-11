"""용인 초·중·고 급식 식단 수집기 (나이스 급식식단정보)

output/latest.json 의 학교 목록을 읽어, 학교마다 오늘부터 일주일치 식단을 받아
output/meals.json 으로 저장한다. 메뉴 이름 뒤의 알레르기 번호는 따로 떼어 둔다.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
API = "https://open.neis.go.kr/hub/mealServiceDietInfo"
KEY = os.environ.get("NEIS_KEY", "")
OFFICE = "J10"
DAYS = 7


def fetch(code, start, end):
    params = {"KEY": KEY, "Type": "json", "pIndex": 1, "pSize": 100, "ATPT_OFCDC_SC_CODE": OFFICE,
              "SD_SCHUL_CODE": code, "MLSV_FROM_YMD": start, "MLSV_TO_YMD": end}
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
            if "mealServiceDietInfo" not in data:
                if data.get("RESULT", {}).get("CODE") == "INFO-200":
                    return []
                raise RuntimeError(str(data.get("RESULT")))
            for part in data["mealServiceDietInfo"]:
                if "row" in part:
                    return part["row"]
            return []
        except Exception as e:
            print(f"  {code} 다시 시도 {i + 1}/3: {e}")
            time.sleep(3)
    return None


def dishes(raw):
    """'기장밥 <br/>맑은대구탕 (5.6)<br/>...' → [['기장밥', ''], ['맑은대구탕', '5.6'], ...]"""
    out = []
    for part in re.split(r"<br\s*/?>", raw or ""):
        part = " ".join(part.split())
        if not part:
            continue
        m = re.search(r"\(?\s*([\d.]+)\s*\)?\s*$", part)
        allergy = ""
        if m and re.fullmatch(r"\d+(\.\d+)*\.?", m.group(1)):
            allergy = m.group(1).strip(".")
            part = part[:m.start()].strip()
        part = re.sub(r"[*#@]+$", "", part).strip()
        if part:
            out.append([part, allergy])
    return out


def main():
    if not KEY:
        raise SystemExit("NEIS_KEY가 없습니다.")
    schools = json.load(open("output/latest.json", encoding="utf-8"))["schools"]
    now = datetime.now(KST)
    start, end = now.strftime("%Y%m%d"), (now + timedelta(days=DAYS)).strftime("%Y%m%d")
    result, ok, fail = {}, 0, 0
    for s in schools:
        rows = fetch(s["code"], start, end)
        if rows is None:
            fail += 1
            continue
        meals = []
        for r in rows:
            ymd = r.get("MLSV_YMD", "")
            meals.append([f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}", r.get("MMEAL_SC_NM") or "", dishes(r.get("DDISH_NM")),
                          (r.get("CAL_INFO") or "").replace(" Kcal", "").strip()])
        meals.sort(key=lambda m: (m[0], {"조식": 0, "중식": 1, "석식": 2}.get(m[1], 9)))
        if meals:
            result[s["code"]] = meals
        ok += 1
        time.sleep(0.15)
    if ok == 0:
        raise SystemExit("급식 정보를 하나도 받지 못했습니다")
    os.makedirs("output", exist_ok=True)
    out = {"updated_at": now.strftime("%Y-%m-%d %H:%M:%S"), "from": start, "to": end,
           "source": "나이스 교육정보 개방포털 급식식단정보", "schools": result}
    with open("output/meals.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"학교 {len(schools)}곳 중 {ok}곳 확인 (실패 {fail}), 식단 있는 학교 {len(result)}곳")


if __name__ == "__main__":
    main()
