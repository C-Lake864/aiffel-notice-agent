# -*- coding: utf-8 -*-
"""직접 말을 걸어 본다.  `python chat.py`  또는  `python chat.py "공가 며칠까지 인정돼요?"`

매 턴 아래에 route · 확신도 · 호출한 도구 · 가드레일 통과 여부가 함께 찍힌다.
틀린 답이 나오면 그 로그가 라우팅·조회·생성 셋 중 어디서 틀렸는지 알려 준다.
"""
import itertools
import sys

from common import enable_utf8
from config import ROUTE_KO, check_data

enable_utf8()

_session = itertools.count(1)


def trace(out):
    conf = out.get("confidence")
    conf_s = f"{conf:.2f}" if conf is not None else "-"
    route = out.get("route", "-")
    print(f'안내봇 > {out["answer"]}')
    print(f'         ↳ route={route}({ROUTE_KO.get(route, "-")}) conf={conf_s} '
          f'action={out["action"]} tools={out.get("tools", [])} '
          f'guardrail={out.get("guardrail_ok")}')
    for v in out.get("violations") or []:
        print(f'           ⚠ {v["type"]}: {v["detail"]}')
    print()


def ask(question, thread_id="demo"):
    """한 턴만 물어본다. 같은 thread_id 로 다시 부르면 앞 턴이 이어진다."""
    from agent import chat_app
    out = chat_app.invoke({"question": question}, {"configurable": {"thread_id": thread_id}})
    print(f"훈련생 > {question}")
    trace(out)
    return out


def chat(thread_id=None):
    """대화를 연다. 빈 줄이나 '그만' 을 입력하면 끝난다."""
    from agent import chat_app
    tid = thread_id or f"you-{next(_session)}"
    cfg = {"configurable": {"thread_id": tid}}
    print(f"[대화 {tid}] 문의를 입력하세요. 끝내려면 빈 줄 또는 '그만'.\n")
    while True:
        try:
            q = input("훈련생 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n끝냅니다.")
            return
        if not q or q in ("그만", "exit", "quit"):
            break
        trace(chat_app.invoke({"question": q}, cfg))
    said = chat_app.get_state(cfg).values.get("history") or []
    print(f"끝냅니다. 오간 문의 {len(said)}건: {said}")


if __name__ == "__main__":
    check_data()
    if len(sys.argv) > 1:
        ask(" ".join(sys.argv[1:]))
    else:
        chat()
