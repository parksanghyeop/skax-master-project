"""adapters 계층 — core 포트의 구체 구현.

실제 언어·빌드 도구를 아는 코드는 전부 여기에 산다. core → adapters 방향의
import는 금지(tests/test_layering.py가 검사). PoC M0에서는 Java·Docker 없이
파이프라인을 돌리기 위한 Fake 구현만 있고, 실물 Java 어댑터는 M1에서 추가한다.
"""
