import os
import io
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from deep_translator import GoogleTranslator
from docx import Document
from pdf2docx import Converter

app = FastAPI(title="Afrikaans Document Translator", version="2.0")

MAX_SIZE = 100 * 1024 * 1024  # 100 MB
templates = Jinja2Templates(directory="templates")
ALLOWED = {".txt", ".pdf", ".docx"}


def chunk_text(text: str, max_chars: int = 4500) -> list[str]:
    """Split long text into safe chunks for Google Translate."""
    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind(". ", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[: split_at + 1].strip())
        text = text[split_at + 1 :].strip()
    return [c for c in chunks if c]


def translate_text(text: str) -> str:
    """Translate any language → Afrikaans."""
    if not text or not text.strip():
        return text
    translator = GoogleTranslator(source="auto", target="af")
    chunks = chunk_text(text)
    parts = []
    for chunk in chunks:
        try:
            result = translator.translate(chunk)
            parts.append(result if result else chunk)
        except Exception:
            parts.append(chunk)  # keep original on failure
    return "\n\n".join(parts)


def translate_paragraph(paragraph):
    """Translate a single paragraph while trying to keep run formatting."""
    if not paragraph.text.strip():
        return

    full_text = paragraph.text
    translated = translate_text(full_text)

    # Simple strategy that works well for most documents:
    # Clear existing runs and put the translated text in the first run
    # (keeps paragraph style, and most basic formatting)
    if paragraph.runs:
        # Keep the first run's formatting
        first_run = paragraph.runs[0]
        first_run.text = translated
        # Remove the rest of the runs
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(translated)


def translate_table(table):
    """Translate all cells in a table."""
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                translate_paragraph(paragraph)


def translate_docx_in_place(docx_bytes: bytes) -> bytes:
    """
    Open a DOCX, translate all text in place (paragraphs + tables),
    keep images, styles, headers, footers, layout as much as possible.
    """
    doc = Document(io.BytesIO(docx_bytes))

    # Body paragraphs
    for paragraph in doc.paragraphs:
        translate_paragraph(paragraph)

    # Tables
    for table in doc.tables:
        translate_table(table)

    # Headers & Footers
    for section in doc.sections:
        for header in [section.header, section.first_page_header]:
            if header:
                for paragraph in header.paragraphs:
                    translate_paragraph(paragraph)
                for table in header.tables:
                    translate_table(table)

        for footer in [section.footer, section.first_page_footer]:
            if footer:
                for paragraph in footer.paragraphs:
                    translate_paragraph(paragraph)
                for table in footer.tables:
                    translate_table(table)

    # Save to bytes
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def pdf_to_docx_bytes(pdf_bytes: bytes) -> bytes:
    """Convert PDF to DOCX using pdf2docx (preserves layout & images reasonably well)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf_path = tmp_pdf.name

    tmp_docx_path = tmp_pdf_path.replace(".pdf", ".docx")

    try:
        cv = Converter(tmp_pdf_path)
        cv.convert(tmp_docx_path, start=0, end=None)
        cv.close()

        with open(tmp_docx_path, "rb") as f:
            docx_bytes = f.read()
        return docx_bytes
    finally:
        for path in (tmp_pdf_path, tmp_docx_path):
            try:
                os.unlink(path)
            except Exception:
                pass


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/translate")
async def translate_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported type. Allowed: {', '.join(ALLOWED)}")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, f"File too large. Maximum is {MAX_SIZE // (1024*1024)} MB")

    try:
        if ext == ".txt":
            text = content.decode("utf-8", errors="replace")
            translated = translate_text(text)
            # Return as simple DOCX for consistency
            doc = Document()
            doc.add_paragraph(translated)
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            output_bytes = buffer.getvalue()
            out_name = f"afrikaans_{Path(file.filename).stem}.docx"

        elif ext == ".docx":
            output_bytes = translate_docx_in_place(content)
            out_name = f"afrikaans_{Path(file.filename).stem}.docx"

        elif ext == ".pdf":
            # Convert PDF → DOCX (keeps layout & images much better)
            docx_bytes = pdf_to_docx_bytes(content)
            # Then translate the DOCX in place
            output_bytes = translate_docx_in_place(docx_bytes)
            out_name = f"afrikaans_{Path(file.filename).stem}.docx"

        else:
            raise HTTPException(400, "Unsupported file type")

    except Exception as e:
        raise HTTPException(500, f"Translation failed: {str(e)}")

    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "target": "Afrikaans (af)", "version": "2.0 - format preserving"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
