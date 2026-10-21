"""Short-lived, local-only PDF text extraction process. No network or OCR."""
import hashlib
from io import BytesIO
import json
import logging
import sys

MAX_BYTES = 8_000_000


def extract(data):
    import pypdf
    from pypdf import PdfReader
    if len(data) > MAX_BYTES or not data.startswith(b"%PDF-"):
        raise ValueError("PDF 文件无效或超过 8 MB。")
    reader = PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted:
        raise ValueError("暂不支持加密 PDF。请提供你有权读取的未加密文件，或手动添加笔记。")
    if not 1 <= len(reader.pages) <= 80:
        raise ValueError("暂支持 1—80 页的 PDF。请选用较短的论文文件，或手动添加笔记。")
    pages, total = [], 0
    for index, page in enumerate(reader.pages, 1):
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > 4_000_000:
            raise ValueError(f"第 {index} 页内容过于复杂，请手动添加相关笔记。")
        value = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n")
        total += len(value)
        if len(value) > 100_000 or total > 500_000:
            raise ValueError("提取文字超过限制，未保存截断内容。请使用较短的文件。")
        pages.append({"page": index, "text": value,
                      "text_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()})
    if not any(p["text"].strip() for p in pages):
        raise ValueError("没有提取到可选择的文字。可能是扫描件；当前不支持 OCR，可手动添加阅读笔记。")
    return {"extractor": "pypdf/" + pypdf.__version__, "page_count": len(pages), "pages": pages,
            "notice": "按 PDF 文件页序提取，可能与印刷页码不同。分栏、公式、表格和 OCR 文字可能有误，请对照原文件核对。"}


def main():
    logging.disable(logging.CRITICAL)
    try:
        result = extract(sys.stdin.buffer.read(MAX_BYTES + 1))
        status = 0
    except ValueError as exc:
        result, status = {"error": str(exc)}, 1
    except Exception:
        result, status = {"error": "无法读取这个 PDF。请检查文件，或手动添加阅读笔记。"}, 1
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
