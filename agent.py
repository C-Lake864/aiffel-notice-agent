# -*- coding: utf-8 -*-
"""라우터 · 조회 · 생성 · 가드레일을 하나의 그래프로 잇는다.

route → answer → guard → (END | answer 재시도 | escalate)
"""
import operator
from typing import Annotated, List, Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from answer import answer_with_tools
from guardrail import guardrail
from router import app as router_app
from tools import escalate_to_manager


class AgentState(TypedDict, total=False):
    """파이프라인 전체가 통과하는 State."""

    question: str
    history: Annotated[list, operator.add]   # 리듀서가 붙어 있어 턴마다 덮이지 않고 쌓인다
    route: str
    confidence: float
    action: str                 # HANDLE / ASK / ANSWER / ESCALATE / OUT_OF_SCOPE
    tools: List[str]
    results: dict
    answer: str
    guardrail_ok: Optional[bool]
    violations: list
    attempts: int


def with_history(state: AgentState) -> str:
    """앞 턴의 발화를 맥락으로 덧붙인다. 대화가 없으면 이번 발화 그대로.

    앞 턴과 이번 턴을 **구분 없이 이어 붙이면 안 된다.** 그냥 붙이면
    "아이가 아파서 병원에… / 시험 때문에 공가…" 가 한 문장이 되어, 주제가 바뀌었는데도
    앞 주제(질병)로 조회해 엉뚱한 답이 나간다. 라벨을 붙여 무엇이 이번 질문인지 밝힌다.
    """
    prior = state.get("history") or []
    if not prior:
        return state["question"]
    lines = [f"[이전 문의 {i}] {q}" for i, q in enumerate(prior[-3:], 1)]
    lines.append(f"[이번 문의] {state['question']}")
    return "\n".join(lines)


def node_route(state):
    """① 분류 — 라우터 그래프를 그대로 부른다. 턴마다 상태를 여기서 초기화한다.

    history 를 빼면 State 는 checkpointer 에 그대로 남아 다음 턴으로 넘어온다. 초기화하지
    않으면 조회 없이 끝나는 턴(응대 범위 밖·이관)에서 **앞 턴의 tools·results 가 그대로
    표시되어**, 부르지도 않은 도구를 부른 것처럼 보인다.
    """
    r = router_app.invoke({"question": with_history(state)})
    return {"route": r["route"], "confidence": r["confidence"], "action": r["action"],
            "tools": [], "results": {}, "answer": "",
            "guardrail_ok": None, "violations": [], "attempts": 0}


def node_answer(state: AgentState) -> AgentState:
    """② 조회 + ③ 생성 — 안에서 도구 호출 그래프가 한 바퀴 돈다."""
    text, results = answer_with_tools(with_history(state), state["route"])
    if results.get("escalate_to_manager", {}).get("escalated"):
        return {"action": "ESCALATE", "tools": list(results), "results": results,
                "answer": text, "history": [state["question"]]}
    if not results:                       # 조회할 단서가 없어 모델이 되물은 경우
        return {"action": "ASK", "tools": [], "results": {}, "answer": text,
                "history": [state["question"]]}
    return {"tools": list(results), "results": results, "answer": text,
            "history": [state["question"]],
            "attempts": state.get("attempts", 0) + 1}


def node_guard(state: AgentState) -> AgentState:
    """④ 가드레일 — 출처 없는 숫자나 근거 미표기가 있으면 되돌려 보낸다."""
    g = guardrail(state["answer"], state["results"])
    return {"guardrail_ok": g["ok"], "violations": g["violations"],
            "action": "ANSWER" if g["ok"] else "RETRY"}


def node_escalate(state: AgentState) -> AgentState:
    reason = {"ESCALATE": "분류확신도미달", "OUT_OF_SCOPE": "응대범위밖"}.get(
        state["action"], "가드레일위반")
    if state["action"] == "OUT_OF_SCOPE":
        msg = ("개인별 기록은 안내봇에서 확인할 수 없어 운영매니저에게 디스코드 DM으로 "
               "문의해 주셔야 확인이 가능합니다.")
    else:
        msg = escalate_to_manager(reason, {"q": state["question"]})["message"]
    return {"answer": msg, "guardrail_ok": state.get("guardrail_ok")}


def after_route(state: AgentState) -> str:
    return "answer" if state["action"] == "HANDLE" else "escalate"


def after_answer(state: AgentState) -> str:
    if state["action"] == "ASK":
        return END
    return "escalate" if state["action"] in ("OUT_OF_SCOPE", "ESCALATE") else "guard"


def after_guard(state: AgentState) -> str:
    """통과하면 끝. 위반이면 한 번 더 생성해 보고, 그래도 안 되면 이관한다."""
    if state["guardrail_ok"]:
        return END
    return "answer" if state.get("attempts", 0) < 2 else "escalate"


def build_agent(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("route", node_route)
    g.add_node("answer", node_answer)
    g.add_node("guard", node_guard)
    g.add_node("escalate", node_escalate)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", after_route, {"answer": "answer", "escalate": "escalate"})
    g.add_conditional_edges("answer", after_answer,
                            {"guard": "guard", "escalate": "escalate", END: END})
    g.add_conditional_edges("guard", after_guard,
                            {"answer": "answer", "escalate": "escalate", END: END})
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer)


agent_app = build_agent()
chat_app = build_agent(checkpointer=InMemorySaver())     # 대화용(맥락 유지)


def notice_agent(question):
    """문의 한 줄을 파이프라인에 통과시킨다."""
    out = agent_app.invoke({"question": question})
    if out["action"] == "RETRY":
        out["action"] = "ESCALATE"
    return {"question": question, **out}
