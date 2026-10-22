"""동네 병원 — 의원 / 병원·종합병원 / 응급실 목록을 모은다 (공공데이터포털).

쓰는 서비스 (공공데이터포털 '활용신청', 인증키는 WEATHER_KEY 와 같은 것):
  1) 국립중앙의료원_전국 병·의원 찾기 서비스        → 종류·주소·전화·위치·진료시간·응급실 운영 여부 (기본)
  2) 국립중앙의료원_전국 응급의료기관 정보 조회 서비스 → 응급실 등급·응급실 직통 전화 (있으면 더 정확)
  (심평원 병원정보서비스 함수 hira() 는 나중에 쓸 수 있게 남겨 둠)
진료과는 코드표를 외우지 않고, 코드마다 불러 본 뒤 병원 이름과 맞춰 스스로 정한다(기록에 남김).

개인정보는 모으지 않는다. 병원 이름·종류·진료과·주소·대표 전화·위치·진료시간(공개 정보)만.
출처: 공공누리 제1유형(출처표시) — 앱 화면 아래에 출처를 적는다.
하루에 부르는 횟수가 많지 않게(구 3개 × 종류·과 몇 개) 일주일에 한 번 돌린다.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
CITY = os.environ.get("CITY", "용인").strip()
KEY = os.environ.get("WEATHER_KEY", "").strip()
SIDO, SIDO_CD = "경기도", "310000"          # 심평원 시도 코드 (경기)
GU = ["수지구", "기흥구", "처인구"]
SGGU_ENV = os.environ.get("HOSP_SGGU", "").strip()   # 예: "수지구=310402,기흥구=310403,처인구=310401" (자동으로 못 찾을 때만)

HIRA = "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"
ER_LIST = "https://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytListInfoInqire"
HOURS = "https://apis.data.go.kr/B552657/HsptlAsembySearchService/getHsptlMdcncListInfoInqire"

# 의원 칸에서 고를 수 있는 진료과 (심평원 진료과목 코드)
DEPTS = [("11", "소아청소년과"), ("13", "이비인후과"), ("01", "내과"), ("14", "피부과"), ("12", "안과"),
         ("23", "가정의학과"), ("10", "산부인과"), ("05", "정형외과")]
# 이름으로 과를 한 번 더 확인 (코드가 틀렸을 때 잘못 붙는 것을 막음)
DEPT_HINT = {"소아청소년과": "소아", "이비인후과": "이비인후", "피부과": "피부", "안과": "안과", "산부인과": "산부인|여성", "정형외과": "정형"}
CLINIC_CL = {"31": "의원", "51": "치과의원"}
HOSP_CL = {"01": "상급종합병원", "11": "종합병원", "21": "병원", "41": "치과병원"}


def kq():
    return KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")


def get(url, params, tries=3):
    q = "ServiceKey=" + kq() + "&" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url + "?" + q, headers={"User-Agent": "airang/1.0"}), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(2 + i * 3)
    raise last


def hira(params):
    """심평원 목록을 끝까지 넘겨 가며 받는다."""
    out, page = [], 1
    while True:
        txt = get(HIRA, dict(params, pageNo=page, numOfRows=500, _type="json"))
        if txt.lstrip().startswith("<"):
            raise RuntimeError("심평원 응답이 JSON 이 아님(활용신청 확인): " + re.sub(r"\s+", " ", txt)[:160])
        body = json.loads(txt).get("response", {}).get("body", {}) or {}
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        out += items
        total = int(body.get("totalCount") or 0)
        if page * 500 >= total or not items:
            return out
        page += 1
        time.sleep(0.4)


def xml_items(txt):
    root = ET.fromstring(txt)
    code = root.findtext(".//resultCode")
    if code not in (None, "00", "0000"):
        raise RuntimeError("응답 코드 " + str(code) + " " + str(root.findtext(".//resultMsg")))
    return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]


def nmc(url, params):
    out, page = [], 1
    while True:
        txt = get(url, dict(params, pageNo=page, numOfRows=500))
        if not txt.lstrip().startswith("<"):
            raise RuntimeError("국립중앙의료원 응답이 XML 이 아님: " + txt[:160])
        items = xml_items(txt)
        out += items
        m = re.search(r"<totalCount>(\d+)</totalCount>", txt)
        if not items or not m or page * 500 >= int(m.group(1)):
            return out
        page += 1
        time.sleep(0.4)


def gu_of(addr):
    for g in GU:
        if g in (addr or ""):
            return g
    return ""


def short_addr(addr):
    a = re.sub(r"^\s*경기도\s*", "", addr or "")
    a = re.sub(r"^용인시\s*", "", a)
    a = re.sub(r"\s*\(.*?\)", "", a)   # (동, 건물 이름) 은 뺀다
    return re.sub(r"\s+", " ", a).strip()[:60]


def digits(t):
    return re.sub(r"\D", "", t or "")


def sggu_codes():
    """용인 구 3개의 심평원 시군구 코드. 경기도 종합병원·병원 목록에서 찾아낸다."""
    if SGGU_ENV:
        return dict(x.split("=") for x in SGGU_ENV.split(",") if "=" in x)
    found = {}
    for cl in ("11", "21"):
        for it in hira({"sidoCd": SIDO_CD, "clCd": cl}):
            g = gu_of(it.get("addr", ""))
            if g and "용인" in it.get("addr", "") and it.get("sgguCd"):
                found.setdefault(g, str(it["sgguCd"]))
        if len(found) == len(GU):
            break
    return found


def pt(it):
    try:
        return round(float(it.get("YPos")), 5), round(float(it.get("XPos")), 5)
    except (TypeError, ValueError):
        return None, None


def row(it, kind):
    y, x = pt(it)
    addr = it.get("addr", "")
    r = {"n": it.get("yadmNm", "").strip(), "k": kind, "g": gu_of(addr), "a": short_addr(addr),
         "t": (it.get("telno") or "").strip(), "y": y, "x": x}
    u = (it.get("hospUrl") or "").strip()
    if re.match(r"^https?://", u):
        r["u"] = u
    return r


DIV_CLINIC = {"의원": "의원", "치과의원": "치과의원", "보건소": "보건소", "보건지소": "보건소", "보건진료소": "보건소"}
DIV_HOSP = {"상급종합병원": "상급종합병원", "종합병원": "종합병원", "병원": "병원", "치과병원": "치과병원"}
DEPT_NAME_HINT = dict(DEPT_HINT, 내과="내과", 가정의학과="가정의학", 치과="치과")


def nmc_row(it, kind):
    try:
        y, x = round(float(it.get("wgs84Lat")), 5), round(float(it.get("wgs84Lon")), 5)
    except (TypeError, ValueError):
        y = x = None
    addr = it.get("dutyAddr", "")
    r = {"n": it.get("dutyName", "").strip(), "k": kind, "g": gu_of(addr), "a": short_addr(addr),
         "t": (it.get("dutyTel1") or "").strip(), "y": y, "x": x, "id": it.get("hpid", "")}
    h = [[it.get(f"dutyTime{i}s", ""), it.get(f"dutyTime{i}c", "")] for i in range(1, 9)]  # 월~일, 공휴일
    if any(a for a, _ in h):
        r["h"] = ["".join(p) if p[0] and p[1] else "" for p in h]
    return r


def nmc_depts(items_by_id):
    """진료과 코드(QD)를 하나씩 불러 보고 스스로 과를 정한다 (코드표를 외워 쓰지 않음).
    어떤 과 이름(예: '소아')이 들어간 의원 거의 전부를 담고 있는 코드 = 그 과. 점수 = 담은 비율 × 코드 안 비율."""
    named = {dept: {i for i, r in items_by_id.items() if re.search(hint, r["n"])} for dept, hint in DEPT_NAME_HINT.items()}
    codes = {}
    for n in range(1, 35):
        code = f"D{n:03d}"
        try:
            ids = {it.get("hpid") for it in nmc(HOURS, {"Q0": SIDO, "Q1": CITY + "시", "QD": code})} & set(items_by_id)
        except Exception as e:
            print(f"  {code} 실패:", e)
            continue
        if len(ids) >= 5:
            codes[code] = ids
        time.sleep(0.3)
    for dept, nm in named.items():
        if len(nm) < 5:
            continue
        best = max(((len(ids & nm) / len(nm)) * (len(ids & nm) / len(ids)), len(ids & nm) / len(nm), c) for c, ids in codes.items()) if codes else None
        if not best or best[1] < 0.6:
            print(f"  진료과 {dept}: 맞는 코드 없음 (이름 {len(nm)}곳)")
            continue
        _, recall, code = best
        print(f"  진료과 {dept} = {code} (이름에 과가 있는 {len(nm)}곳 중 {recall:.0%} 포함, 이 코드 {len(codes[code])}곳)")
        for i in codes[code]:
            if dept not in items_by_id[i]["d"]:
                items_by_id[i]["d"].append(dept)


def main():
    if not KEY:
        raise SystemExit("WEATHER_KEY 없음")
    today = datetime.now(KST)
    result = {"city": CITY, "updated": today.strftime("%Y-%m-%d %H:%M"), "depts": [d for _, d in DEPTS] + ["치과"],
              "src": {"nmc": False, "er": False}, "clinics": [], "hospitals": [], "er": []}

    # 1) 국립중앙의료원 병·의원 찾기 — 종류·주소·전화·위치·진료시간·응급실 운영 여부
    nmc_all = []
    try:
        nmc_all = nmc(HOURS, {"Q0": SIDO, "Q1": CITY + "시"})
        print(f"  병·의원 {len(nmc_all)}곳 받음. 종류:", dict(Counter(it.get("dutyDivNam", "") for it in nmc_all).most_common(15)))
        if nmc_all:
            print("  칸:", sorted(nmc_all[0].keys()))
        clinics, hosps = {}, {}
        for it in nmc_all:
            div = (it.get("dutyDivNam") or "").strip()
            if div in DIV_CLINIC:
                r = nmc_row(it, DIV_CLINIC[div])
                r["d"] = ["치과"] if "치과" in div else []
                clinics[r["id"]] = r
            elif div in DIV_HOSP:
                hosps[nmc_row(it, DIV_HOSP[div])["id"]] = nmc_row(it, DIV_HOSP[div])
        nmc_depts(clinics)
        for c in clinics.values():   # 이름에 과가 있으면 그 과를 맨 앞에
            for dept, hint in DEPT_HINT.items():
                if re.search(hint, c["n"]):
                    if dept in c["d"]:
                        c["d"].remove(dept)
                    c["d"].insert(0, dept)
                    break
        order = {"상급종합병원": 0, "종합병원": 1, "병원": 2, "치과병원": 3}
        result["clinics"] = sorted(clinics.values(), key=lambda r: (r["g"], r["n"]))
        result["hospitals"] = sorted(hosps.values(), key=lambda r: (order.get(r["k"], 9), r["g"], r["n"]))
        result["src"]["nmc"] = bool(clinics or hosps)
        print(f"  의원 {len(clinics)}곳, 병원 {len(hosps)}곳")
    except Exception as e:
        print("  병·의원 찾기 실패:", e)

    # 2) 응급실 — 응급의료기관 서비스(응급실 전화 포함)가 되면 그것, 아니면 병·의원 목록의 '응급실 운영' 표시
    rank = {"권역응급의료센터": 0, "지역응급의료센터": 1, "지역응급의료기관": 2}
    try:
        for it in nmc(ER_LIST, {"Q0": SIDO, "Q1": CITY + "시"}):
            r = nmc_row(it, it.get("dutyEmclsName", "") or "응급실")
            r["t"] = it.get("dutyTel3") or r["t"]
            r.pop("h", None)
            result["er"].append(r)
        result["src"]["er"] = "er"
    except Exception as e:
        print("  응급의료기관 서비스 실패 → 병·의원 목록에서 응급실 운영 기관을 씀:", e)
        for it in nmc_all:
            if str(it.get("dutyEryn", "")).strip() == "1":
                r = nmc_row(it, (it.get("dutyEmclsName") or "").strip() or "응급실 운영")
                r["t"] = (it.get("dutyTel3") or "").strip() or r["t"]   # 응급실 직통
                r.pop("h", None)
                result["er"].append(r)
        result["src"]["er"] = "list" if result["er"] else False
    result["er"].sort(key=lambda r: (rank.get(r["k"], 3), r["n"]))
    print(f"  응급실 {len(result['er'])}곳")

    for r in result["clinics"] + result["hospitals"] + result["er"]:
        r.pop("id", None)
    if not result["src"]["nmc"] and not result["src"]["er"]:
        raise SystemExit("병원 정보를 못 받음 — 저장하지 않음 (활용신청 확인)")
    os.makedirs("output", exist_ok=True)
    with open("output/hospitals.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print("  저장:", os.path.getsize("output/hospitals.json") // 1024, "KB")


if __name__ == "__main__":
    main()
