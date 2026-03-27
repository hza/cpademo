from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import mimetypes
    
from src.textract_client import TextractClient
from src.llm import run_prompt, run_prompt_stream
from src.vllm import run_visual_ocr
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel


BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# load environment variables from .env (if present)
load_dotenv()

# configure basic logging to stdout
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Textract Server")

# shared Textract client (uses environment AWS credentials)
client = TextractClient(region=os.environ.get("AWS_REGION", "us-east-1"))

# Allow CORS for common dev origins (Vite, localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from backend/webroot at /webroot
WEBROOT_DIR = BASE_DIR / "webroot"
if WEBROOT_DIR.exists():
    app.mount("/webroot", StaticFiles(directory=str(WEBROOT_DIR)), name="webroot")
    # Mount any subdirectories (e.g. /assets) so absolute paths in index.html resolve
    for p in WEBROOT_DIR.iterdir():
        if p.is_dir():
            mount_path = f"/{p.name}"
            try:
                app.mount(mount_path, StaticFiles(directory=str(p)), name=p.name)
            except Exception:
                pass
    # serve favicon at site root if present
    favicon_path = WEBROOT_DIR / "favicon.svg"
    if favicon_path.exists():
        @app.get("/favicon.svg")
        def favicon_svg():
            try:
                return FileResponse(path=str(favicon_path), filename="favicon.svg", media_type="image/svg+xml")
            except Exception:
                raise HTTPException(status_code=500, detail="failed to read favicon")
    # optional: serve index at root of mounted path
    @app.get("/", response_class=HTMLResponse)
    def root_index():
        index = WEBROOT_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"))
        return JSONResponse({"status": "ok"})


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> JSONResponse:
    """Upload an image/PDF and receive an `id` to reference it later.

    Returns JSON: {"id": "<id>"}
    """
    file_id = uuid.uuid4().hex
    suffix = Path(file.filename).suffix or ""
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    try:
        contents = await file.read()
        dest.write_bytes(contents)
        logger.info("Saved upload '%s' to %s", file.filename, dest)
        # create metadata JSON referencing the original filename and upload time
        # metadata filename uses bare id (no prefix)
        meta = UPLOAD_DIR / f"{file_id}.json"
        try:
            uploaded_at = dest.stat().st_mtime
            # prefer provided upload content type, else guess from filename
            content_type = getattr(file, 'content_type', None) or mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
            meta.write_text(json.dumps({"filename": file.filename, "uploadedAt": uploaded_at, "contentType": content_type}), encoding="utf-8")
        except Exception:
            logger.exception("Failed to write metadata for upload %s", dest)
    except Exception as e:
        logger.exception("Failed to save upload '%s' -> %s", file.filename, dest)
        raise HTTPException(status_code=500, detail=f"failed to save upload: {e}")
    return JSONResponse({"id": file_id})


def _find_file_by_id(file_id: str) -> Optional[Path]:
    # If metadata exists, prefer the original uploaded filename/suffix recorded there
    meta = UPLOAD_DIR / f"{file_id}.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            orig = data.get("filename")
            if orig:
                suffix = Path(orig).suffix or ""
                candidate = UPLOAD_DIR / f"{file_id}{suffix}"
                if candidate.exists():
                    return candidate
        except Exception:
            logger.exception("Failed to read metadata for %s", file_id)

    # Fallback: prefer any match that isn't metadata (.json) or extracted text (.txt)
    matches = sorted(UPLOAD_DIR.glob(f"{file_id}.*"), key=lambda p: p.suffix)
    for p in matches:
        if p.suffix.lower() not in (".json", ".txt"):
            return p

    # If only .txt or .json exist, prefer the text file first, then metadata JSON
    for p in matches:
        if p.suffix.lower() == ".txt":
            return p
    for p in matches:
        if p.suffix.lower() == ".json":
            return p

    # fallback: allow files saved with no extension
    p = UPLOAD_DIR / file_id
    if p.exists():
        return p
    return None


