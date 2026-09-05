"""시크릿 가림 — 화면·로그·오류 문구에 API 키가 새지 않게 하는 마지막 방어선 (v4 6.6, 3단계 A-3).

게이트웨이 클라이언트는 키를 오류 문구에 애초에 넣지 않는다(구조적 방어). 이 함수는 그 위에
얹는 2차 방어다 — 어떤 경로로든 키 값이 문자열에 섞였을 때 CLI가 출력 직전에 가린다.
층: llm — 어떤 이름의 환경변수가 키인지 아는 곳은 여기뿐이다.
"""

import os
import re

from cta.llm.gateway import ENV_API_KEY

MASK = "****"

# 게이트웨이 키의 모양(접두어 atl-). 환경변수에 키가 없을 때도(다른 계정의 키가 로그에 섞인 경우)
# 모양으로 잡는다. 6자 이상만 — "atl-"로 시작하는 평범한 단어를 오탐하지 않게.
_KEY_SHAPE = re.compile(r"atl-[A-Za-z0-9_\-]{6,}")

# 이보다 짧은 값은 가려도 의미가 없고, 빈 값·한 글자를 치환하면 문장이 망가진다
_MIN_SECRET_LEN = 4


def mask_secrets(text: str) -> str:
    """text 안의 API 키를 ****로 바꾼다 — 환경변수의 실제 값과 키 모양 둘 다.

    입력: 아무 문자열(오류 문구·로그 줄). 출력: 키가 가려진 문자열. 키가 없으면 그대로.
    """
    secret = os.environ.get(ENV_API_KEY, "")
    if len(secret) >= _MIN_SECRET_LEN:
        text = text.replace(secret, MASK)
    return _KEY_SHAPE.sub(f"atl-{MASK}", text)
