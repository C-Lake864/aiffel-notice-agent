# -*- coding: utf-8 -*-
"""답변을 두 가지로 점검한다.

① 숫자의 출처 역추적 — 허용 집합 = 조회 결과 + 매뉴얼 고정값 + 한 단계 산술 유도값.
② 근거 표기 — 규정을 안내하면서 출처를 밝히지 않은 답변을 잡는다.

숫자가 아닌 오류는 못 잡는다는 한계가 있다.
"""
import json
import re

from context import FIXED_POLICY

# 이 낱말이 답변에 있으면 규정을 안내한 것으로 보고 근거 표기를 요구한다.
POLICY_WORDS = re.compile(
    r"인정|제출|신청|기준|출석|결석|지각|조퇴|외출|공가|휴가|장려금|제적|경고|수료|졸업|서류")

# 개인 기록을 단정하면 안 된다(매뉴얼 9.3). 이런 표현이 있으면 위반으로 본다.
PERSONAL_CLAIM = re.compile(
    r"(귀하|회원님|훈련생님)?\s*(의)?\s*(잔여|남은)\s*(결석|출석)|"
    r"현재\s*출석률은|지급될\s*금액은|제적\s*대상입니다|경고\s*\d+회\s*누적되었")


def numbers_in(obj):
    """문자열/딕셔너리/리스트에서 정수들을 모두 뽑아낸다(콤마 제거 후)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)          # 20,000 -> 20000
    return {int(m) for m in re.findall(r"\d+", text)}


def allowed_numbers(tool_results):
    """조회 결과 + 매뉴얼 고정값 + 한 단계 산술 유도값을 허용 집합으로 만든다."""
    allowed = set()
    for v in FIXED_POLICY.values():                      # 매뉴얼 고정값
        if isinstance(v, int):
            allowed.add(v)
        elif isinstance(v, list):
            allowed.update(x for x in v if isinstance(x, int))
    tool_nums = set()
    for r in (tool_results or {}).values():
        tool_nums |= numbers_in(r)
    allowed |= tool_nums
    base = sorted(allowed)
    for a in base:                                       # 한 단계 산술 유도값
        for b in base:
            if a > b:
                allowed.add(a - b)
            allowed.add(a + b)
    return allowed, tool_nums


def guardrail(answer, tool_results=None, min_check=100):
    """답변을 점검한다. 위반이 있으면 목록으로 돌려준다.

    min_check 를 100 으로 둔 이유: 이 도메인에서 의미 있는 수치는 일수(1~120), 비율(20~80),
    금액(10000~20000), 시각(10:10~18:10)이다. 두 자리 이하는 문장 속 조사·순번과 섞여
    오탐이 많아, 세 자리 이상만 출처를 따진다. 시각과 일수는 ②·③ 규칙이 따로 잡는다.
    """
    allowed, tool_nums = allowed_numbers(tool_results)
    found = numbers_in(answer)
    suspicious = sorted(n for n in found if n >= min_check and n not in allowed)

    violations = []
    if suspicious:
        violations.append({"type": "출처 불명 수치",
                           "detail": f"조회 결과·매뉴얼 고정값에 없는 숫자: {suspicious}"})

    # ② 규정을 안내했는데 근거를 밝히지 않은 경우 (매뉴얼 답변 규칙 8)
    if POLICY_WORDS.search(answer) and "근거:" not in answer:
        violations.append({"type": "근거 미표기",
                           "detail": "규정을 안내하면서 (근거: ...) 줄을 붙이지 않았습니다"})

    # ③ 조회 없이 공가 인정일수를 단정했는지 (매뉴얼 3.2)
    if re.search(r"(인정일|인정\s*일수|출석\s*인정)", answer) and re.search(r"\d+\s*일", answer):
        if "get_leave_detail" not in (tool_results or {}):
            violations.append({"type": "툴 미호출 단정",
                               "detail": "공가 인정일수를 get_leave_detail 조회 없이 단정"})

    # ④ 개인 기록을 단정했는지 (매뉴얼 9.3)
    if PERSONAL_CLAIM.search(answer):
        violations.append({"type": "개인 기록 단정",
                           "detail": "개인의 출결·장려금·경고 기록을 단정했습니다"})

    return {"ok": not violations, "violations": violations,
            "numbers_in_answer": sorted(found), "from_tools": sorted(tool_nums)}
