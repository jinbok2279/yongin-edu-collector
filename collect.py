import json
import os
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def collect():
    now = datetime.now(KST)
    items = [
        {
            "source": "테스트",
            "title": "수집기 동작 확인용 샘플 공고",
            "target": "초등 전학년",
            "deadline": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
            "summary": "예약 실행이 정상이면 updated_at 시각이 계속 바뀝니다.",
            "link": "",
        }
    ]
    return {
        "region": "용인시 기흥구",
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "items": items,
    }


data = collect()
os.makedirs("output", exist_ok=True)
with open("output/latest.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("수집 완료:", data["updated_at"])