@app.get("/uploads")
def list_uploads() -> JSONResponse:
    """Return uploads based on metadata JSON files created at upload time.

    Each metadata file is named `<id>.json` and contains {"filename": "..."}.
    This endpoint returns a list of objects with `id` and `name` (original filename).
    """
    files = []
    # consider metadata JSON files (new style: <id>.json)
    for p in sorted(UPLOAD_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "filename" not in data:
                # skip unrelated JSON files
                continue
            filename = data.get("filename") or ""
            uploaded_at = data.get("uploadedAt") or p.stat().st_mtime
            content_type = data.get("contentType")
            # bare id is the filename stem
            bare_id = p.stem
            # determine status by checking for extracted text file (new style: <id>.txt)
            new_text = UPLOAD_DIR / f"{bare_id}.txt"
            has_text = new_text.exists()
            status = "READY" if has_text else "UPLOADED"
            files.append({
                "id": bare_id,
                "name": filename,
                "uploadedAt": uploaded_at,
                "status": status,
                "contentType": content_type,
                "has_text": has_text,
                "ocrMethod": data.get("ocrMethod") if isinstance(data, dict) else None,
                "ocrModel": data.get("ocrModel") if isinstance(data, dict) else None,
            })
        except Exception:
            logger.exception("Failed to read upload metadata %s", p)
            continue
    return JSONResponse({"uploads": files})


@app.delete("/upload/{file_id}")
def delete_upload(file_id: str) -> JSONResponse:
    """Delete all files associated with a given upload id (<id>.* and <id>).

    Returns JSON listing deleted filenames. If no files are found, returns 404.
    """
    deleted = []
    # remove files matching the id with any extension
    for p in list(UPLOAD_DIR.glob(f"{file_id}.*")):
        try:
            p.unlink()
            logger.info("Deleted %s", p)
            deleted.append(p.name)
        except Exception:
            logger.exception("Failed to delete %s", p)
    # also remove file with no extension if present
    plain = UPLOAD_DIR / file_id
    if plain.exists():
        try:
            plain.unlink()
            logger.info("Deleted %s", plain)
            deleted.append(plain.name)
        except Exception:
            logger.exception("Failed to delete %s", plain)

    if not deleted:
        raise HTTPException(status_code=404, detail="file id not found")

    return JSONResponse({"deleted": deleted})


@app.get("/textract/{file_id}")
def textract_by_id(file_id: str, fresh: bool = False) -> JSONResponse:
    """Run Textract on the previously uploaded file and return extracted text."""
    path = _find_file_by_id(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="file id not found")

    # If a saved text file already exists (new style: <stem>.txt), return it.
    # Look for extracted text in new style: <id>.txt
    stem = path.stem
    new_text = UPLOAD_DIR / f"{stem}.txt"
    # If cached text exists and the client didn't request a fresh extraction, return cached
    if new_text.exists() and not fresh:
        try:
            # prefer new_text; if only old_text exists, migrate it to new_text
            txt = new_text.read_text(encoding="utf-8")
            return JSONResponse({"id": file_id, "text": txt})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"failed to read text file: {e}")

    try:
        # prefer rich markdown export (tables/forms) when available
        text = client.export_markdown(file_path=str(path))
    except Exception:
        # fallback to plain-line extraction
        try:
            text = client.extract_text(file_path=str(path))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # save extracted text (new style: <stem>.txt) so future requests can return it immediately
    try:
        new_text.write_text(text, encoding="utf-8")
    except Exception:
        # don't fail the request if saving the file fails; just log silently
        pass

    # update metadata JSON to record OCR method (textract) and model (none)
    try:
        meta_path = UPLOAD_DIR / f"{stem}.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
        meta["ocrMethod"] = "textract"
        meta["ocrModel"] = None
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except Exception:
        logger.exception("Failed to update metadata JSON with OCR info for %s", stem)

    return JSONResponse({"id": file_id, "text": text})


