# Afrikaans Document Translator

A simple web app that translates documents (TXT, PDF, DOCX) from **any language** to **Afrikaans**.

Built for easy deployment on **Render.com**.

## Features

- Upload files up to **100 MB**
- Supported formats: `.txt`, `.pdf`, `.docx`
- Automatic source language detection
- Translation to Afrikaans using Google Translate (via `deep-translator`)
- Returns a bilingual DOCX (original + Afrikaans translation)
- Clean drag-and-drop interface

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

## Deploy to Render.com

1. Push this folder to a GitHub repository.
2. Go to [https://render.com](https://render.com) → **New +** → **Web Service**.
3. Connect your repository.
4. Configure:
   - **Name**: anything you like (e.g. `afrikaans-translator`)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free (or Starter for better performance with large files)
5. Click **Create Web Service**.

Your app will be available at `https://your-service-name.onrender.com`.

### Important Notes for Free Tier

- Free services have **512 MB RAM**. Very large or complex PDFs may cause out-of-memory errors.
- The filesystem is **ephemeral** — uploaded files are not stored permanently.
- Free services spin down after inactivity (cold starts take ~30–60 seconds).
- For production use with large documents, upgrade to a paid plan.

## API Endpoints

| Method | Path       | Description                          |
|--------|------------|--------------------------------------|
| GET    | `/`        | Web interface                        |
| POST   | `/translate` | Upload a file and get translated DOCX |
| GET    | `/health`  | Health check                          |

## Limitations

- Translation quality depends on Google Translate.
- Long documents are chunked (≈4500 characters) to stay within free API limits.
- Scanned PDFs (image-only) are **not** supported (no OCR).
- Formatting from the original document is mostly lost (output is a clean bilingual DOCX).

## License

MIT – feel free to use and modify.
