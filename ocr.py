import pytesseract
from PIL import Image, ImageFilter, ImageOps

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def _preprocess(img: Image.Image) -> Image.Image:
    # Upscale 2x — Tesseract accuracy improves significantly at higher resolution
    w, h = img.size
    img = img.resize((w * 2, h * 2), Image.LANCZOS)
    img = img.convert('L')
    # Invert dark backgrounds so text becomes dark on white (Tesseract expects this)
    avg = sum(img.getdata()) / (img.width * img.height)
    if avg < 128:
        img = ImageOps.invert(img)
    img = img.point(lambda p: 255 if p > 140 else 0)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def run_ocr(img: Image.Image) -> str:
    processed = _preprocess(img)
    text = pytesseract.image_to_string(processed, config='--psm 6 --oem 3')
    return text.strip()