@app.post("/vllm/ocr/{file_id}")
def vllm_ocr(file_id: str, model: Optional[str] = None) -> JSONResponse:
    """Run visual OCR (OpenRouter visual LLM with local fallback) on the original file.

    Saves the extracted text to `<id>.txt` and returns `{"id":"...","text":"..."}`.
    """
    path = _find_file_by_id(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="file id not found")

    try:
        res = run_visual_ocr(str(path), model=model)
        # prefer `text` key if present
        text = res.get("text") if isinstance(res, dict) else str(res)
        if text is None:
            text = json.dumps(res)
    except Exception as e:
        logger.exception("vllm OCR failed for %s: %s", file_id, e)
        raise HTTPException(status_code=500, detail=f"vllm ocr failed: {e}")

    # persist as extracted text for future requests (vllm output should be saved)
    try:
        stem = path.stem
        txt_path = UPLOAD_DIR / f"{stem}.txt"
        txt_path.write_text(text, encoding="utf-8")
    except Exception:
        logger.exception("Failed to save extracted text for %s", file_id)

    # update metadata JSON to record OCR method (vllm) and model used
    try:
        meta_path = UPLOAD_DIR / f"{stem}.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
        meta["ocrMethod"] = "vllm"
        meta["ocrModel"] = model or None
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except Exception:
        logger.exception("Failed to update metadata JSON with vllm OCR info for %s", stem)

    return JSONResponse({"id": file_id, "text": text})


@app.get("/download/{file_id}")
def download_file(file_id: str):
    """Return the originally uploaded file (binary) for the given id."""
    path = _find_file_by_id(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="file id not found")
    try:
        # set a sensible Content-Type based on the file extension
        media_type = mimetypes.guess_type(str(path))[0]
        return FileResponse(path=str(path), filename=path.name, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read file: {e}")


class DetectRequest(BaseModel):
    id: str
    prompt: str
    model: Optional[str] = None


@app.post("/detect_gl")
def detect_gl(req: DetectRequest) -> JSONResponse:
    """Run the user-provided prompt against the document text via the LLM.

    Body: {"id": "...", "prompt": "..."}
    Returns: {"result": "<llm output>"}
    """
    path = _find_file_by_id(req.id)
    if not path:
        raise HTTPException(status_code=404, detail="file id not found")

    # get extracted text (prefer cached .txt, else run Textract)
    # prefer cached text in new style: <id>.txt
    stem = path.stem
    new_text = UPLOAD_DIR / f"{stem}.txt"
    if new_text.exists():
        doc_text = new_text.read_text(encoding="utf-8")
    else:
        try:
            doc_text = client.export_markdown(file_path=str(path))
        except Exception:
            doc_text = client.extract_text(file_path=str(path))

    try:
        # ensure API key is present before calling the LLM
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY is not set. Set it in the environment to call the LLM.")
        result = run_prompt(req.prompt, doc_text, model=req.model)
    except Exception as e:
        # If an HTTPException was raised above, re-raise it; otherwise return 500
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({"result": result})


@app.websocket("/ws/detect_gl")
async def ws_detect_gl(websocket: WebSocket):
    """WebSocket endpoint that accepts a single JSON message: {"id": "...", "prompt": "..."}

    Streams LLM output back to the client as plain text frames. Sends a final `[[DONE]]` frame when finished.
    """
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        try:
            payload = json.loads(raw)
            file_id = payload.get("id")
            prompt = payload.get("prompt")
            model = payload.get("model") or None
        except Exception:
            await websocket.send_text(json.dumps({"error": "invalid payload; expected JSON with id and prompt"}))
            await websocket.close()
            return

        path = _find_file_by_id(file_id)
        if not path:
            await websocket.send_text(json.dumps({"error": "file id not found"}))
            await websocket.close()
            return

        # obtain document text (prefer cached in new style: <id>.txt)
        stem = path.stem
        new_text = UPLOAD_DIR / f"{stem}.txt"
        if new_text.exists():
            doc_text = new_text.read_text(encoding="utf-8")
        else:
            try:
                doc_text = client.export_markdown(file_path=str(path))
            except Exception:
                doc_text = client.extract_text(file_path=str(path))

        # run the streaming LLM in a background thread and forward chunks as they arrive
        loop = asyncio.get_running_loop()

        def produce():
            try:
                # stream LLM output to client without persisting to disk
                for chunk in run_prompt_stream(prompt, doc_text, model=model):
                    asyncio.run_coroutine_threadsafe(websocket.send_text(chunk), loop)

                asyncio.run_coroutine_threadsafe(websocket.send_text('[[DONE]]'), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(websocket.send_text(json.dumps({"error": str(e)})), loop)

        await loop.run_in_executor(None, produce)

    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# Catch-all: serve index.html for any unmatched route so React Router handles client-side navigation.
# Must be registered last so it doesn't shadow API routes.
@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
def spa_fallback(full_path: str):
    index = WEBROOT_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Not found")
