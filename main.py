import os, json, time, re
from pathlib import Path

import httpx
from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
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

# ----------------------------
# Supabase Storage config
# ----------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "photos")  # change if needed

def sb_public_url(key: str) -> str:
    # Only works if bucket is public
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{key}"

async def sb_upload_bytes(key: str, data: bytes, content_type: str):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY on backend",
        )

    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{key}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "x-upsert": "true",
        "Content-Type": content_type or "application/octet-stream",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(upload_url, headers=headers, content=data)
    if r.status_code >= 300:
        raise HTTPException(status_code=500, detail=f"Supabase upload failed: {r.status_code} {r.text}")

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
    
    if path.suffix.lower() == ".html":
        # Read the file and ignore heavy decoding errors
        html = path.read_text(encoding="utf-8", errors="ignore")
        
        # 1. Fix the "Weird Writing" (Encoding artifacts)
        replacements = {
            "\u00C2": "", "\u00E2\u20AC\u2122": "'", "\u00E2\u20AC\u201C": "-", "\u00E2\u20AC\u0153": '"', "\u00E2\u20AC": '"',
            "&#8217;": "'", "&#8211;": "-", "&#8220;": '"', "&#8221;": '"',
            "&#038;": "&", "&nbsp;": " ",
        }
        for bad, good in replacements.items():
            html = html.replace(bad, good)
            
        # 2. Fix the Mobile Menu (Force open during Edit Mode)
        mobile_menu_fix = """
<script>
document.addEventListener("DOMContentLoaded", function() {
    // Loop a check so it pops open the second you hit your edit hotkey
    setInterval(function() {
        const mobileMenu = document.querySelector('.et_mobile_menu');
        const isEditMode = sessionStorage.getItem("__EDIT_MODE__") === "1";
        
        if (mobileMenu && isEditMode) {
            mobileMenu.style.display = 'block';
            mobileMenu.style.opacity = '1';
            mobileMenu.style.visibility = 'visible';
            mobileMenu.style.position = 'relative'; // Stops it from overlapping other content
        }
    }, 500);
});
</script>
</body>
"""
        html = html.replace("</body>", mobile_menu_fix)
        
        # 3. Image rewriting logic (Keep your existing regex logic here)
        html = re.sub(r'\s+(data-)?srcset="[^"]*"', '', html)
        html = re.sub(r'\s+(data-)?sizes="[^"]*"', '', html)
        
        def swap_img_src(match):
            tag = match.group(0)
            slot = re.search(r'data-slot="([^"]+)"', tag).group(1)
            return re.sub(r'src="[^"]*"', f'src="/media/{slot}"', tag)
            
        html = re.sub(r'<img[^>]+data-slot="[^"]*"[^>]*>', swap_img_src, html)
        
        def swap_bg(match):
            tag = match.group(0)
            slot = re.search(r'data-bg-slot="([^"]+)"', tag).group(1)
            if 'style="' in tag:
                return re.sub(r'style="([^"]*)"', rf'style="\1; background-image: url(\'/media/{slot}\') !important;"', tag)
            else:
                return tag.replace('>', f' style="background-image: url(\'/media/{slot}\') !important;">')

        html = re.sub(r'<[^>]+data-bg-slot="[^"]*"[^>]*>', swap_bg, html)
        
        return HTMLResponse(content=html)

    # For non-HTML files, just serve them normally
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

@app.get("/api/manifest", include_in_schema=False)
def get_manifest_api():
    return JSONResponse(manifest)

@app.get("/media/{slot}", include_in_schema=False)
def get_media(slot: str):
    info = manifest.get(slot)

    # 1) If manifest has a Supabase public_url, redirect to it
    if info and info.get("public_url"):
        return RedirectResponse(url=info["public_url"], status_code=307)

    # 2) Backwards compatible: local stored_name
    if info and info.get("stored_name"):
        path = UPLOADS_DIR / info["stored_name"]
        if path.exists():
            return FileResponse(str(path))

    # 3) Defaults
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

@app.post("/admin/upload-sb/{slot}")
async def upload_sb(
    slot: str,
    file: UploadFile = File(...),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    require_admin(x_admin_token)

    data = await file.read()
    content_type = file.content_type or "application/octet-stream"

    # Decide the object name in your bucket:
    # keep it stable per slot so re-uploads overwrite
    ext = Path(file.filename).suffix.lower() or ".bin"
    sb_key = f"{slot}{ext}"

    # Upload to Supabase bucket
    await sb_upload_bytes(sb_key, data, content_type)

    # Write manifest entry using public_url (NOT stored_name)
    manifest[slot] = {
        "original": file.filename,
        "content_type": content_type,
        "sb_key": sb_key,
        "public_url": sb_public_url(sb_key),
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
        stored = info.get("stored_name")
        if stored:
            path = UPLOADS_DIR / stored
            if path.exists():
                path.unlink()
        save_manifest(manifest)

    return {"ok": True, "slot": slot}

# ----------------------------
# Serve your HTML and assets from the root
# ----------------------------
app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="site")
