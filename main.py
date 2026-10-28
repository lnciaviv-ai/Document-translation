import os
import io
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from deep_translator import GoogleTranslator
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_COLOR_INDEX
from pdf2docx import Converter

app = FastAPI(title="Afrikaans Document Translator", version="3.0")

MAX_SIZE = 100 * 1024 * 1024  # 100 MB
templates = Jinja2Templates(directory="templates")
ALLOWED = {".txt", ".pdf", ".docx"}


def chunk_text(text: str, max_chars: int = 4000) -> list[str]:
    """Split long text into safe chunks for Google Translate."""
    if not text or not text.strip():
        return []
    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        # Prefer natural breaks
        split_at = text.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind(". ", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind(" ", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[: split_at + 1].strip())
        text = text[split_at + 1 :].strip()
    return [c for c in chunks if c]


def translate_text(text: str) -> str:
    """Translate any language → Afrikaans with robust chunking."""
    if not text or not text.strip():
        return text

    # Skip pure numbers / very short non-text
    if text.strip().isdigit() or len(text.strip()) < 2:
        return text

    translator = GoogleTranslator(source="auto", target="af")
    chunks = chunk_text(text)
    parts = []
    for chunk in chunks:
        try:
            result = translator.translate(chunk)
            parts.append(result if result else chunk)
        except Exception:
            parts.append(chunk)
    return "\n\n".join(parts)


def translate_paragraph_bilingual(paragraph):
    """
    Best practical approach:
    - Keep original text
    - Add Afrikaans translation underneath in a slightly different style
    This is more reliable than pure replacement when text length changes a lot.
    """
    original = paragraph.text.strip()
    if not original:
        return

    translated = translate_text(original)
    if not translated or translated == original:
        return

    # Clear existing content carefully
    if paragraph.runs:
        # Keep first run formatting for original
        first_run = paragraph.runs[0]
        first_run.text = original
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(original)

    # Add translation as a new paragraph after this one (handled by caller for simplicity)
    # For true in-place we append to the same paragraph with a line break
    paragraph.add_run("\n")
    trans_run = paragraph.add_run(translated)
    try:
        trans_run.font.color.rgb = RGBColor(0x1A, 0x73, 0xE8)  # Google-ish blue
        trans_run.italic = True
    except Exception:
        pass


def translate_paragraph_replace(paragraph):
    """Pure replacement – closer to Google Docs 'replace' behaviour."""
    original = paragraph.text.strip()
    if not original:
        return

    translated = translate_text(original)
    if not translated:
        return

    if paragraph.runs:
        paragraph.runs[0].text = translated
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(translated)


def translate_table(table, mode: str = "bilingual"):
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                if mode == "bilingual":
                    translate_paragraph_bilingual(paragraph)
                else:
                    translate_paragraph_replace(paragraph)


def translate_docx(docx_bytes: bytes, mode: str = "bilingual") -> bytes:
    """
    Translate a DOCX while preserving structure, images, tables, headers, footers.
    mode = "bilingual" (recommended) or "replace"
    """
    doc = Document(io.BytesIO(docx_bytes))

    # Body
    for paragraph in doc.paragraphs:
        if mode == "bilingual":
            translate_paragraph_bilingual(paragraph)
        else:
            translate_paragraph_replace(paragraph)

    # Tables
    for table in doc.tables:
        translate_table(table, mode)

    # Headers & Footers
    for section in doc.sections:
        for part in [section.header, section.first_page_header,
                     section.footer, section.first_page_footer]:
            if part is None:
                continue
            for paragraph in part.paragraphs:
                if mode == "bilingual":
                    translate_paragraph_bilingual(paragraph)
                else:
                    translate_paragraph_replace(paragraph)
            for table in part.tables:
                translate_table(table, mode)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def pdf_to_docx_bytes(pdf_bytes: bytes) -> bytes:
    """Convert PDF → DOCX while preserving layout and images as well as possible."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf_path = tmp_pdf.name

    tmp_docx_path = tmp_pdf_path + ".docx"

    try:
        cv = Converter(tmp_pdf_path)
        cv.convert(tmp_docx_path, start=0, end=None)
        cv.close()
        with open(tmp_docx_path, "rb") as f:
            return f.read()
    finally:
        for p in (tmp_pdf_path, tmp_docx_path):
            try:
                os.unlink(p)
            except Exception:
                pass


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/translate")
async def translate_document(
    file: UploadFile = File(...),
    mode: str = Form("bilingual")  # "bilingual" or "replace"
):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported type. Allowed: {', '.join(sorted(ALLOWED))}")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, f"File too large. Maximum allowed is {MAX_SIZE // (1024*1024)} MB")

    if mode not in ("bilingual", "replace"):
        mode = "bilingual"

    try:
        if ext == ".txt":
            text = content.decode("utf-8", errors="replace")
            translated = translate_text(text)
            doc = Document()
            if mode == "bilingual":
                p = doc.add_paragraph(text)
                p.add_run("\n")
                tr = p.add_run(translated)
                try:
                    tr.font.color.rgb = RGBColor(0x1A, 0x73, 0xE8)
                    tr.italic = True
                except Exception:
                    pass
            else:
                doc.add_paragraph(translated)
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            output_bytes = buffer.getvalue()

        elif ext == ".docx":
            output_bytes = translate_docx(content, mode=mode)

        elif ext == ".pdf":
            # Best available: PDF → DOCX (keeps layout + images) → translate
            docx_bytes = pdf_to_docx_bytes(content)
            output_bytes = translate_docx(docx_bytes, mode=mode)

        else:
            raise HTTPException(400, "Unsupported file type")

    except Exception as e:
        raise HTTPException(500, f"Translation failed: {str(e)}")

    out_name = f"afrikaans_{Path(file.filename).stem}.docx"
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "target": "Afrikaans (af)",
        "version": "3.0",
        "modes": ["bilingual", "replace"],
        "max_upload_mb": 100
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
