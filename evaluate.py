# -*- coding: utf-8 -*-
"""두 지표를 한 번에 잰다.  `python evaluate.py`

    ① 의도 분류 정확도 — 평가셋 64건, 정답 라우트와 대조
    ② 근거 기반 답변 통과율 — 직접 구성한 골든셋 37건, action·tools·must·forbid 네 축
    ③ 대화 흐름 통과율 — 멀티턴 골든셋 7개 대화 14턴

③ 은 ① ② 로는 잡히지 않는 것을 잰다. 주제 전환, 대명사 풀기, 조건 보충, 턴 간 상태 누수.
실제로 이 사각지대에서 버그 두 개가 나왔다.

무언가 고쳤으면 이걸 돌려서 숫자가 어디로 움직였는지 보면 된다.
`--only router` / `--only answer` 로 한쪽만 잴 수 있고, `--difficulty hard` 로 난이도별로
쪼개 볼 수 있다.
"""
import argparse
import json
import re

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from common import enable_utf8, pmap
from config import BASE, LABELS5, NON_COMMITTING_TOOLS, ROUTES, check_data

enable_utf8()

ASK_PAT = re.compile(r"\?|주시겠|알려\s?주|말씀해|어떤|어느|무엇")

# 되묻기와 양립하는 도구들. 이 둘은 '답을 확정'하는 도구가 아니라
# 사유를 좁히거나(search_leave_type) 어차피 함께 안내해야 하는 고정 절차를
# 가져오는(get_leave_procedure) 도구다.
#
# 앞선 모두몰 프로젝트에서, 조회를 하면 ASK 판정이 구조적으로 불가능해져
# 정답과 똑같이 답한 건이 영영 실패로 찍히는 문제를 겪었다. 원인은 채점기가
# "도구를 하나도 안 불렀을 때만 ASK" 로 판정한 것이었다. 같은 실수를 반복하지
# 않도록, 무엇이 '답을 확정하는 도구'인지 여기서 명시한다.
NON_COMMITTING = NON_COMMITTING_TOOLS   # config 에서 한 곳으로 관리한다


# ───────────────────────── ① 의도 분류 ─────────────────────────
def eval_router(report=True, difficulty=None):
    from router import app

    ev = pd.read_csv(BASE / "routing_eval.csv")
    ev = ev[ev["split"] == "eval"].reset_index(drop=True)
    if difficulty:
        ev = ev[ev["difficulty"] == difficulty].reset_index(drop=True)

    print("── ① 의도 분류 ─────────────────────────────")
    states = pmap(lambda q: app.invoke({"question": q}), ev["question"].tolist())
    pred = [s["route"] for s in states]
    y = ev["route"].tolist()
    acc = accuracy_score(y, pred)
    f1 = f1_score(y, pred, labels=LABELS5, average="macro", zero_division=0)
    print(f"[LLM 라우터] n={len(ev)}  정확도 {acc:.3f}  macro F1 {f1:.3f}")

    if report:
        print()
        print(classification_report(y, pred, labels=ROUTES, digits=3, zero_division=0))
        cm = confusion_matrix(y, pred, labels=ROUTES)
        print("[혼동 행렬] 행=정답, 열=예측")
        print(pd.DataFrame(cm, index=ROUTES, columns=ROUTES).to_string())

        ev = ev.assign(pred=pred, conf=[s["confidence"] for s in states])
        print("\n[난이도별 정확도]")
        print(ev.assign(ok=ev["route"] == ev["pred"])
                .groupby("difficulty")["ok"]
                .agg(["count", "sum", "mean"])
                .rename(columns={"count": "건수", "sum": "정답", "mean": "정확도"})
                .to_string())

        miss = ev[ev["route"] != ev["pred"]]
        print(f"\n[오분류 {len(miss)}건] — 여기를 읽는 것이 개선의 출발점이다")
        for _, r in miss.iterrows():
            print(f'  {r["qa_id"]} [{r["route"]} → {r["pred"]}] conf={r["conf"]:.2f} '
                  f'({r["difficulty"]})  {r["question"][:46]}')
            print(f'      메모: {r["note"]}')

    return {"acc": acc, "macro_f1": f1, "n": len(ev)}


# ───────────────────────── ② 근거 기반 답변 ─────────────────────────
def norm_num(s):
    return re.sub(r"(?<=\d),(?=\d)", "", str(s))


