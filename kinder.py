"""용인시 유치원 정보 수집기 (유치원 알리미 공시정보 Open API)

일반현황 + 통학차량 + 방과후과정을 합쳐 output/kinder.json 으로 저장한다.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
KEY = os.environ.get("KINDER_KEY", "")
BASE = "https://e-childschoolinfo.moe.go.kr/api/notice/"
SIDO = 41
# 용인시 처인구·기흥구·수지구 (행정구역 코드)
SGG = {"처인구": 41461, "기흥구": 41463, "수지구": 41465}


def call(api, sgg):
    params = {"key": KEY, "sidoCode": SIDO, "sggCode": sgg, "pageCnt": 1000, "currentPage": 1}
    url = BASE + api + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (yongin-edu-collector)"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                data = json.loads(res.read().decode("utf-8"))
            if data.get("status") != "SUCCESS":
                raise RuntimeError(f"{data.get('status')} {data.get('message')}")
            return data.get("kinderInfo") or []
        except Exception as e:
            print(f"  {api} {sgg} 다시 시도 {i + 1}/3: {e}")
            time.sleep(4)
    return None


def num(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0


def clean(v):
    s = " ".join(str(v or "").split())
    return "" if s in ("null", "None", "-") else s


def dong_of(addr):
    m = re.search(r"\(([^)]*?[동읍면리])[,)\s]", addr + ")") or re.search(r"\s(\S+[읍면])\s", addr + " ")
    return m.group(1).split(",")[0].strip() if m else ""


def main():
    if not KEY:
        raise SystemExit("KINDER_KEY가 없습니다. 저장소 Secrets에 KINDER_KEY를 넣어 주세요.")
    out = {}
    for gu, code in SGG.items():
        basic = call("basicInfo2.do", code)
        if basic is None:
            raise SystemExit(f"{gu} 일반현황을 가져오지 못했습니다")
        bus = {b.get("kinderCode"): b for b in (call("schoolBus.do", code) or [])}
        after = {a.get("kinderCode"): a for a in (call("afterSchoolPresent.do", code) or [])}
        print(f"{gu}({code}): 유치원 {len(basic)}곳, 통학차량 {len(bus)}, 방과후 {len(after)}")
        for k in basic:
            kc = k.get("kinderCode")
            if not kc:
                continue
            addr = clean(k.get("addr"))
            b, a = bus.get(kc, {}), after.get(kc, {})
            cap = {"3": num(k.get("ag3fpcnt")), "4": num(k.get("ag4fpcnt")), "5": num(k.get("ag5fpcnt")),
                   "mix": num(k.get("mixfpcnt")), "sp": num(k.get("spcnfpcnt"))}
            kids = {"3": num(k.get("ppcnt3")), "4": num(k.get("ppcnt4")), "5": num(k.get("ppcnt5")),
                    "mix": num(k.get("mixppcnt")), "sp": num(k.get("shppcnt"))}
            cls = {"3": num(k.get("clcnt3")), "4": num(k.get("clcnt4")), "5": num(k.get("clcnt5")),
                   "mix": num(k.get("mixclcnt")), "sp": num(k.get("shclcnt"))}
            out[kc] = {
                "id": kc,
                "n": clean(k.get("kindername")),
                "type": clean(k.get("establish")),
                "gu": gu,
                "dong": dong_of(addr),
                "addr": addr,
                "tel": clean(k.get("telno")),
                "hp": clean(k.get("hpaddr")),
                "time": clean(k.get("opertime")),
                "head": clean(k.get("ldgrname")),
                "open": clean(k.get("odate")),
                "cap": num(k.get("prmstfcnt")) or sum(cap.values()),
                "capBy": cap,
                "kids": kids,
                "cls": cls,
                "lat": clean(k.get("lttdcdnt")),
                "lng": clean(k.get("lngtcdnt")),
                "bus": {"yn": clean(b.get("vhcl_oprn_yn")), "cnt": num(b.get("opra_vhcnt"))} if b else None,
                "after": {"cls": num(a.get("inor_clcnt")) + num(a.get("pm_rrgn_clcnt")),
                          "kids": num(a.get("inor_ptcn_kpcnt")) + num(a.get("pm_rrgn_ptcn_kpcnt")),
                          "time": clean(a.get("oper_time"))} if a else None,
                "term": clean(k.get("pbnttmng")),
            }
    if not out:
        raise SystemExit("유치원 정보를 하나도 가져오지 못했습니다 (시군구 코드를 확인하세요)")
    lst = sorted(out.values(), key=lambda x: (x["gu"], x["n"]))
    os.makedirs("output", exist_ok=True)
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
              "source": "유치원 알리미 (교육부·한국교육학술정보원) 공시정보", "count": len(lst), "kinders": lst}
    with open("output/kinder.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    types = {}
    for k in lst:
        types[k["type"]] = types.get(k["type"], 0) + 1
    print(f"유치원 {len(lst)}곳 저장 · 설립유형 {types}")
    for k in lst[:3]:
        print("  예:", k["n"], k["type"], k["gu"], k["dong"], "정원", k["cap"], "현원", sum(k["kids"].values()), "차량", k["bus"])


if __name__ == "__main__":
    main()
