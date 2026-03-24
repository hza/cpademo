# Textract Frontend

Vite + React frontend for uploading documents to the Textract backend.

Run:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and upload an image or PDF. The app will POST to `http://localhost:8000/upload` and show the returned `id` with a link to view extracted text.
