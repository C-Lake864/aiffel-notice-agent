# -*- coding: utf-8 -*-
"""한곳에 모아 둔 설정. 여기 값만 바꿔도 동작이 달라진다.

- MODEL        : 라우팅용. 출력이 짧고 호출이 많다.
- ANSWER_MODEL : 답변 생성용. 매뉴얼 컨텍스트가 붙어 입력이 길다.
- CONF_THRESHOLD: 이 값 미만이면 운영매니저에게 넘긴다.
- MAX_TOOL_TURNS: 도구 호출 루프 상한. 3이면 조회 두 번에 답변 한 번이 빠듯하다.
"""
import os
from pathlib import Path

BASE = Path(__file__).parent / "data"

MODEL = os.environ.get("AIF_MODEL", "gpt-5.6-luna")
ANSWER_MODEL = os.environ.get("AIF_ANSWER_MODEL", "gpt-5.6-terra")

CONF_THRESHOLD = 0.5          # 라우팅 확신도 임계값
MAX_TOOL_TURNS = 4            # 도구 호출 루프 상한
GUARDRAIL_RETRY = 1           # 가드레일 위반 시 재생성 횟수
WORKERS = 12                  # 동시 호출 수. 요청 한도에 걸리면 낮춘다

# 되묻기와 양립하는 도구들. '답을 확정하는' 도구가 아니라, 사유를 좁히거나
# (search_leave_type) 되물을 때 어차피 함께 안내해야 하는 고정 절차를 가져오는
# (get_leave_procedure) 도구다.
#
# 이 구분이 없으면 "조회를 했으니 답한 것"으로 보게 되어, 실제로는 되물었는데
# action=ANSWER 로 기록된다. 에이전트와 채점기가 같은 기준을 써야 하므로 여기 둔다.
NON_COMMITTING_TOOLS = {"search_leave_type", "get_leave_procedure"}

ROUTES = ["ATTENDANCE", "LEAVE", "STIPEND", "RULES", "SCHEDULE", "OTHER"]
LABELS5 = ["ATTENDANCE", "LEAVE", "STIPEND", "RULES", "SCHEDULE"]

ROUTE_KO = {
    "ATTENDANCE": "출결",
    "LEAVE": "공가·휴가",
    "STIPEND": "장려금·고용형태",
    "RULES": "규칙·제적",
    "SCHEDULE": "일정·커리큘럼",
    "OTHER": "응대 범위 밖",
}

DATA_FILES = ("notice_manual.md", "leave_types.json", "schedule.json",
              "unit_periods.json", "employment_docs.json",
              "routing_eval.csv", "answer_goldenset.json",
              "multiturn_goldenset.json")


def check_data():
    """데이터가 다 있는지 확인한다. 없으면 무엇이 없는지 알려 준다."""
    missing = [f for f in DATA_FILES if not (BASE / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"data/ 에 다음 파일이 없습니다: {missing}\n"
            f"저장소를 통째로 내려받았는지 확인하세요.")
    return True
