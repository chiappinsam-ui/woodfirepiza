import os, json, time, mimetypes
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)  # always load the right .env

import boto3
import httpx
from botocore.client import Config
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS: allow your static site (Live Server) to talk to this API.
# Add/adjust origins as needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5800",
        "http://localhost:5800",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# R2 presign (S3-compatible)
# ----------------------------
def env(*names: str, default: str | None = None) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return default

# accept BOTH names so you can't get nuked by a mismatch
R2_ACCOUNT_ID = env("R2_ACCOUNT_ID")
R2_BUCKET = env("R2_BUCKET", "R2_BUCKET_NAME")
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
R2_PUBLIC_BASE_URL = env("R2_PUBLIC_BASE_URL", "R2_PUBLIC_BASE", default="").rstrip("/")
_r2_client = None

def get_r2_client():
    global _r2_client
    missing = []
    if not R2_ACCOUNT_ID:
        missing.append("R2_ACCOUNT_ID")
    if not R2_BUCKET:
        missing.append("R2_BUCKET")
    if not R2_ACCESS_KEY_ID:
        missing.append("R2_ACCESS_KEY_ID")
    if not R2_SECRET_ACCESS_KEY:
        missing.append("R2_SECRET_ACCESS_KEY")
    if not R2_PUBLIC_BASE_URL:
        missing.append("R2_PUBLIC_BASE_URL (or R2_PUBLIC_BASE)")
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"R2 not configured (missing {', '.join(missing)})",
        )

    if _r2_client is None:
        _r2_client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _r2_client

class PresignReq(BaseModel):
    slot: str
    content_type: str = "image/jpeg"

# ----------------------------
# Paths (make them robust)
# ----------------------------

# HTML files live next to main.py (adjust if you move them into /site)
INDEX_FILE = BASE_DIR / "index1.html"
MENU_FILE = BASE_DIR / "menu2.html"
GALLERY_FILE = BASE_DIR / "gallery5.html"
CONTACT_FILE = BASE_DIR / "contact6.html"
CATERING_FILE = BASE_DIR / "catering3.html"
BOOKINGS_FILE = BASE_DIR / "bookins4.html"

# Static site root (HTML + assets live alongside main.py)
SITE_DIR = BASE_DIR

# persistent-ish storage folder (free plan will still reset on redeploy)
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
MANIFEST_PATH = DATA_DIR / "manifest.json"
DEFAULTS_DIR = BASE_DIR / "defaults"

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------
# Manifest helpers
# ----------------------------
def load_manifest():
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_manifest(m):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2), encoding="utf-8")

manifest = load_manifest()

# ----------------------------
# Mount folders like *_files if present (optional)
# ----------------------------
for name in os.listdir(BASE_DIR):
    p = BASE_DIR / name
    if p.is_dir() and name.endswith("_files"):
        app.mount(f"/{name}", StaticFiles(directory=str(p)), name=name)

# ----------------------------
# Static assets
# ----------------------------
ASSETS_DIR = BASE_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# (Optional) expose uploaded files directly (not required if /media works)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# ----------------------------
# Admin auth
# ----------------------------
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "1234")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "photos")

def _guess_content_type(name: str) -> str:
    ct, _ = mimetypes.guess_type(name or "")
    return ct or "application/octet-stream"

def _public_url(key: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{key}"

def require_admin(x_admin_token: str | None):
    if (x_admin_token or "").strip() != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ----------------------------
# Routes: website pages
# ----------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/index1.html")

def serve_file(path: Path):
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File missing: {path.name}")
    return FileResponse(str(path))

@app.get("/index1.html", include_in_schema=False)
def index1_html():
    return serve_file(INDEX_FILE)

@app.get("/menu2.html", include_in_schema=False)
def menu2_html():
    return serve_file(MENU_FILE)

@app.get("/gallery5.html", include_in_schema=False)
def gallery5_html():
    return serve_file(GALLERY_FILE)

@app.get("/contact6.html", include_in_schema=False)
def contact6_html():
    return serve_file(CONTACT_FILE)

@app.get("/catering3.html", include_in_schema=False)
def catering3_html():
    return serve_file(CATERING_FILE)

@app.get("/bookins4.html", include_in_schema=False)
def bookins4_html():
    return serve_file(BOOKINGS_FILE)

# "pretty" routes (optional)
@app.get("/menu", include_in_schema=False)
def menu():
    return RedirectResponse(url="/menu2.html")

@app.get("/gallery", include_in_schema=False)
def gallery():
    return RedirectResponse(url="/gallery5.html")

@app.get("/contact", include_in_schema=False)
def contact():
    return RedirectResponse(url="/contact6.html")

@app.get("/catering", include_in_schema=False)
def catering():
    return RedirectResponse(url="/catering3.html")

@app.get("/bookings", include_in_schema=False)
def bookings():
    return RedirectResponse(url="/bookins4.html")

# ----------------------------
# Media + manifest
# ----------------------------
@app.get("/manifest.json", include_in_schema=False)
def get_manifest():
    return JSONResponse(manifest)

@app.get("/media/{slot}", include_in_schema=False)
def get_media(slot: str, request: Request):
    info = manifest.get(slot)

    # If this slot is stored in R2, redirect to the public URL (and keep cache-bust query params)
    if info and (info.get("public_url") or info.get("publicUrl")):
        public_url = (info.get("public_url") or info.get("publicUrl") or "").strip()
        if public_url:
            qs = request.url.query  # includes v=... etc
            if qs:
                public_url = public_url + ("&" if "?" in public_url else "?") + qs
            return RedirectResponse(url=public_url, status_code=307)

    # Otherwise fall back to local uploads (old behavior)
    if info and info.get("stored_name"):
        path = UPLOADS_DIR / info["stored_name"]
        if path.exists():
            return FileResponse(str(path))

    # Otherwise fall back to defaults/
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = DEFAULTS_DIR / f"{slot}{ext}"
        if p.exists():
            return FileResponse(str(p))

    raise HTTPException(status_code=404, detail="No image for this slot")

# ----------------------------
# R2 presigned uploads
# ----------------------------
@app.post("/r2/presign-put")
def presign_put(req: PresignReq):
    try:
        slot = req.slot.strip()
        if not slot or "/" in slot or ".." in slot:
            raise HTTPException(status_code=400, detail="Bad slot")

        # stable key per slot = global save
        ext = "jpg"
        if req.content_type == "image/png":
            ext = "png"
        elif req.content_type == "image/webp":
            ext = "webp"

        key = f"slots/{slot}.{ext}"
        s3 = get_r2_client()

        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": R2_BUCKET,
                "Key": key,
                "ContentType": req.content_type,
            },
            ExpiresIn=60,
        )

        public_url = f"{R2_PUBLIC_BASE_URL}/{key}"
        return {"uploadUrl": upload_url, "publicUrl": public_url, "key": key}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"presign failed: {type(e).__name__}: {e}")