def score_turn(expect, answer, tools_called, action):
    """한 건을 채점한다. 반환: (통과 여부, 실패 항목)"""
    fails = []
    a = norm_num(answer)
    if expect["action"] != action:
        fails.append(f'action: 기대 {expect["action"]} != 실제 {action}')
    need = set(expect.get("tools", []))
    if need - set(tools_called):
        fails.append(f'tools 미호출: {sorted(need - set(tools_called))}')
    for m in expect.get("must", []):
        if norm_num(m) not in a:
            fails.append(f'must 누락: "{m}"')
    for f in expect.get("forbid", []):
        if norm_num(f) in a:
            fails.append(f'forbid 위반: "{f}"')
    if expect["action"] == "ASK" and not ASK_PAT.search(answer):
        fails.append("ASK 인데 되묻는 문장이 아님")
    return (not fails), fails


def load_cases(difficulty=None):
    gold = json.loads((BASE / "answer_goldenset.json").read_text(encoding="utf-8"))
    cases = gold["cases"]
    if difficulty:
        cases = [c for c in cases if c["difficulty"] == difficulty]
    return cases


def eval_answer(report=True, difficulty=None):
    from answer import answer_with_tools
    from tools import get_rule_violation  # noqa: F401  (도구 로딩 확인용)

    cases = load_cases(difficulty)

    # 채점기 자체 검증 — 모범 답안은 전부 통과해야 한다. 아니면 채점기가 틀린 것이다.
    bad = [c["case_id"] for c in cases
           if not score_turn(c["expect"], c["expect"]["reference"],
                             c["expect"].get("tools", []), c["expect"]["action"])[0]]
    print("── ② 근거 기반 답변 ─────────────────────────")
    print(f"[채점기 자기 검증] 모범 답안 {len(cases)}건 중 실패 {len(bad)}건 "
          f"{bad if bad else '✅'}")

    def run_case(case):
        text, results = answer_with_tools(case["question"], case["route"])
        committing = set(results) - NON_COMMITTING
        if case["route"] == "OTHER" or results.get("escalate_to_manager"):
            action = "OUT_OF_SCOPE"
        elif not committing and ASK_PAT.search(text):
            action = "ASK"
        else:
            action = "ANSWER"
        return action, text, list(results)

    outs = pmap(run_case, cases)

    rows = []
    for c, (action, text, tools) in zip(cases, outs):
        ok, fails = score_turn(c["expect"], text, tools, action)
        rows.append({"case": c["case_id"], "난이도": c["difficulty"],
                     "기대": c["expect"]["action"], "실제": action,
                     "ok": ok, "fails": "; ".join(fails), "answer": text})
    res = pd.DataFrame(rows)
    rate = res["ok"].mean()
    print(f'채점 {len(res)}건 / 통과 {res["ok"].sum()}건 ({100 * rate:.1f}%)')

    if report:
        print("\n[난이도별]")
        print(res.groupby("난이도")["ok"].agg(["count", "sum", "mean"])
              .rename(columns={"count": "건수", "sum": "통과", "mean": "통과율"}).to_string())
        print("\n[기대 행동별]")
        print(res.groupby("기대")["ok"].agg(["count", "sum", "mean"])
              .rename(columns={"count": "건수", "sum": "통과", "mean": "통과율"}).to_string())
        kinds = [f.split(":")[0] for s in res.loc[~res["ok"], "fails"] for f in s.split("; ") if f]
        print("\n[실패 유형]")
        print(pd.Series(kinds).value_counts().to_string() if kinds else "  없음")
        print("\n[실패 사례] — 여기를 읽는 것이 개선의 출발점이다")
        for _, r in res[~res["ok"]].iterrows():
            print(f'  {r["case"]} ({r["난이도"]}) 기대={r["기대"]} 실제={r["실제"]}  {r["fails"][:90]}')
            print(f'      답변: {r["answer"][:100]}')

    return {"pass_rate": rate, "n": len(res)}


