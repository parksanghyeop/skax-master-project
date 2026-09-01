"""도구 반환 문자열의 길이 상한 처리.

모든 도구는 예외 대신 "모델이 읽을 문자열 + 길이 상한"을 반환한다(phase1 스킬 규칙).
상한 로직은 언어와 무관한 공통 관심사라 core에 둔다. 도구 골격(M3)이 이 함수를 쓴다.
"""

# 도구 반환 상한. v4 설계 원문이 리포에 없어 임시로 정한 값 —
# 근거: 실패 로그 수십 줄 + 소스 조각이 들어가는 크기. poc-findings '설계 수정 필요' 참조.
TOOL_OUTPUT_MAX_CHARS = 4000

# 잘렸다는 사실을 모델이 알아야 "더 좁혀서 다시 조회"를 판단할 수 있다.
_CLIP_NOTICE = "\n...[잘림: 전체 {total}자 중 앞 {kept}자만 표시]"


def clip(text: str, limit: int = TOOL_OUTPUT_MAX_CHARS) -> str:
    """text가 limit자를 넘으면 앞부분만 남기고 잘림 표식을 붙인다.

    입력: text 원문, limit 최대 길이(표식 포함).
    출력: limit 이하 길이의 문자열. 원문이 limit 이하면 그대로 반환.
    """
    if len(text) <= limit:
        return text
    notice = _CLIP_NOTICE.format(total=len(text), kept=0)
    kept = max(0, limit - len(notice))
    # 왜 두 번 만드나: kept 자릿수에 따라 표식 길이가 변해서, 자리 계산 후 다시 채운다.
    notice = _CLIP_NOTICE.format(total=len(text), kept=kept)
    kept = max(0, limit - len(notice))
    return text[:kept] + notice