# ----------------------------
# Admin endpoints
# ----------------------------
@app.options("/admin/upload-sb", include_in_schema=False)
@app.options("/admin/upload-sb/", include_in_schema=False)
def options_upload_sb():
    return JSONResponse(content={"detail": "OPTIONS allowed"})

@app.post("/admin/upload-sb")
@app.post("/admin/upload-sb/")
async def upload_supabase(
    request: Request,
    authorization: str | None = Header(default=None),
    x_key: str | None = Header(default=None),      # storage key like: menu__header-image.jpg
    x_filename: str | None = Header(default=None), # original filename (optional)
):
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    missing_env = []
    if not SUPABASE_URL:
        missing_env.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing_env.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing_env:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase env vars missing: {', '.join(missing_env)}",
        )

    key = (x_key or "").strip().lstrip("/")
    if not key:
        raise HTTPException(status_code=400, detail="Missing X-Key header")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty upload body")

    content_type = _guess_content_type(x_filename or key)

    # Upload (upsert overwrite)
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{key}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(upload_url, content=body, headers=headers)

    if r.status_code >= 400:
        raise HTTPException(status_code=500, detail=f"Supabase upload failed: {r.status_code} {r.text}")

    # Store as page-scoped manifest slot, e.g. menu__header-image
    manifest_slot = key.rsplit(".", 1)[0] if "." in key else key
    public_url = _public_url(key)
    manifest[manifest_slot] = {
        "content_type": content_type,
        "sb_key": key,
        "public_url": public_url,
        "updated": int(time.time()),
    }
    save_manifest(manifest)

    return {"ok": True, "key": key, "slot": manifest_slot, "publicUrl": public_url}

@app.post("/admin/upload/{slot}")
async def upload(
    slot: str,
    file: UploadFile = File(...),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    require_admin(x_admin_token)

    data = await file.read()
    ext = Path(file.filename).suffix.lower() or ".bin"
    stored_name = f"{slot}-{int(time.time())}{ext}"
    out_path = UPLOADS_DIR / stored_name
    out_path.write_bytes(data)

    manifest[slot] = {
        "original": file.filename,
        "content_type": file.content_type,
        "stored_name": stored_name,
        "size": len(data),
        "updated": int(time.time()),
    }
    save_manifest(manifest)
    return {"ok": True, "slot": slot, **manifest[slot]}

@app.post("/admin/upload-r2/{slot}")
async def upload_r2_alias(
    slot: str,
    file: UploadFile = File(...),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    require_admin(x_admin_token)

    data = await file.read()
    ext = Path(file.filename).suffix.lower() or ".bin"
    stored_name = f"{slot}-{int(time.time())}{ext}"
    out_path = UPLOADS_DIR / stored_name
    out_path.write_bytes(data)

    manifest[slot] = {
        "original": file.filename,
        "content_type": file.content_type,
        "stored_name": stored_name,
        "size": len(data),
        "updated": int(time.time()),
    }
    save_manifest(manifest)

    return {"ok": True, "slot": slot, "publicUrl": f"/media/{slot}", **manifest[slot]}

@app.delete("/admin/delete/{slot}")
def delete(
    slot: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    require_admin(x_admin_token)

    info = manifest.pop(slot, None)
    if info:
        path = UPLOADS_DIR / info["stored_name"]
        if path.exists():
            path.unlink()
        save_manifest(manifest)

    return {"ok": True, "slot": slot}

# ----------------------------
# Serve your HTML and assets from the root
# ----------------------------
# Disable the catch-all static mount by default so unmatched POSTs return 404
# instead of StaticFiles 405 responses. Set ENABLE_ROOT_STATIC_MOUNT=1 if needed.
ENABLE_ROOT_STATIC_MOUNT = os.getenv("ENABLE_ROOT_STATIC_MOUNT", "0") == "1"
if ENABLE_ROOT_STATIC_MOUNT:
    app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="site")
