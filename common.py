# -*- coding: utf-8 -*-
"""여러 모듈이 함께 쓰는 잡동사니."""
import sys
from concurrent.futures import ThreadPoolExecutor

from config import WORKERS


def pmap(fn, items, workers=WORKERS):
    """여러 건을 동시에 호출한다. 결과 순서는 입력 순서와 같다.

    LLM 호출은 대부분 응답을 기다리는 시간이라 동시에 보내면 거의 그 배수만큼 빨라진다.
    workers 를 너무 올리면 요청 한도(rate limit)에 걸린다.
    """
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def enable_utf8():
    """콘솔 출력을 UTF-8 로 맞춘다.

    윈도우 기본 콘솔 코덱(cp949)은 '↳', '──', '✅' 같은 글자를 못 찍고 UnicodeEncodeError 로
    죽는다. 실행 진입점에서 한 번 불러 두면 된다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def show_graph(compiled):
    """그래프 구조를 mermaid 로 출력한다."""
    print(compiled.get_graph().draw_mermaid())
