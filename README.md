# Afrikaans Document Translator (High Limit)

Translate large documents to Afrikaans while preserving layout, images and tables as much as possible.

Built as a practical alternative to Google Docs translation with a much higher upload limit (100 MB).

## Features

- Upload limit: **100 MB**
- Supported formats: TXT, PDF, DOCX
- Two modes:
  - **Bilingual** (recommended): keeps original text + adds Afrikaans underneath
  - **Replace**: only Afrikaans text
- DOCX: in-place translation (images, tables, styles, headers/footers preserved)
- PDF: converted to DOCX first (best open-source quality), then translated
- Clean Google-inspired interface

## Deploy on Render

1. Push this folder to a GitHub repository.
2. Create a new **Web Service** on Render.
3. Settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Environment Variable (very important):
   - Key: `PYTHON_VERSION`
   - Value: `3.12.7`
5. Deploy.

Also make sure `runtime.txt` is present in the repo (contains `python-3.12.7`).

## Local testing

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000

## Notes

- Perfect 1:1 PDF layout preservation is not possible with free open-source tools.
- The PDF → DOCX conversion is currently the best practical approach.
- Very complex or scanned PDFs may lose some formatting.
- Free Google Translate has rate limits; very large documents can take several minutes.

## License

MIT
