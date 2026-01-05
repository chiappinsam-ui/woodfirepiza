from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os, json, time
from pathlib import Path

app = FastAPI()

# Mount any folders ending in "_files" (Dreamweaver-style exports)
for name in os.listdir("."):
    if os.path.isdir(name) and name.endswith("_files"):
        app.mount(f"/{name}", StaticFiles(directory=name), name=name)

# ====== storage on disk (simple) ======
DATA_DIR = Path("data")
UPLOADS_DIR = DATA_DIR / "uploads"
MANIFEST_PATH = DATA_DIR / "manifest.json"

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

def load_manifest():
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}

def save_manifest(m):
    MANIFEST_PATH.write_text(json.dumps(m, indent=2), encoding="utf-8")

manifest = load_manifest()

# Serve your normal static assets if needed
# (adjust folder names if different)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# ====== simple admin auth (header token) ======
# Set this as a Render env var: ADMIN_TOKEN = something
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme")

def require_admin(x_admin_token: str | None):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ====== Serve HTML pages ======
@app.get("/")
def home():
    return FileResponse("index1.html")

@app.get("/index1.html")
def index1_html():
    return FileResponse("index1.html")

@app.get("/menu")
def menu():
    return FileResponse("menu2.html")

@app.get("/menu2.html")
def menu2_html():
    return FileResponse("menu2.html")

@app.get("/gallery")
def gallery():
    return FileResponse("gallery5.html")

@app.get("/gallery5.html")
def gallery5_html():
    return FileResponse("gallery5.html")

@app.get("/contact")
def contact():
    return FileResponse("contact6.html")

@app.get("/contact6.html")
def contact6_html():
    return FileResponse("contact6.html")

@app.get("/catering")
def catering():
    return FileResponse("catering3.html")

@app.get("/catering3.html")
def catering3_html():
    return FileResponse("catering3.html")

@app.get("/bookings")
def bookings():
    return FileResponse("bookins4.html")  # confirm spelling

@app.get("/bookins4.html")
def bookins4_html():
    return FileResponse("bookins4.html")

# ====== Media slot serving ======
@app.get("/media/{slot}")
def get_media(slot: str):
    info = manifest.get(slot)
    if not info:
        # return a placeholder or 404
        raise HTTPException(status_code=404, detail="No image for this slot")
    path = UPLOADS_DIR / info["stored_name"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on server")
    return FileResponse(path)

@app.get("/manifest.json")
def get_manifest():
    return JSONResponse(manifest)

# ====== Admin endpoints ======
@app.post("/admin/upload/{slot}")
async def upload(slot: str, file: UploadFile = File(...), x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    data = await file.read()

    # keep extension if possible
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
def delete(slot: str, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    info = manifest.pop(slot, None)
    if info:
        path = UPLOADS_DIR / info["stored_name"]
        if path.exists():
            path.unlink()
        save_manifest(manifest)
    return {"ok": True, "slot": slot}
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/media/{slot}")
def get_media(slot: str):
    # look for any file that starts with "{slot}."
    for name in os.listdir(UPLOAD_DIR):
        if name == slot or name.startswith(slot + "."):
            path = os.path.join(UPLOAD_DIR, name)
            return FileResponse(path)

    # (optional) return a placeholder instead of 404
    # return FileResponse("assets/placeholder.png")

    raise HTTPException(status_code=404, detail="Image not found")
g