import logging
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# ---------- Logging Setup ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

# File extensions we care about
TARGET_EXTS = {".py"}

# ---------- Root PDF folder (1 place for all modules) ----------
PROJECT_ROOT = Path(__file__).resolve().parent  # thư mục gốc chứa script này
PDF_ROOT = PROJECT_ROOT / "pdfs"
PDF_ROOT.mkdir(exist_ok=True)

def file_to_pdf(src_path: Path, dst_path: Path):
    """Convert one source file to a PDF."""
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(dst_path), pagesize=A4)

    with src_path.open("r", encoding="utf-8", errors="ignore") as f:
        code = f.read()

    elements = [
        Paragraph(f"Source: {src_path}", styles["Title"]),
        Preformatted(code, styles["Code"]),
    ]
    doc.build(elements)
    logging.info("Created PDF: %s", dst_path)

def convert_all(base_folder: str):
    """
    Recursively find all target files under base_folder
    and save their PDFs to PROJECT_ROOT/pdfs/<module>__<filename>.pdf
    """
    base = Path(base_folder).resolve()
    files = [f for f in base.rglob("*") if f.suffix.lower() in TARGET_EXTS]
    logging.info("Found %d target files in %s", len(files), base)

    for i, src_file in enumerate(files, start=1):
        module_name = base.name   # tên module ví dụ: ms1_ingestion
        filename = src_file.stem  # không có .py
        pdf_name = f"{module_name}__{filename}.pdf"

        target_pdf = PDF_ROOT / pdf_name
        target_pdf.parent.mkdir(parents=True, exist_ok=True)

        logging.info("[%d/%d] Converting %s -> %s",
                     i, len(files), src_file, target_pdf.name)

        file_to_pdf(src_file, target_pdf)

    logging.info("✅ Conversion complete. PDFs stored in: %s", PDF_ROOT)

if __name__ == "__main__":
    file_names = [
        "api", "core", "utils", "concurrent_storage"
    ]
    for name in file_names:
        convert_all(f"C:/Users/Admin/Desktop/CMC/ms1_emailIngestion/{name}")