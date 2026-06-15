#!/usr/bin/env python3
"""
PDF to Markdown Converter with Smart OCR Fallback
==================================================
Chuyển đổi PDF sang Markdown, tự động bật OCR nếu text bị lỗi font.
Yêu cầu: pymupdf4llm (pip install pymupdf4llm) và Tesseract OCR (cài riêng).

Cài đặt Tesseract:
- Windows: https://github.com/UB-Mannheim/tesseract/wiki (nhớ chọn "Add to PATH")
- macOS: brew install tesseract
- Linux: sudo apt install tesseract-ocr

Sử dụng:
    python pdf_to_md_smart.py <input_dir> [-o output] [--force-ocr] [--no-ocr]
"""

import sys
import argparse
import re
import subprocess
from pathlib import Path

try:
    import pymupdf4llm
except ImportError:
    print("Lỗi: Thiếu pymupdf4llm. Hãy chạy: pip install pymupdf4llm")
    sys.exit(1)

def is_tesseract_available() -> bool:
    """Kiểm tra xem Tesseract có trong PATH không."""
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def is_text_corrupted(text: str) -> bool:
    """Phát hiện text bị lỗi font qua các mẫu đặc trưng."""
    if not text or len(text) < 50:
        return True  # Quá ngắn, có thể bị lỗi
    # Các pattern lỗi từ ảnh bạn cung cấp
    patterns = [
        r'banri,ers',      # barriers bị sai
        r'ent●',           # ký tự lạ
        r'Mon I \.\s*opo y',  # Monopoly bị tách
        r'[a-z]\s+[a-z]\s+[a-z]',  # khoảng trắng giữa chữ cái
        r'[A-Z]\s+\.\s+[A-Z]',     # "C . o m p"
        r'[a-z],[a-z]',    # dấu phẩy giữa chữ
        r'\d+[a-z]',       # số liền chữ
        r'[a-z]\d+[a-z]',  # chữ-số-chữ
    ]
    for pat in patterns:
        if re.search(pat, text):
            return True
    # Thêm kiểm tra tỷ lệ ký tự lạ
    special_chars = sum(1 for c in text if ord(c) > 127 or c in '●■▲▼')
    if special_chars > 3:
        return True
    return False

def pdf_to_markdown(pdf_path: Path, output_path: Path, force_ocr: bool = False, no_ocr: bool = False) -> None:
    """Chuyển PDF sang Markdown, tự động quyết định có dùng OCR hay không."""
    use_ocr = False
    if no_ocr:
        use_ocr = False
    elif force_ocr:
        use_ocr = True
    else:
        # Thử đọc text thô, kiểm tra lỗi
        try:
            sample_md = pymupdf4llm.to_markdown(str(pdf_path))
            if is_text_corrupted(sample_md):
                print(f"  ⚠ Phát hiện text lỗi trong {pdf_path.name}, cần OCR.")
                use_ocr = True
            else:
                use_ocr = False
        except Exception:
            use_ocr = True

    if use_ocr:
        if not is_tesseract_available():
            print(f"  ❌ Cần OCR nhưng Tesseract chưa được cài đặt hoặc không trong PATH.")
            print(f"     Hãy cài Tesseract theo hướng dẫn: https://github.com/UB-Mannheim/tesseract/wiki")
            print(f"     Sau đó chạy lại. Hiện tại sẽ xuất text thô (có thể bị lỗi).")
            use_ocr = False  # fallback

    try:
        # Gọi pymupdf4llm với hoặc không OCR
        md_text = pymupdf4llm.to_markdown(str(pdf_path), ocr=use_ocr)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_text, encoding='utf-8')
        ocr_status = " (OCR)" if use_ocr else ""
        print(f"✓ Đã chuyển: {pdf_path.name} -> {output_path}{ocr_status}")
    except Exception as e:
        print(f"❌ Lỗi xử lý {pdf_path.name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="PDF to Markdown với tự động phát hiện lỗi font và OCR")
    parser.add_argument("input_dir", help="Thư mục chứa file PDF")
    parser.add_argument("-o", "--output", default="pdf_markdown", help="Thư mục đầu ra (mặc định: pdf_markdown)")
    parser.add_argument("--no-recursive", action="store_true", help="Chỉ quét thư mục hiện tại, không đệ quy")
    parser.add_argument("--force-ocr", action="store_true", help="Ép buộc dùng OCR cho mọi file (chậm hơn)")
    parser.add_argument("--no-ocr", action="store_true", help="Tắt hoàn toàn OCR, chỉ dùng text thô")
    args = parser.parse_args()

    input_path = Path(args.input_dir)
    if not input_path.exists():
        print(f"Lỗi: Thư mục '{input_path}' không tồn tại")
        sys.exit(1)

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    pattern = "**/*.pdf" if not args.no_recursive else "*.pdf"
    pdf_files = list(input_path.glob(pattern))

    if not pdf_files:
        print("Không tìm thấy file PDF nào.")
        return

    print(f"Tìm thấy {len(pdf_files)} file PDF.")
    for pdf_file in pdf_files:
        rel_path = pdf_file.relative_to(input_path)
        out_md = output_root / rel_path.with_suffix(".md")
        pdf_to_markdown(pdf_file, out_md, force_ocr=args.force_ocr, no_ocr=args.no_ocr)

    print("✅ Hoàn thành!")

if __name__ == "__main__":
    main()