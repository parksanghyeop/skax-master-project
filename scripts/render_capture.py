"""실행 로그(텍스트)를 터미널 모양 PNG로 렌더링한다 — 산출물 캡처 이미지 재생성용.

스크린샷 대신 실제 실행 로그 파일을 그대로 그린다: 캡처가 로그와 어긋날 일이 없고,
다시 실행하면 같은 절차로 갱신할 수 있다. 한글은 맑은 고딕, 코드는 Consolas(Windows 기본 글꼴).

사용:  python scripts/render_capture.py <로그 파일> <출력 PNG> [--title "제목"] [--width 110]
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_KO = r"C:\Windows\Fonts\malgun.ttf"
FONT_MONO = r"C:\Windows\Fonts\consola.ttf"
FONT_SIZE = 22
LINE_HEIGHT = 32
PADDING = 28
BG = (30, 30, 30)
FG = (220, 220, 220)
TITLE_BG = (50, 50, 50)
DIM = (140, 140, 140)
ACCENT = (120, 200, 255)


def _is_ascii(ch: str) -> bool:
    return ord(ch) < 0x2E80 and ch not in "①②③④⑤⑥⑦⑧⑨⑩┌┐└┘│─→←·…"


def _draw_line(draw, x, y, text, mono, ko, color):
    """글자 단위로 글꼴을 바꿔 가며 그린다 — 한글·기호는 맑은 고딕, 나머지는 Consolas.

    anchor="ls"(왼쪽·기준선): 두 글꼴의 위아래 여백이 달라 기본 앵커로 그리면 한 줄 안에서
    글자가 위아래로 들쭉날쭉해진다. 기준선을 공유하면 나란히 놓인다.
    """
    baseline = y + FONT_SIZE
    for ch in text:
        font = mono if _is_ascii(ch) else ko
        draw.text((x, baseline), ch, font=font, fill=color, anchor="ls")
        x += draw.textlength(ch, font=font)


def _wrap(line: str, max_px: float, mono, ko) -> list[str]:
    """화면 너비를 넘는 줄은 들여쓰기를 유지한 채 이어 그린다 — 잘려서 안 보이는 것보다 낫다."""
    indent = len(line) - len(line.lstrip(" "))
    pieces, current, width = [], "", 0.0
    for ch in line:
        w = (mono if _is_ascii(ch) else ko).getlength(ch)
        if width + w > max_px and current.strip():
            pieces.append(current)
            current, width = " " * (indent + 4), (indent + 4) * mono.getlength(" ")
        current += ch
        width += w
    pieces.append(current)
    return pieces


def render(log_path: Path, out_path: Path, title: str, width_chars: int) -> None:
    mono = ImageFont.truetype(FONT_MONO, FONT_SIZE)
    ko = ImageFont.truetype(FONT_KO, FONT_SIZE)
    char_w = mono.getlength("M")
    width = int(PADDING * 2 + char_w * width_chars)
    lines = [
        piece
        for raw in log_path.read_text(encoding="utf-8").splitlines()
        for piece in _wrap(raw, width - PADDING * 2, mono, ko)
    ]
    title_h = LINE_HEIGHT + 12 if title else 0
    height = int(PADDING * 2 + title_h + LINE_HEIGHT * len(lines))
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    y = PADDING
    if title:
        draw.rectangle([0, 0, width, title_h + PADDING // 2], fill=TITLE_BG)
        _draw_line(draw, PADDING, 8, f"$ {title}", mono, ko, ACCENT)
        y += title_h
    for line in lines:
        color = DIM if line.strip().startswith("[") and "초]" in line else FG
        if line.strip().startswith("결과 상태:") or "결과 상태:" in line:
            color = ACCENT
        _draw_line(draw, PADDING, y, line, mono, ko, color)
        y += LINE_HEIGHT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"{out_path} ({width}x{height}, {len(lines)}줄)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("out")
    ap.add_argument("--title", default="")
    ap.add_argument("--width", type=int, default=110)
    a = ap.parse_args()
    render(Path(a.log), Path(a.out), a.title, a.width)
