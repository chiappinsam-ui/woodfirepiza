import os, json, time
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS: allow your static site (Live Server) to talk to this API.
# Add/adjust origins as needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Paths (make them robust)
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent

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
ADMIN_TOKEN = "1234"

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
def get_media(slot: str):
    # 1) If we have a replacement in manifest, serve it
    info = manifest.get(slot)
    if info:
        path = UPLOADS_DIR / info["stored_name"]
        if path.exists():
            return FileResponse(str(path))

    # 2) Otherwise serve default/original from defaults/
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = DEFAULTS_DIR / f"{slot}{ext}"
        if p.exists():
            return FileResponse(str(p))

    raise HTTPException(status_code=404, detail="No image for this slot")

# ----------------------------
# Admin endpoints
# ----------------------------
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
app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="site")
