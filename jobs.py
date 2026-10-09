"""엄마 일자리 수집기 (용인)

1) 경기도교육청 구인구직: 용인시 학교·병설유치원의 기간제/사립교원, 초중등 시간강사(방과후 포함), 교육공무직원
2) 경기육아종합지원센터 인력뱅크: 용인시 어린이집 구인 (구인중)
결과는 output/jobs.json 으로 저장한다. 개인 연락처·이메일·담당자 이름은 저장하지 않는다.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from books import Tree

KST = timezone(timedelta(hours=9))
GOE = "https://www.goe.go.kr"
GOE_LIST = GOE + "/recruit/ad/func/pb/hnfpPbancList.do"
GOE_VIEW = GOE + "/recruit/ad/func/pb/hnfpPbancInfoView.do"
CARE = "https://gyeonggi.childcare.go.kr"
CARE_LIST = CARE + "/ccef/job/JobOfferSlPL.jsp"
CARE_VIEW = CARE + "/ccef/job/JobOfferSl.jsp"
KINDS = {"A": "기간제·사립교원", "B": "시간강사·방과후", "C": "교육공무직"}
UA = {"User-Agent": "Mozilla/5.0 (yongin-edu-collector)"}


def http(url, data=None, tries=3):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    headers = dict(UA)
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers)
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40) as res:
                raw = res.read()
            for enc in ("utf-8", "euc-kr"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    pass
            return raw.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  다시 시도 {i + 1}/{tries}: {e}")
            time.sleep(4)
    raise RuntimeError("접속 실패: " + url)


def sp(s):
    return " ".join((s or "").split())


def ymd(s):
    m = re.search(r"(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})", s or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def two_dates(s):
    ds = re.findall(r"\d{4}[./\-]\d{1,2}[./\-]\d{1,2}", s or "")
    return (ymd(ds[0]) if ds else "", ymd(ds[-1]) if ds else "")


def office_phone(p):
    p = sp(p)
    return "" if not p or p.startswith("010") else p


def goe_jobs():
    out, seen = [], set()
    for cd, kind in KINDS.items():
        n = 0
        for page in range(1, 6):
            form = {"mi": "10500", "currPage": page, "srchEcptDl": "Y", "srchLgnNm": "용인시", "srchOcptCd": cd,
                    "pageIndex": 50, "orderbyType": "", "searchType": "", "searchValue": ""}
            try:
                html = http(GOE_LIST, form)
            except Exception as e:
                print("  교육청 목록 실패:", kind, e)
                break
            items = re.findall(r"<li>\s*<a href=\"javascript:goView\('(\d+)'\);?\">(.*?)</a>\s*</li>", html, re.S)
            for sn, body in items:
                if sn in seen:
                    continue
                seen.add(sn)
                txt = lambda h: sp(re.sub(r"<[^>]+>", " ", h))
                top = [txt(x) for x in re.findall(r"<span>(.*?)</span>", re.search(r'cont_top">(.*?)</div>', body, re.S).group(1), re.S)] if 'cont_top' in body else []
                tit = re.search(r'cont_tit">(.*?)</p>', body, re.S)
                title = txt(re.sub(r'<span class="krds-badge[^"]*">.*?</span>', "", tit.group(1), flags=re.S)) if tit else ""
                field = {}
                for k, v in re.findall(r'<em class="btm_tit">(.*?)</em>(.*?)</p>', body, re.S):
                    field[txt(k)] = txt(v)
                org = top[0] if top else ""
                phone = next((office_phone(x) for x in top[1:] if re.match(r"^[\d\-]{8,}$", x)), "")
                reg = next((ymd(x) for x in top if x.startswith("등록일")), "")
                a0, a1 = two_dates(field.get("접수기간"))
                w0, w1 = two_dates(field.get("채용기간"))
                pay = field.get("모집정보", "").split("|")[0].strip()
                out.append({
                    "id": "G" + sn, "kind": kind, "cd": cd, "title": title, "org": org,
                    "kinder": "유치원" in org, "phone": phone, "reg": reg,
                    "applyStart": a0, "applyEnd": a1, "workStart": w0, "workEnd": w1,
                    "count": field.get("채용인원", ""), "field": field.get("직무분야", ""), "pay": pay,
                    "link": GOE_VIEW + "?" + urllib.parse.urlencode({"mi": "10500", "pbancSn": sn}),
                })
                n += 1
            if len(items) < 50:
                break
            time.sleep(0.5)
        print(f"  교육청 {kind}: {n}건")
    return out


def care_jobs():
    out = []
    for page in range(0, 6):
        form = {"flag": "SlPL", "signgu": "41460", "endYn": "N", "offset": page * 50, "limit": 50,
                "schCrType": "", "crspec": "", "crpub": "", "schEmpGbCode": "", "crcert": "", "schCrName": "", "dong": ""}
        try:
            html = http(CARE_LIST, form)
        except Exception as e:
            print("  어린이집 목록 실패:", e)
            break
        t = Tree(); t.feed(html)
        rows = []
        for tr in t.root.find_all("tr"):
            tds = tr.find_all("td")
            a = tr.find("a")
            m = re.search(r"fnGoBoardSl\('(\d+)'", (a.attrs.get("onclick") or "") if a else "")
            if m and len(tds) >= 8:
                rows.append((m.group(1), tds, a))
        for jo, tds, a in rows:
            g = lambda i: sp(tds[i].all_text())
            area = g(5)
            if "용인" not in area:
                continue
            gu = (re.search(r"(처인구|기흥구|수지구)", area) or [None, ""])[1]
            out.append({"id": "C" + jo, "type": g(1), "title": sp(a.attrs.get("title") or g(2)), "org": g(3),
                        "job": g(4), "gu": gu, "applyEnd": ymd(g(6)), "reg": ymd(g(7)),
                        "link": CARE_VIEW + "?" + urllib.parse.urlencode({"flag": "Sl", "JOSEQ": jo})})
        if len(rows) < 50:
            break
        time.sleep(0.5)
    # 상세: 동·자격·임금·연장반 여부 (연락처·이메일·이름은 저장 안 함)
    for j in out[:150]:
        try:
            t = Tree(); t.feed(http(j["link"], tries=2))
            info = {}
            for tr in t.root.find_all("tr"):
                ths, tds = tr.find_all("th"), tr.find_all("td")
                for th, td in zip(ths, tds):
                    info[sp(th.all_text())] = sp(td.all_text())
            loc = info.get("소재지", "")
            m = re.search(r"([가-힣0-9]+(?:동|읍|면))$", loc)
            j["dong"] = m.group(1) if m else ""
            j["qual"] = info.get("자격사항", "")[:60]
            j["pay"] = info.get("임금", "")[:60]
            j["extended"] = info.get("연장보육반 전담교사", "") == "예"
        except Exception as e:
            print("  어린이집 상세 실패:", j["id"], e)
        time.sleep(0.25)
    print(f"  어린이집 구인: {len(out)}건")
    return out


def main():
    today = datetime.now(KST).date().isoformat()
    school, care = [], []
    try:
        school = goe_jobs()
    except Exception as e:
        print("교육청 채용 실패:", e)
    try:
        care = care_jobs()
    except Exception as e:
        print("어린이집 구인 실패:", e)
    old = {}
    if os.path.exists("output/jobs.json"):
        try:
            old = json.load(open("output/jobs.json", encoding="utf-8"))
        except Exception:
            old = {}
    if not school and old.get("school"):
        school = [j for j in old["school"] if (j.get("applyEnd") or "9") >= today]
    if not care and old.get("care"):
        care = [j for j in old["care"] if (j.get("applyEnd") or "9") >= today]
    if not school and not care:
        raise SystemExit("채용 정보를 하나도 가져오지 못했습니다")
    school.sort(key=lambda j: (j.get("applyEnd") or "9", j["org"]))
    care.sort(key=lambda j: (j.get("reg") or ""), reverse=True)
    os.makedirs("output", exist_ok=True)
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
              "source": "경기도교육청 구인구직 · 경기육아종합지원센터 인력뱅크", "school": school, "care": care}
    with open("output/jobs.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print(f"학교·유치원 {len(school)}건, 어린이집 {len(care)}건 저장")
    for j in school[:5]:
        print("  [학교]", j["kind"], j["org"], j["title"], j["applyEnd"])
    for j in care[:5]:
        print("  [어린이집]", j["org"], j["job"], j.get("dong"), j["applyEnd"], j.get("pay"))


if __name__ == "__main__":
    main()