# ───────────────────────── ③ 대화 흐름 ─────────────────────────
def eval_multiturn(report=True):
    """대화를 통째로 흘려보며 턴마다 채점한다.

    ① ② 는 문의 한 건을 따로 던진다. 실제 상담은 그렇지 않다. 앞 턴을 물려받아야 하는
    경우(대명사)와 물려받으면 안 되는 경우(주제 전환)를 모두 여기서 잰다.
    """
    import uuid

    from agent import build_agent
    from langgraph.checkpoint.memory import InMemorySaver

    gold = json.loads((BASE / "multiturn_goldenset.json").read_text(encoding="utf-8"))
    convs = gold["conversations"]
    print("── ③ 대화 흐름 ─────────────────────────────")

    def run_conv(conv):
        """대화 하나를 처음부터 끝까지 흘린다. 대화마다 새 체크포인터를 쓴다."""
        app = build_agent(checkpointer=InMemorySaver())
        cfg = {"configurable": {"thread_id": uuid.uuid4().hex[:12]}}
        rows = []
        for i, turn in enumerate(conv["turns"], 1):
            out = app.invoke({"question": turn["text"]}, cfg)
            e = turn.get("expect")
            if not e:
                continue
            tools = out.get("tools") or []
            fails = []
            if e["action"] != out.get("action"):
                fails.append(f'action: 기대 {e["action"]} != 실제 {out.get("action")}')
            if set(e.get("tools", [])) - set(tools):
                fails.append(f'tools 미호출: {sorted(set(e["tools"]) - set(tools))}')
            leaked = set(e.get("forbid_tools", [])) & set(tools)
            if leaked:
                fails.append(f'앞 턴 주제로 조회: {sorted(leaked)}')
            answer = norm_num(out.get("answer", ""))
            for m in e.get("must", []):
                if norm_num(m) not in answer:
                    fails.append(f'must 누락: "{m}"')
            for f in e.get("forbid", []):
                if norm_num(f) in answer:
                    fails.append(f'forbid 위반: "{f}"')
            rows.append({"conv": conv["conv_id"], "kind": conv["kind"], "turn": i,
                         "ok": not fails, "fails": "; ".join(fails),
                         "tools": tools, "answer": out.get("answer", "")})
        return rows

    res = pd.DataFrame([r for rows in pmap(run_conv, convs) for r in rows])
    turn_rate = res["ok"].mean()
    done = res.groupby("conv")["ok"].all()
    conv_rate = done.mean()
    print(f'대화 {len(convs)}개 / {len(res)}턴 · 턴 통과 {res["ok"].sum()}건 '
          f'({100 * turn_rate:.1f}%) · 끝까지 통과한 대화 {done.sum()}개 '
          f'({100 * conv_rate:.1f}%)')

    if report:
        print("\n[유형별]")
        print(res.groupby("kind")["ok"].agg(["count", "sum", "mean"])
              .rename(columns={"count": "턴", "sum": "통과", "mean": "통과율"}).to_string())
        print("\n[실패 턴] — 여기를 읽는 것이 개선의 출발점이다")
        bad = res[~res["ok"]]
        if bad.empty:
            print("  없음")
        for _, r in bad.iterrows():
            print(f'  {r["conv"]} {r["turn"]}턴 ({r["kind"]})  {r["fails"][:88]}')
            print(f'      tools={r["tools"]}')
            print(f'      답변: {r["answer"][:95]}')

    return {"turn_rate": turn_rate, "turns": len(res),
            "conv_rate": conv_rate, "convs": len(convs)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="두 지표를 잰다")
    ap.add_argument("--only", choices=["router", "answer", "multiturn"],
                    help="하나만 재기")
    ap.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="난이도별로 재기")
    ap.add_argument("--quiet", action="store_true", help="요약만")
    args = ap.parse_args()

    check_data()
    out = {}
    if args.only in (None, "router"):
        out["router"] = eval_router(report=not args.quiet, difficulty=args.difficulty)
        print()
    if args.only in (None, "answer"):
        out["answer"] = eval_answer(report=not args.quiet, difficulty=args.difficulty)
        print()
    if args.only in (None, "multiturn"):
        out["multiturn"] = eval_multiturn(report=not args.quiet)

    print("\n══ 요약 ══")
    if "router" in out:
        print(f'  ① 의도 분류   정확도 {out["router"]["acc"]:.3f} · '
              f'macro F1 {out["router"]["macro_f1"]:.3f} ({out["router"]["n"]}건)')
    if "answer" in out:
        print(f'  ② 근거 답변   통과율 {100 * out["answer"]["pass_rate"]:.1f}% '
              f'({out["answer"]["n"]}건)')
    if "multiturn" in out:
        m = out["multiturn"]
        print(f'  ③ 대화 흐름   턴 통과율 {100 * m["turn_rate"]:.1f}% ({m["turns"]}턴) · '
              f'대화 완주율 {100 * m["conv_rate"]:.1f}% ({m["convs"]}개)')
