# -*- coding: utf-8 -*-
"""매뉴얼을 장 단위로 쪼개고, 라우트에 필요한 장만 골라 컨텍스트를 만든다.

전문을 넣지 않는 이유는 두 가지다. 입력이 길어 비용과 지연이 늘고, 관련 없는 규정이
오답을 유도한다(출결 문의에 제적 기준이 섞여 들어가는 식).
"""
import json
import re

from config import BASE

POLICY = BASE / "notice_manual.md"


def split_sections(text):
    """'## ' 헤딩 단위로 매뉴얼을 쪼갠다. 키는 장 번호(문자열), 부록은 제외."""
    parts = re.split(r"^## ", text, flags=re.M)
    out = {"_header": parts[0].strip()}
    for p in parts[1:]:
        title = p.split("\n", 1)[0].strip()
        if title.startswith("부록"):        # 부록은 안내 문구 모음
            continue
        m = re.match(r"(\d+)\.", title)
        key = m.group(1) if m else title
        out[key] = "## " + p.rstrip()
    return out


sections = split_sections(POLICY.read_text(encoding="utf-8"))


SECTION_MAP = {
    "ATTENDANCE": ["2"],          # 2장 출결
    "LEAVE":      ["3"],          # 3장 공가와 휴가
    "STIPEND":    ["4", "5"],     # 4장 훈련장려금 + 5장 고용형태
    "RULES":      ["6", "7"],     # 6장 참여 규칙 + 7장 경고와 제적
    "SCHEDULE":   ["8"],          # 8장 일정과 툴
    "OTHER":      [],
}

# 어느 라우트에서든 필요한 장 — 과정 기본 정보, 분류 기준, 응대 범위
ALWAYS = ["이 매뉴얼을 쓰는 방법", "0", "1", "9"]


def build_context(route, secs=None):
    """라우트에 필요한 매뉴얼 조각만 이어 붙여 프롬프트용 컨텍스트를 만든다."""
    secs = sections if secs is None else secs
    keys = [k for k in ALWAYS + SECTION_MAP.get(route, []) if k in secs]
    return "\n\n".join([secs["_header"]] + [secs[k] for k in keys])


# 매뉴얼 본문에 그대로 적힌 고정값. 가드레일의 허용 집합에 들어간다.
FIXED_POLICY = {
    "total_training_days": 120,        # 0장 훈련일수
    "daily_hours": 7,                  # 0장 1일 출석시간
    "completion_rate": 80,             # 0.2 수료 기준(%)
    "graduation_score": 50,            # 0.2 졸업 학습점수(%)
    "expulsion_total_rate": 20,        # 7.1 전체 결석 기준(%)
    "expulsion_unit_rate": 50,         # 7.1 단위기간 결석 기준(%)
    "late_accumulation": 3,            # 2.1 지각·조퇴·외출 3회 = 결석 1회
    "away_minutes": 20,                # 2.1 무단 이석 기준(분)
    "return_buffer_minutes": 10,       # 2.3 외출 복귀 여유(분)
    "unit_count": 7,                   # 0.1 단위기간 개수
    "stipend_daily": 20000,            # 4.2 1일 장려금
    "stipend_base": 10000,             # 4.2 기본
    "stipend_kdt": 10000,              # 4.2 KDT 특별수당
    "stipend_max_days": 20,            # 4.2 최대 지급일수
    "payout_weeks": [2, 4],            # 4.3 지급 소요(주)
    "employment_report_weeks": 2,      # 5.2 개강 후 변경 신청 기한(주)
    "sidejob_week_hours": 15,          # 5.3 주 근무시간 기준
    "sidejob_month_hours": 60,         # 5.3 월 근무시간 기준
    "leave_apply_plus_days": 1,        # 3.1 공가 신청 기한(발생일 +1일)
    "document_days": 7,                # 3.1 증빙 제출 기한(일주일)
    "clock": [10, 0, 10, 10, 11, 13, 14, 30, 17, 40, 49, 50, 18, 0, 10],  # 2.2 기준 시각들
}

TOOL_NAMES = ["search_leave_type", "get_leave_detail", "list_leave_types",
              "get_leave_procedure", "get_attendance_rule", "get_unit_period",
              "get_completion_criteria", "get_stipend_policy", "get_employment_docs",
              "get_side_job_rule", "get_schedule", "get_rule_violation",
              "get_tool_setup", "escalate_to_manager"]


def build_answer_prompt(question, route, tool_results=None):
    """답변 생성용 시스템 프롬프트를 조립한다."""
    from prompts import ANSWER_RULES
    ctx = build_context(route)
    tr = json.dumps(tool_results or {}, ensure_ascii=False, indent=1)
    return (f"{ANSWER_RULES}\n"
            f"===== 안내 매뉴얼 (라우트: {route}) =====\n{ctx}\n\n"
            f"===== 조회 결과 =====\n{tr}\n")
