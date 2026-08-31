from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


DPI = 200
FONT_PATH = Path(__file__).parent / "assets" / "NotoSansTC-Subset.ttf"
INK = "#243028"
MUTED = "#66736A"
GREEN = "#356B48"
PALE_GREEN = "#EDF5EF"
PALE_BLUE = "#EAF2F7"
LINE = "#C9D6CC"
WHITE = "#FFFFFF"


def point_size(points: float) -> int:
    return max(1, round(points * DPI / 72))


def font(points: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), point_size(points))


def page_image(orientation: str = "portrait") -> Image.Image:
    width, height = (1654, 2339) if orientation == "portrait" else (2339, 1654)
    return Image.new("RGB", (width, height), WHITE)


def text_width(draw: ImageDraw.ImageDraw, value: str, text_font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), value or " ", font=text_font)
    return box[2] - box[0]


def wrap_text(draw: ImageDraw.ImageDraw, value: object, text_font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    text = "" if value is None else str(value)
    if not text:
        return [""]
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for character in paragraph:
            candidate = current + character
            if current and text_width(draw, candidate, text_font) > max_width:
                lines.append(current)
                current = character
            else:
                current = candidate
        lines.append(current)
    return lines or [""]


def draw_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    text_font: ImageFont.FreeTypeFont,
    fill: str = INK,
    line_gap: int = 8,
) -> int:
    x, y = xy
    line_height = text_font.getbbox("國Ag")[3] - text_font.getbbox("國Ag")[1] + line_gap
    for line in lines:
        draw.text((x, y), line, font=text_font, fill=fill)
        y += line_height
    return y


def rounded_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str = WHITE, outline: str = LINE, radius: int = 18) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def images_to_pdf(images: list[Image.Image], orientation: str = "portrait") -> bytes:
    if not images:
        images = [page_image(orientation)]
    stream = BytesIO()
    page_size = A4 if orientation == "portrait" else landscape(A4)
    pdf = canvas.Canvas(stream, pagesize=page_size, pageCompression=1)
    for image in images:
        payload = BytesIO()
        image.save(payload, format="PNG", optimize=True, dpi=(DPI, DPI))
        payload.seek(0)
        pdf.drawImage(ImageReader(payload), 0, 0, width=page_size[0], height=page_size[1], preserveAspectRatio=False)
        pdf.showPage()
    pdf.save()
    return stream.getvalue()
