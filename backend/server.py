from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import mimetypes
    
from src.textract_client import TextractClient
from src.llm import run_prompt, run_prompt_stream
from src.vllm import run_visual_ocr, ocr_with_openrouter_stream
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

app = FastAPI(title="CPADemo Server")

# shared Textract client (uses environment AWS credentials)
client = TextractClient(region=os.environ.get("AWS_REGION", "us-east-1"))

# Allow CORS for common dev origins (Vite, localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:8080", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from backend/webroot at /webroot
WEBROOT_DIR = BASE_DIR / "webroot"
if WEBROOT_DIR.exists():
    app.mount("/webroot", StaticFiles(directory=str(WEBROOT_DIR)), name="webroot")
    # Mount subdirectories and register routes for root-level files
    for p in WEBROOT_DIR.iterdir():
        if p.is_dir():
            try:
                app.mount(f"/{p.name}", StaticFiles(directory=str(p)), name=p.name)
            except Exception:
                pass
        elif p.is_file() and p.name != "index.html":
            def _make_file_route(fp=p, fn=p.name):
                media_type = mimetypes.guess_type(fn)[0] or "application/octet-stream"
                @app.get(f"/{fn}", include_in_schema=False)
                def _serve():
                    return FileResponse(path=str(fp), media_type=media_type, content_disposition_type="inline")
            _make_file_route()
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


def _write_upload_metadata(file_id: str, filename: str, uploaded_at: float, content_type: str, source_url: Optional[str] = None) -> None:
    meta = {
        "filename": filename,
        "uploadedAt": uploaded_at,
        "contentType": content_type,
    }
    if source_url:
        meta["sourceUrl"] = source_url

    meta_path = UPLOAD_DIR / f"{file_id}.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def _store_upload_bytes(
    *,
    file_id: str,
    filename: str,
    contents: bytes,
    content_type: Optional[str] = None,
    source_url: Optional[str] = None,
) -> Path:
    suffix = Path(filename).suffix or ""
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    dest.write_bytes(contents)

    uploaded_at = dest.stat().st_mtime
    resolved_content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    _write_upload_metadata(file_id, filename, uploaded_at, resolved_content_type, source_url=source_url)
    return dest


def _filename_from_url(url: str, content_type: Optional[str]) -> str:
    parsed = urlparse(url)
    raw_name = Path(unquote(parsed.path)).name
    if raw_name:
        return raw_name

    guessed_ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
    return f"downloaded-document{guessed_ext}"


def _is_supported_remote_document(filename: str, content_type: Optional[str]) -> bool:
    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type.startswith("image/") or normalized_type == "application/pdf":
        return True

    guessed_type = mimetypes.guess_type(filename)[0] or ""
    return guessed_type.startswith("image/") or guessed_type == "application/pdf"


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> JSONResponse:
    """Upload an image/PDF and receive an `id` to reference it later.

    Returns JSON: {"id": "<id>"}
    """
    file_id = uuid.uuid4().hex
    try:
        contents = await file.read()
        filename = file.filename or "uploaded-file"
        dest = _store_upload_bytes(
            file_id=file_id,
            filename=filename,
            contents=contents,
            content_type=getattr(file, "content_type", None),
        )
        logger.info("Saved upload '%s' to %s", file.filename, dest)
    except Exception as e:
        logger.exception("Failed to save upload '%s'", file.filename)
        raise HTTPException(status_code=500, detail=f"failed to save upload: {e}")
    return JSONResponse({"id": file_id})


class UploadLinkRequest(BaseModel):
    url: str


@app.post("/upload-link")
def upload_link(req: UploadLinkRequest) -> JSONResponse:
    """Download a remote document into the uploads directory and return its id."""
    url = (req.url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="invalid document URL")

    file_id = uuid.uuid4().hex
    request = Request(url, headers={"User-Agent": "textract-uploader/1.0"})

    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type() or response.headers.get("Content-Type")
            contents = response.read()

        if not contents:
            raise HTTPException(status_code=400, detail="downloaded file is empty")

        filename = _filename_from_url(url, content_type)
        if not _is_supported_remote_document(filename, content_type):
            raise HTTPException(status_code=400, detail="remote document must be an image or PDF")

        dest = _store_upload_bytes(
            file_id=file_id,
            filename=filename,
            contents=contents,
            content_type=content_type,
            source_url=url,
        )
        logger.info("Downloaded remote upload '%s' to %s", url, dest)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to download remote upload '%s'", url)
        raise HTTPException(status_code=400, detail=f"failed to download document: {e}")

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
    stem = path.stem
    try:
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


