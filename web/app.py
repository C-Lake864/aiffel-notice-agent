# -*- coding: utf-8 -*-
"""웹 데모 서버.  `python web/app.py` 또는 `uvicorn web.app:app --reload`

브라우저에서 http://127.0.0.1:8000 을 열면 안내봇과 대화할 수 있다.
답변 아래에 라우팅 결과·호출한 도구·가드레일 통과 여부가 함께 표시되는데,
이게 이 데모의 핵심이다 — 틀린 답이 나왔을 때 어디서 틀렸는지 눈으로 보인다.
"""
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROUTE_KO, check_data      # noqa: E402

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="AI 에이전트 1기 안내봇")


class Ask(BaseModel):
    question: str
    thread_id: str | None = None


@app.on_event("startup")
def _startup():
    check_data()
    import agent                              # noqa: F401  미리 로딩해 첫 응답을 빠르게
    print("안내봇 준비 완료 → http://127.0.0.1:8000")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/examples")
def examples():
    """데모에서 눌러 볼 수 있는 예시 질문. 쉬운 것과 어려운 것을 섞어 둔다."""
    return {"examples": [
        {"q": "10시 10분에 입실하면 지각인가요?", "tag": "쉬움"},
        {"q": "예비군 훈련 가면 며칠 인정되고 뭘 내야 하나요?", "tag": "쉬움"},
        {"q": "훈련장려금은 하루에 얼마인가요?", "tag": "쉬움"},
        {"q": "아이가 아파서 병원에 데려가야 하는데 공가 되나요?", "tag": "어려움"},
        {"q": "이번 단위기간이 22일인데 장려금은 22일치 나오나요?", "tag": "어려움"},
        {"q": "주 15시간 미만으로 일하는데 산재보험에 가입했어요. 괜찮나요?", "tag": "어려움"},
        {"q": "시험 때문에 공가 쓰려는데 며칠 인정되나요?", "tag": "되물음"},
        {"q": "제 출석률이 지금 몇 퍼센트인가요?", "tag": "범위 밖"},
    ]}


@app.post("/api/ask")
def ask(body: Ask):
    from agent import chat_app

    tid = body.thread_id or uuid.uuid4().hex[:12]
    out = chat_app.invoke({"question": body.question},
                          {"configurable": {"thread_id": tid}})
    route = out.get("route")
    return {
        "thread_id": tid,
        "answer": out.get("answer", ""),
        "route": route,
        "route_ko": ROUTE_KO.get(route),
        "confidence": out.get("confidence"),
        "action": out.get("action"),
        "tools": out.get("tools", []),
        "guardrail_ok": out.get("guardrail_ok"),
        "violations": out.get("violations", []),
    }


app.mount("/static", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
