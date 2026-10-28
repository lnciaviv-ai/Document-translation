import os
import io
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from deep_translator import GoogleTranslator
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Pt

app = FastAPI(title="Afrikaans Document Translator", version="1.0")

# Max upload size: 100 MB
MAX_SIZE = 100 * 1024 * 1024

templates = Jinja2Templates(directory="templates")

# Allowed extensions
ALLOWED = {".txt", ".pdf", ".docx"}


def chunk_text(text: str, max_chars: int = 4500) -> list[str]:
    """Split text into safe chunks for Google Translate."""
    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        # Prefer splitting on paragraph or sentence
        split_at = text.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind(". ", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[: split_at + 1].strip())
        text = text[split_at + 1 :].strip()
    return [c for c in chunks if c]


def translate_to_afrikaans(text: str) -> str:
    """Translate any language → Afrikaans with chunking + auto-detect."""
    if not text or not text.strip():
        return ""
    translator = GoogleTranslator(source="auto", target="af")
    chunks = chunk_text(text)
    translated_parts = []
    for chunk in chunks:
        try:
            result = translator.translate(chunk)
            translated_parts.append(result or chunk)
        except Exception as e:
            # Fallback: keep original on failure
            translated_parts.append(f"[Translation error: {str(e)[:80]}]\n{chunk}")
    return "\n\n".join(translated_parts)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    texts = []
    for page in doc:
        texts.append(page.get_text("text"))
    doc.close()
    return "\n\n".join(texts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])


def create_translated_docx(original_text: str, translated: str) -> bytes:
    """Create a simple bilingual-style DOCX (original + Afrikaans)."""
    doc = Document()
    doc.add_heading("Oorspronklike teks / Original", level=1)
    # Limit original text length to keep file reasonable
    preview = original_text[:30000] + ("..." if len(original_text) > 30000 else "")
    doc.add_paragraph(preview)
    doc.add_heading("Afrikaanse vertaling", level=1)
    for para in translated.split("\n\n"):
        p = doc.add_paragraph(para)
        for run in p.runs:
            run.font.size = Pt(11)
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/translate")
async def translate_document(file: UploadFile = File(...)):
    # Validate
    if not file.filename:
        raise HTTPException(400, "No filename")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported type. Allowed: {', '.join(ALLOWED)}")

    # Size check
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, f"File too large. Max {MAX_SIZE // (1024 * 1024)} MB")

    # Extract text
    try:
        if ext == ".txt":
            text = content.decode("utf-8", errors="replace")
        elif ext == ".pdf":
            text = extract_text_from_pdf(content)
        elif ext == ".docx":
            text = extract_text_from_docx(content)
        else:
            raise HTTPException(400, "Unsupported")
    except Exception as e:
        raise HTTPException(400, f"Failed to extract text: {str(e)}")

    if not text.strip():
        raise HTTPException(400, "No extractable text found in document")

    # Translate
    try:
        translated = translate_to_afrikaans(text)
    except Exception as e:
        raise HTTPException(500, f"Translation failed: {str(e)}")

    # Return as downloadable DOCX
    output_bytes = create_translated_docx(text, translated)
    filename = f"afrikaans_{Path(file.filename).stem}.docx"

    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "target": "Afrikaans (af)"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
