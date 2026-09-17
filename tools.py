# -*- coding: utf-8 -*-
"""조회 도구. 매뉴얼의 [조회] 표시에서 도출한 것들이다.

고칠 때 주의할 점 두 가지.
- 선택 인자는 반드시 `Optional[...]` 로 적는다. 타입이 str 인데 기본값이 None 이면
  모델이 '모름'의 뜻으로 None 을 보냈을 때 스키마 검증에서 거부당한다.
- docstring 첫 줄이 모델이 읽는 도구 설명이다. 여기를 고치면 도구 선택이 달라진다.
"""
import json
import re
from datetime import date, datetime
from typing import Optional

from config import BASE


def _load(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


LEAVES = _load("leave_types.json")["leaves"]
SCHEDULE = _load("schedule.json")["events"]
UNITS = _load("unit_periods.json")
EMPLOY = _load("employment_docs.json")

LEAVE_BY_TYPE = {l["leave_type"]: l for l in LEAVES}

# 훈련생이 실제로 쓰는 말 → 공가 리스트의 정식 사유명
LEAVE_ALIASES = {
    "출산(배우자)": ["출산", "배우자출산", "아이", "출산휴가"],
    "휴가": ["연차", "월차", "휴가", "쉬는날", "개인사정", "개인적인일"],
    "해커톤 참여": ["해커톤", "경진대회", "공모전", "대회"],
    "결혼": ["결혼", "결혼식", "혼인", "예식"],
    "입사시험": ["면접", "입사", "채용", "취업", "인적성", "입사시험", "시험"],
    "질병 / 입원": ["질병", "입원", "병원", "아파서", "아픔", "몸살", "감기", "진료",
                 "치료", "수술", "병가", "통원"],
    "자격시험": ["자격증", "자격시험", "시험", "응시"],
    # 훈련생은 사유명("사망")이 아니라 호칭으로 말한다. 호칭이 빠져 있으면
    # '할아버지 상을 당했는데'가 조회되지 않아 "확인되지 않는다"고 답하게 된다.
    "사망": ["사망", "장례", "조의", "부고", "상조", "발인", "빈소", "돌아가",
           "조부", "조모", "조부모", "할아버지", "할머니", "외할아버지", "외할머니",
           "아버지", "어머니", "부모님", "형제", "자매", "누나", "형", "오빠", "언니", "동생"],
    "예비군 / 민방위": ["예비군", "민방위", "동원훈련", "훈련소"],
}


def _norm(s):
    """공백·가운뎃점·슬래시를 지워 비교하기 쉽게 만든다."""
    return re.sub(r"[\s·/()]+", "", str(s))


def search_leave_type(query: str) -> dict:
    """공가 사유를 훈련생이 말한 표현으로 찾는다. 공가·휴가 문의에서 가장 먼저 부르는 도구다.

    후보를 점수와 함께 돌려준다. 후보가 여럿이면 확정하지 말고 어떤 사유인지 되물어야 한다.
    """
    q = _norm(query)
    if not q:
        return {"query": query, "candidates": [], "resolved_leave_type": None,
                "ambiguous": False, "note": "질의가 비어 있습니다."}

    hits = []
    for name, aliases in LEAVE_ALIASES.items():
        flat = _norm(name)
        score = 0.0
        # 정식 사유명이 질의에 통째로 들어 있으면 만점
        if flat and flat in q:
            score = 1.0
        else:
            for a in aliases:
                if _norm(a) in q:
                    # 별칭이 길수록 확실한 신호다. '시험'(2자)보다 '자격시험'(4자)이 강하다.
                    score = max(score, 0.6 + 0.1 * min(len(_norm(a)) - 1, 4))
        if score:
            hits.append({"leave_type": name, "score": round(score, 2)})

    hits.sort(key=lambda h: -h["score"])
    top = [h for h in hits if h["score"] == hits[0]["score"]] if hits else []
    return {
        "query": query,
        "candidates": hits[:5],
        "resolved_leave_type": top[0]["leave_type"] if len(top) == 1 else None,
        "ambiguous": len(top) > 1,
        "note": ("후보가 여러 개입니다. 어떤 사유인지 훈련생에게 확인하십시오."
                 if len(top) > 1 else
                 None if hits else "공가 리스트에 없는 사유입니다. 운영매니저 확인이 필요합니다."),
    }


def get_leave_detail(leave_type: str) -> dict:
    """공가 사유 하나의 인정일수·증빙서류·유의사항을 조회한다. 인정일수는 반드시 여기서 가져온다."""
    row = LEAVE_BY_TYPE.get(leave_type)
    if not row:
        near = [t for t in LEAVE_BY_TYPE if _norm(leave_type) in _norm(t)
                or _norm(t) in _norm(leave_type)]
        return {"found": False, "leave_type": leave_type,
                "available": list(LEAVE_BY_TYPE), "did_you_mean": near}
    return {"found": True, "source": "공가 리스트", **row}


def list_leave_types() -> dict:
    """출석 인정되는 공가 사유 전체 목록을 돌려준다. '어떤 경우에 공가가 되나요' 문의에 쓴다."""
    return {"source": "공가 리스트", "count": len(LEAVES),
            "leave_types": [l["leave_type"] for l in LEAVES]}


def get_leave_procedure() -> dict:
    """공가 신청 기한·증빙 제출 기한·제출처·서류 필수 기재사항을 조회한다."""
    return {
        "source": "공가 및 휴가에 대하여",
        "apply_deadline": "발생일 +1일까지 전산 신청",
        "document_deadline": "일주일 이내",
        "apply_form": "[운영 공지의 공가 신청서 폼 참조]",
        "document_form": "[운영 공지의 공가 증빙서류 제출 폼 참조]",
        "required_on_document": ["이름", "생년월일", "일자", "발급기관 직인"],
        "warning": "서류 미제출 시 인정 불가",
    }


def get_attendance_rule(topic: Optional[str] = None) -> dict:
    """출결 기준 시각과 판정 기준을 조회한다. 지각·조퇴·외출·결석의 경계를 물으면 부른다.

    topic 에 '지각' '조퇴' '외출' '결석' '퇴실' 중 하나를 넣으면 그 항목만 돌려준다.
    """
    rules = {
        "정상출석": {"입실": "10:00", "퇴실": "18:00", "1일 출석시간": "7시간"},
        "지각": {"기준": "10:11 이후 입실", "정상 인정": "10:10까지"},
        "조퇴": {"기준": "14:30~17:49 퇴실", "정상 퇴실 가능": "17:50부터"},
        "퇴실": {"체크 시간": "17:50~18:10",
                "주의": "본인 부주의로 퇴실을 체크하지 못하면 출석 인정이 어렵습니다"},
        "외출": {"가능 시한": "훈련 종료 10분 전까지",
                "복귀 기한": "17:40까지 (17:50 퇴실 기준)",
                "주의": "외출 처리 없이 무단으로 20분 이상 자리를 비우면 부정 훈련으로 처리될 수 있습니다"},
        "결석": {"기준": "1일 출석시간 7시간 중 50% 미충족",
                "예시": ["14:30 이전 퇴실", "외출 후 미복귀 또는 외출이 출석시간 50% 초과",
                       "입실 미진행 또는 14:30 이후 참여", "입실 후 퇴실 미진행"]},
        "누적": {"규칙": "지각·조퇴·외출 3회 누적 시 결석 1회"},
    }
    if topic:
        for k, v in rules.items():
            if k in topic or topic in k:
                out = {"source": "출결에 대하여", "topic": k, "rule": v}
                # 지각·조퇴·외출·퇴실은 결과가 결석 판정으로 이어진다. 그 항목만 떼어
                # 돌려주면 "퇴실 미진행 = 결석"이라는 결론이 가려져 답변이 반쪽이 된다.
                if k in ("퇴실", "외출", "조퇴", "지각"):
                    out["결석 판정"] = rules["결석"]
                    out["누적 규칙"] = rules["누적"]
                return out
    return {"source": "출결에 대하여", "rules": rules}


def get_unit_period(on_date: Optional[str] = None,
                    unit: Optional[int] = None) -> dict:
    """단위기간을 조회한다. 날짜(YYYY-MM-DD)를 주면 그 날이 속한 단위기간과 소정훈련일수를 돌려준다."""
    if unit:
        for u in UNITS["units"]:
            if u["unit"] == unit:
                return {"source": "AI 에이전트 훈련 정보", **u}
        return {"found": False, "unit": unit, "available": [u["unit"] for u in UNITS["units"]]}
    if on_date:
        for u in UNITS["units"]:
            if u["start"] <= on_date <= u["end"]:
                return {"source": "AI 에이전트 훈련 정보", "on_date": on_date, **u}
        return {"found": False, "on_date": on_date,
                "note": "훈련기간 밖이거나 단위기간 사이의 공백입니다.",
                "units": UNITS["units"]}
    return {"source": "AI 에이전트 훈련 정보", "course_period": UNITS["period"],
            "daily": UNITS["daily"], "units": UNITS["units"]}


def get_completion_criteria() -> dict:
    """수료·졸업 기준과 제적 기준선을 계산해서 돌려준다. '며칠까지 빠져도 되나요' 문의에 쓴다."""
    total = UNITS["period"]["total_training_days"]
    return {
        "source": "AI 에이전트 훈련 정보 · 출결에 대하여",
        "total_training_days": total,
        "completion": {"기준": "전체 훈련일수의 80% 이상 출석",
                       "필요 출석일수": round(total * 0.8),
                       "허용 결석일수": total - round(total * 0.8)},
        "graduation": {"기준": ["수료 출석률 충족", "학습 점수 50% 이상"],
                       "반영": ["퀘스트 점수", "노드 누적 별점", "해커톤 프로젝트 점수"]},
        "expulsion": {"전체 기준": "전체 훈련기간의 20% 이상 결석",
                      "전체 기준 일수": round(total * 0.2),
                      "단위기간 기준": "단위기간 내 50% 이상 결석"},
        "caution": "개인별 잔여 결석일수는 안내봇에서 확인할 수 없습니다. 운영매니저 확인이 필요합니다.",
    }


def get_stipend_policy() -> dict:
    """훈련장려금 지급 기준·금액·절차·소요기간을 조회한다. 금액은 반드시 여기서 가져온다."""
    return {
        "source": "훈련 장려금 지급/확인",
        "conditions": ["단위기간 내 80% 이상 출석", "고용형태에 따라 지급"],
        "daily_amount": 20000,
        "daily_breakdown": {"기본": 10000, "KDT 특별수당": 10000},
        "max_days_per_unit": 20,
        "calc": "1일 20,000원 × 출석일수. 단 20일을 초과해도 20일분까지만 지급.",
        "example": "단위기간이 22일이고 22일 출석해도 20일분 지급 / 단위기간이 18일이면 18일분 지급",
        "payout_lead_time": "신청 후 2~4주 (고용센터 처리 기준)",
        "confirm_step": "개별 문자 확인 후 디스코드 공지 쓰레드에 '성함/확인완료' 작성",
        "blocking": "모든 인원의 확인이 완료되어야 신청 가능",
        "duplicate": {"국민취업지원제도": "중복 수급 가능",
                      "지자체 등 타기관 구직활동 지원금": "중복 수급 불가"},
        "caution": "개인별 지급 금액은 안내봇에서 확인할 수 없습니다.",
    }


def get_employment_docs(employment: Optional[str] = None,
                        change_from: Optional[str] = None,
                        change_to: Optional[str] = None) -> dict:
    """고용형태별 제출 서류를 조회한다. 최초 제출은 employment, 변경은 change_from/change_to 를 쓴다."""
    if change_from or change_to:
        rows = EMPLOY["changes"]
        if change_from:
            rows = [r for r in rows if _norm(change_from) in _norm(r["before"])
                    or _norm(r["before"]) in _norm(change_from)]
        if change_to:
            rows = [r for r in rows if _norm(change_to) in _norm(r["after"])
                    or _norm(r["after"]) in _norm(change_to)]
        return {"source": "수강 중 고용 형태 관련 안내", "kind": "변경",
                "matches": rows, "all_changes": EMPLOY["changes"] if not rows else None,
                "report_deadline": EMPLOY["report_deadline"]}
    if employment:
        rows = [r for r in EMPLOY["initial"]
                if _norm(employment) in _norm(r["employment"])
                or _norm(r["employment"]) in _norm(employment)]
        return {"source": "수강 중 고용 형태 관련 안내", "kind": "최초",
                "matches": rows, "all_initial": EMPLOY["initial"] if not rows else None}
    return {"source": "수강 중 고용 형태 관련 안내", "initial": EMPLOY["initial"],
            "changes": EMPLOY["changes"], "report_deadline": EMPLOY["report_deadline"]}


def get_side_job_rule() -> dict:
    """아르바이트·프리랜서 병행 시의 신고 의무와 장려금 수급 가능 여부를 조회한다."""
    return {
        "source": "수강 중 고용 형태 관련 안내",
        "time_rule": "교육시간(월~금 10:00~18:00) 외에만 가능",
        "must_report_if": ["주 15시간 이상 근무", "월 60시간 이상 근무",
                           "4대 보험 중 하나라도 가입",
                           "특수형태근로종사자(프리랜서, 보험설계 등)로 계약"],
        "if_reported_case": "위 항목에 해당하면 훈련장려금 수급 불가 대상자",
        "allowed_case": "고용보험 가입 후 주 15시간 또는 월 60시간 미만 근무 시 장려금 지급 가능",
        "extra_docs": ["근로계약서", "급여명세서", "출근부"],
        "trap": "주 15시간 미만이어도 산업재해 보험에 가입하면 특수형태근로종사자에 해당되어 장려금 미지급",
        "penalty": "알리지 않고 근무하면 부정 훈련으로 훈련장려금 환수, 제적 등의 불이익",
    }


def get_schedule(on_date: Optional[str] = None, module: Optional[str] = None,
                 keyword: Optional[str] = None, limit: int = 10) -> dict:
    """교육 일정을 조회한다. 날짜(YYYY-MM-DD)·모듈명·키워드 중 하나로 찾는다. 일정은 반드시 조회해서 답한다."""
    rows = SCHEDULE
    if on_date:
        rows = [e for e in rows if e["date"] == on_date]
    if module:
        rows = [e for e in rows if e.get("module") and _norm(module) in _norm(e["module"])]
    if keyword:
        rows = [e for e in rows
                if _norm(keyword) in _norm(e.get("title") or "")
                or _norm(keyword) in _norm(e.get("module") or "")
                or _norm(keyword) in _norm(e.get("kind") or "")]
    out = rows[:limit]
    result = {"source": "교육 일정 캘린더", "count": len(rows), "events": out}
    if module or keyword:
        dates = [e["date"] for e in rows]
        if dates:
            result["date_range"] = {"first": min(dates), "last": max(dates)}
    if not rows:
        result["note"] = "해당 조건의 일정이 캘린더에 없습니다. 없다고 단정하지 말고 운영매니저 확인을 안내하십시오."
    return result


def get_rule_violation(topic: Optional[str] = None) -> dict:
    """경고(옐로카드)·제적(레드카드) 사유를 조회한다. 불이익 가능성을 묻는 문의에 부른다."""
    data = {
        "red_card": {
            "출석일수 부족": ["전체 훈련일수의 20% 이상 미출석",
                          "단위기간 훈련일수의 50% 이상 미출석"],
            "피해 행위": ["상해", "폭행", "절도", "성추행", "재물손괴"],
            "부정 출석": "거짓 기타 부정한 방법으로 출석 확인한 훈련생 및 대리 출석 확인 행위자",
            "시점": "사유 발생일의 다음 날에 제적",
        },
        "yellow_card": {
            "출석일수": "잦은 결석·지각·조퇴·외출로 출석률에 영향을 미쳐 학습 진행이 어려운 경우",
            "훈련 규칙 위반": "참여 규칙 각 항목 미준수",
            "부정 출석 및 무단 외출": [
                "수업에 참여하지 않고 출석 확인",
                "QR 코드를 저장해서 출석 확인",
                "QR 코드를 본인이 아닌 사람이 찍는 경우(대리출석)",
                "지정된 훈련 장소(자택 또는 사전승인 장소)가 아닌 곳에서 QR 촬영",
                "운송수단 탑승 중·보행 중 QR 촬영",
                "사전 승인되지 않은 외부 장소(카페 등)에서 QR 촬영",
                "사전 보고 없이 20분 이상 부재 시 무단 외출로 간주",
            ],
            "수강 태도 불량": ["운영진 지시사항 반복 불이행",
                          "마이크·스피커·카메라 정상 구동 유지 노력 부족",
                          "조별활동 시 타 훈련생 학습에 지장을 주는 태도·언행 반복"],
        },
        "escalation": "구두 경고 → 서면 경고 → 제적",
        "legal_basis": "국민내일배움카드 운영규정 제35조 1항·2항",
        "caution": "개인의 경고 누적 여부와 제적 여부는 안내봇에서 확인할 수 없습니다.",
    }
    if topic:
        for k in ("red", "제적", "레드"):
            if k in topic.lower():
                return {"source": "제적 가이드", "red_card": data["red_card"],
                        "legal_basis": data["legal_basis"]}
        for k in ("yellow", "경고", "옐로"):
            if k in topic.lower():
                return {"source": "제적 가이드", "yellow_card": data["yellow_card"],
                        "escalation": data["escalation"]}
    return {"source": "제적 가이드 · 훈련 참여 규칙", **data}


def get_tool_setup(tool: Optional[str] = None) -> dict:
    """LMS·디스코드·ZEP·출결 앱의 접속 주소와 닉네임 규칙을 조회한다."""
    tools = {
        "LMS": {"url": "https://learn.modulabs.co.kr/signin",
                "안내": "과정 신청 시 입력한 이메일로 로그인"},
        "디스코드": {"url": "[운영 공지의 디스코드 초대 링크 참조]",
                  "안내": "로그인 후 공지사항의 문제를 풀면 권한이 부여됩니다",
                  "닉네임": "AI에이전트1기/이름/지역"},
        "ZEP": {"닉네임": "AI에이전트1기/이름/지역"},
        "출결 앱": {"이름": "고용24 직업훈련 출결관리 앱",
                 "안내": "설치 후 자동 로그인을 설정하십시오"},
    }
    if tool:
        for k, v in tools.items():
            if _norm(tool) in _norm(k) or _norm(k) in _norm(tool):
                return {"source": "툴 세팅", "tool": k, "info": v}
    return {"source": "툴 세팅", "tools": tools,
            "nickname_rule": "AI에이전트1기/이름/지역"}


def escalate_to_manager(reason: str, context: Optional[dict] = None) -> dict:
    """운영매니저에게 넘긴다. 개인 기록 조회나 근거 없는 건은 여기로 보낸다."""
    return {"escalated": True, "reason": reason, "context": context or {},
            "channel": "디스코드 개인 DM",
            "message": "정확한 확인을 위해 운영매니저에게 디스코드 DM으로 문의해 주시기 바랍니다."}


TOOLS = {f.__name__: f for f in [
    search_leave_type, get_leave_detail, list_leave_types, get_leave_procedure,
    get_attendance_rule, get_unit_period, get_completion_criteria,
    get_stipend_policy, get_employment_docs, get_side_job_rule,
    get_schedule, get_rule_violation, get_tool_setup, escalate_to_manager,
]}
