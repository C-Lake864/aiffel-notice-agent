# -*- coding: utf-8 -*-
"""의도 분류 라우터. State 하나와 노드 둘로 된 그래프다.

classify 는 모델이 하는 일(분류), gate 는 정책이 정하는 일(처리/이관/범위밖)이다.
둘을 나눠 둔 덕에 임계값만 바꿀 때 모델을 다시 부르지 않아도 된다.
"""
from typing import Literal, Optional, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from config import CONF_THRESHOLD, MODEL
from prompts import ROUTE_GUIDE


class RouterState(TypedDict, total=False):
    """그래프를 통과하며 채워지는 값들. 노드는 자기가 바꾼 키만 돌려준다."""

    question: str           # 입력 — 훈련생 문의 한 문장
    route: str              # ① 분류 노드가 채운다
    confidence: float       # ① 분류 노드가 채운다
    reason: str             # ① 분류 노드가 채운다
    action: str             # ② 판정 노드가 채운다 — HANDLE / ESCALATE / OUT_OF_SCOPE
    message: Optional[str]  # ② 판정 노드가 채운다 — 훈련생에게 바로 나갈 문구


class RouteDecision(BaseModel):
    """훈련생 문의 한 건에 대한 라우팅 판단 결과."""

    route: Literal["ATTENDANCE", "LEAVE", "STIPEND", "RULES", "SCHEDULE", "OTHER"] = Field(
        description="문의를 배정할 라우트. 6개 값 중 하나만 사용한다.")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="판단의 확신도. 두 라우트 사이에서 애매하면 0.5 미만으로 낮춘다.")
    reason: str = Field(
        description="그 라우트로 판단한 근거를 한 문장으로. 훈련생이 얻으려는 결과를 기준으로 쓴다.")


_router_chain = None


def classify(state: RouterState) -> RouterState:
    """노드 ① 분류 — 구조화 출력으로 라우트·확신도·근거를 한 번에 받는다."""
    global _router_chain
    if _router_chain is None:
        _router_chain = init_chat_model(
            MODEL, temperature=0, timeout=60, max_retries=2
        ).with_structured_output(RouteDecision)
    d = _router_chain.invoke(
        [("system", ROUTE_GUIDE), ("human", f"훈련생 문의: {state['question']}")])
    return {"route": d.route, "confidence": d.confidence, "reason": d.reason}


def gate(state: RouterState) -> RouterState:
    """노드 ② 판정 — 확신도와 응대 범위를 보고 처리/이관/범위밖을 정한다."""
    if state["confidence"] < CONF_THRESHOLD:
        return {"action": "ESCALATE",
                "message": "정확한 확인을 위해 운영매니저에게 디스코드 DM으로 문의해 주시기 바랍니다."}
    if state["route"] == "OTHER":
        return {"action": "OUT_OF_SCOPE",
                "message": "개인별 기록은 안내봇에서 확인할 수 없어 운영매니저에게 "
                           "디스코드 DM으로 문의해 주셔야 확인이 가능합니다."}
    return {"action": "HANDLE", "message": None}


def build(node=None):
    """노드를 이름으로 찾아 그래프를 만든다.

    globals()[...] 로 찾기 때문에, 같은 이름의 함수를 다시 정의한 뒤 build() 를 한 번 더
    부르면 그 노드만 갈아 끼워진다.
    """
    g = StateGraph(RouterState)
    g.add_node("classify", node or globals()["classify"])
    g.add_node("gate", globals()["gate"])
    g.add_edge(START, "classify")
    g.add_edge("classify", "gate")
    g.add_edge("gate", END)
    return g.compile()


app = build()


def route(question):
    """문의 한 줄을 라우터에 통과시킨다."""
    return app.invoke({"question": question})
