"""mermaid(.mmd) 다이어그램을 PNG로 렌더링한다 — 산출물 워크플로우 그림 재생성용.

외부 렌더 서비스에 그림 내용을 보내지 않고, 로컬 Chrome(헤드리스)으로 mermaid.js를
실행해 화면을 찍은 뒤 여백을 잘라낸다. mermaid.js 자체만 CDN에서 받는다.

사용:  python scripts/render_diagram.py <입력.mmd> <출력.png> [--width 1568] [--scale 2]
전제:  Chrome 설치(기본 경로) + 인터넷(mermaid.js 1회 다운로드)
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
# 그림이 잘리지 않도록 넉넉히 잡고, 렌더 후 흰 여백을 잘라낸다
CANVAS_HEIGHT = 6000
MARGIN = 16  # 자른 뒤 남길 여백(px)

_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>
  body {{ margin: 0; background: #fff; font-family: "Malgun Gothic", "Segoe UI", sans-serif; }}
  #d {{ width: {width}px; padding: 8px; }}
</style></head><body>
<pre id="d" class="mermaid">{code}</pre>
<script src="{js}"></script>
<script>
  // useMaxWidth:false — SVG를 컨테이너 폭에 맞춰 늘리지 않는다
  //   (늘리면 글자가 흐려지고 줄바꿈이 촘촘해진다).
  // wrappingWidth — 노드 글자의 줄바꿈 폭. 기본 200은 한글 문장이 너무 잘게 나뉜다.
  mermaid.initialize({{
    startOnLoad: false, theme: "default",
    fontFamily: "Malgun Gothic, Segoe UI, sans-serif",
    flowchart: {{ useMaxWidth: false, htmlLabels: true, wrappingWidth: 320 }}
  }});
  mermaid.run({{ nodes: [document.getElementById("d")] }})
    .then(() => {{ document.title = "done"; }});
</script></body></html>"""


def _escape(code: str) -> str:
    return code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _autocrop(image: Image.Image) -> Image.Image:
    """흰 배경과 다른 부분의 경계 상자로 잘라내고 MARGIN만 남긴다."""
    rgb = image.convert("RGB")
    bg = Image.new("RGB", rgb.size, (255, 255, 255))
    box = ImageChops.difference(rgb, bg).getbbox()
    if not box:
        return rgb
    left, top, right, bottom = box
    return rgb.crop(
        (
            max(0, left - MARGIN),
            max(0, top - MARGIN),
            min(rgb.width, right + MARGIN),
            min(rgb.height, bottom + MARGIN),
        )
    )


def render(mmd_path: Path, out_path: Path, width: int, scale: int) -> None:
    code = mmd_path.read_text(encoding="utf-8")
    # mermaid는 <pre> 안의 &lt; 같은 엔티티를 그대로 텍스트로 쓰므로 이스케이프 후 넣는다
    html = _HTML.format(width=width, code=_escape(code), js=MERMAID_JS)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "diagram.html"
        page.write_text(html, encoding="utf-8")
        shot = Path(tmp) / "shot.png"
        subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--force-device-scale-factor={scale}",
                f"--window-size={width + 16},{CANVAS_HEIGHT}",
                "--virtual-time-budget=8000",  # mermaid.js 다운로드·렌더 대기(가상 시간)
                f"--screenshot={shot}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        image = Image.open(shot)
        image.load()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _autocrop(image).save(out_path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mmd")
    p.add_argument("out")
    p.add_argument(
        "--width", type=int, default=1568, help="CSS 픽셀 너비(기존 산출물과 동일 기본값)"
    )
    p.add_argument("--scale", type=int, default=1, help="배율(2면 고해상도)")
    a = p.parse_args()
    render(Path(a.mmd), Path(a.out), a.width, a.scale)
    print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