@app.websocket("/ws/vllm/ocr")
async def ws_vllm_ocr(websocket: WebSocket):
    """WebSocket endpoint for streaming vllm visual OCR.

    Accepts a single JSON message: {"id": "...", "model": "..." (optional)}
    Streams OCR text chunks back as plain text frames, then sends [[DONE]].
    Saves final result to <id>.txt and updates metadata JSON.
    """
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        try:
            payload = json.loads(raw)
            file_id = payload.get("id")
            model = payload.get("model") or None
        except Exception:
            await websocket.send_text(json.dumps({"error": "invalid payload; expected JSON with id"}))
            await websocket.close()
            return

        path = _find_file_by_id(file_id)
        if not path:
            await websocket.send_text(json.dumps({"error": "file id not found"}))
            await websocket.close()
            return

        loop = asyncio.get_running_loop()
        stem = path.stem

        def produce():
            try:
                chunks = []
                for chunk in ocr_with_openrouter_stream(str(path), model=model):
                    asyncio.run_coroutine_threadsafe(websocket.send_text(chunk), loop)
                    chunks.append(chunk)

                full_text = ''.join(chunks)

                # persist to <id>.txt
                try:
                    txt_path = UPLOAD_DIR / f"{stem}.txt"
                    txt_path.write_text(full_text, encoding="utf-8")
                except Exception:
                    logger.exception("Failed to save vllm stream result for %s", file_id)

                # update metadata JSON
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
                    logger.exception("Failed to update metadata JSON for vllm stream %s", stem)

                asyncio.run_coroutine_threadsafe(websocket.send_text("[[DONE]]"), loop)
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
        # persist LLM result to <id>.llm.txt so it survives page refreshes
        try:
            llm_path = UPLOAD_DIR / f"{stem}.llm.txt"
            llm_path.write_text(result or "", encoding="utf-8")
        except Exception:
            logger.exception("Failed to save LLM result for %s", stem)
        # update metadata JSON with LLM model used
        try:
            meta_path = UPLOAD_DIR / f"{stem}.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    meta = {}
            meta["llmMethod"] = "llm"
            meta["llmModel"] = req.model or None
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
        except Exception:
            logger.exception("Failed to update metadata JSON with LLM info for %s", stem)
    except Exception as e:
        # If an HTTPException was raised above, re-raise it; otherwise return 500
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({"result": result})


@app.get("/llm/{file_id}")
def get_llm_result(file_id: str) -> JSONResponse:
    """Return previously saved LLM result for given id (if present)."""
    path = _find_file_by_id(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="file id not found")
    stem = path.stem
    llm_path = UPLOAD_DIR / f"{stem}.llm.txt"
    if not llm_path.exists():
        raise HTTPException(status_code=404, detail="llm result not found")
    try:
        txt = llm_path.read_text(encoding="utf-8")
        # attempt to include saved model name from metadata JSON
        model = None
        try:
            meta_path = UPLOAD_DIR / f"{stem}.json"
            if meta_path.exists():
                m = json.loads(meta_path.read_text(encoding="utf-8")) or {}
                model = m.get("llmModel") or m.get("ocrModel")
        except Exception:
            logger.exception("Failed to read metadata JSON for %s", stem)
        return JSONResponse({"id": file_id, "text": txt, "model": model})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read llm result: {e}")


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
                # stream LLM output to client and collect chunks to persist after completion
                chunks = []
                stem = path.stem
                for chunk in run_prompt_stream(prompt, doc_text, model=model):
                    asyncio.run_coroutine_threadsafe(websocket.send_text(chunk), loop)
                    try:
                        chunks.append(chunk)
                    except Exception:
                        logger.exception("Failed to buffer stream chunk for %s", file_id)

                # after streaming completes, persist the collected LLM output to <id>.llm.txt
                try:
                    llm_path = UPLOAD_DIR / f"{stem}.llm.txt"
                    llm_path.write_text(''.join(chunks), encoding="utf-8")
                except Exception:
                    logger.exception("Failed to save streamed LLM result for %s", file_id)
                # update metadata JSON with LLM model used
                try:
                    meta_path = UPLOAD_DIR / f"{stem}.json"
                    meta = {}
                    if meta_path.exists():
                        try:
                            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
                        except Exception:
                            meta = {}
                    meta["llmMethod"] = "llm"
                    meta["llmModel"] = model or None
                    meta_path.write_text(json.dumps(meta), encoding="utf-8")
                except Exception:
                    logger.exception("Failed to update metadata JSON with LLM info for %s", stem)

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
