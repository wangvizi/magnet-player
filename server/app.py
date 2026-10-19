"""磁力播放器服务器主程序。

职责：
1. 接收磁力链接 / .torrent 文件，交给 aria2 下载；
2. 实时汇报下载进度；
3. 下载完成后用 ffmpeg 生成 HLS，供 iOS AVPlayer 直接播放。
"""
import base64
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from downloader import Aria2Downloader, Aria2Error
from streamer import generate_hls, pick_video_file

BASE = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parent / "data")))
DOWNLOAD_DIR = BASE / "downloads"
HLS_ROOT = BASE / "hls"
HLS_ROOT.mkdir(parents=True, exist_ok=True)

STATIC_DIR = Path(__file__).resolve().parent / "static"

API_KEY = os.getenv("API_KEY", "").strip()

dl = Aria2Downloader(
    port=int(os.getenv("ARIA2_PORT", "6800")),
    secret=os.getenv("RPC_SECRET", "magnetplayer"),
    download_dir=str(DOWNLOAD_DIR),
)

tasks = {}
tasks_lock = threading.Lock()
hls_locks = {}


class MagnetIn(BaseModel):
    magnet: str


class Task:
    def __init__(self, gid, magnet=None):
        self.gid = gid
        self.magnet = magnet or ""
        self.name = ""
        self.status = "pending"
        self.total_length = 0
        self.completed_length = 0
        self.download_speed = 0
        self.num_seeders = 0
        self.error = ""
        self.video_path = None
        self.file_paths = []
        self.hls_ready = False
        self.hls_generating = False
        self.created_at = time.time()


def task_to_dict(t):
    return {
        "gid": t.gid,
        "name": t.name,
        "status": t.status,
        "totalLength": t.total_length,
        "completedLength": t.completed_length,
        "progress": round(t.completed_length / t.total_length, 4) if t.total_length else 0.0,
        "downloadSpeed": t.download_speed,
        "numSeeders": t.num_seeders,
        "error": t.error,
        "hlsReady": t.hls_ready,
        "hlsGenerating": t.hls_generating,
        "createdAt": t.created_at,
    }


def refresh_task(t):
    try:
        s = dl.status(t.gid)
    except Aria2Error as e:
        # 任务可能已被 aria2 清理
        t.status = "removed"
        t.error = str(e)
        return t

    t.status = s.get("status") or "unknown"
    t.total_length = int(s.get("totalLength") or 0)
    t.completed_length = int(s.get("completedLength") or 0)
    t.download_speed = int(s.get("downloadSpeed") or 0)
    t.num_seeders = int(s.get("numSeeders") or 0)

    code = s.get("errorCode") or "0"
    if code not in ("0", ""):
        t.error = s.get("errorMessage") or f"aria2 错误码 {code}"

    bt = s.get("bittorrent") or {}
    info = bt.get("info") or {}
    if info.get("name"):
        t.name = info["name"]

    files = s.get("files") or []
    if files:
        t.file_paths = [f.get("path") for f in files if f.get("path")]
        if not t.name:
            t.name = Path(files[0].get("path", "")).name
        if t.status == "complete" and not t.video_path:
            vf = pick_video_file(files)
            if vf:
                t.video_path = vf["path"]
    return t


def start_hls_generation(t):
    """触发后台 HLS 生成，返回当前状态：ready / generating / error。"""
    lock = hls_locks.setdefault(t.gid, threading.Lock())
    with lock:
        if t.hls_ready:
            return "ready"
        if t.hls_generating:
            return "generating"
        if not t.video_path:
            return "error"
        t.hls_generating = True
        threading.Thread(target=_hls_worker, args=(t.gid,), daemon=True).start()
        return "generating"


def _hls_worker(gid):
    t = tasks.get(gid)
    if not t:
        return
    lock = hls_locks.setdefault(gid, threading.Lock())
    try:
        generate_hls(t.video_path, HLS_ROOT / gid)
        with lock:
            t.hls_ready = True
    except Exception as e:
        with lock:
            t.error = str(e)
    finally:
        with lock:
            t.hls_generating = False


@asynccontextmanager
async def lifespan(_app):
    dl.start()
    # 恢复历史任务（避免重启后丢失）
    try:
        for item in dl.list_all():
            gid = item.get("gid")
            if gid:
                t = Task(gid)
                refresh_task(t)
                tasks[gid] = t
    except Exception:
        pass
    yield
    dl.stop()


app = FastAPI(title="Magnet Player Server", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_auth(request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        if request.headers.get("X-API-Key") != API_KEY:
            return JSONResponse(status_code=401, content={"error": "无效的 API Key"})
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.0.0"}


@app.post("/api/task")
def add_magnet(payload: MagnetIn):
    magnet = payload.magnet.strip()
    if not magnet:
        raise HTTPException(400, "磁力链接为空")
    if not (magnet.startswith("magnet:") or magnet.startswith("http")):
        raise HTTPException(400, "请提供 magnet: 磁力链接")
    try:
        gid = dl.add_magnet(magnet)
    except Aria2Error as e:
        raise HTTPException(500, str(e))
    t = Task(gid, magnet=magnet)
    with tasks_lock:
        tasks[gid] = t
    try:
        with tasks_lock:
            refresh_task(t)
    except Exception:
        pass
    return task_to_dict(t)


@app.post("/api/task/torrent")
async def add_torrent(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "文件为空")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "种子文件过大")
    b64 = base64.b64encode(data).decode()
    try:
        gid = dl.add_torrent(b64)
    except Aria2Error as e:
        raise HTTPException(500, str(e))
    t = Task(gid)
    with tasks_lock:
        tasks[gid] = t
    return task_to_dict(t)


@app.get("/api/tasks")
def list_tasks():
    with tasks_lock:
        gids = list(tasks.keys())
    result = []
    for gid in gids:
        t = tasks.get(gid)
        if not t:
            continue
        try:
            refresh_task(t)
        except Exception:
            pass
        result.append(task_to_dict(t))
    result.sort(key=lambda x: x["createdAt"], reverse=True)
    return result


@app.get("/api/task/{gid}")
def get_task(gid: str):
    t = tasks.get(gid)
    if not t:
        raise HTTPException(404, "任务不存在")
    refresh_task(t)
    return task_to_dict(t)


@app.post("/api/task/{gid}/play")
def play(gid: str):
    t = tasks.get(gid)
    if not t:
        raise HTTPException(404, "任务不存在")
    refresh_task(t)
    if t.status != "complete":
        progress = t.completed_length / t.total_length if t.total_length else 0.0
        return JSONResponse(
            status_code=409,
            content={"error": "下载未完成", "progress": round(progress, 4), "status": t.status},
        )
    state = start_hls_generation(t)
    if state == "ready":
        return {"stream_path": f"/hls/{gid}/index.m3u8", "name": t.name}
    if state == "error":
        raise HTTPException(500, "未找到可播放的视频文件")
    # 后台生成中
    return JSONResponse(status_code=202, content={"status": "generating", "name": t.name})


@app.delete("/api/task/{gid}")
def delete_task(gid: str):
    t = tasks.pop(gid, None)
    dl.remove(gid)
    if t:
        shutil.rmtree(HLS_ROOT / gid, ignore_errors=True)
        for p in t.file_paths:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
    return {"ok": True}


@app.get("/hls/{gid}/{filename}")
def hls_file(gid: str, filename: str):
    t = tasks.get(gid)
    if not t:
        raise HTTPException(404, "任务不存在")
    root = (HLS_ROOT / gid).resolve()
    path = (root / filename).resolve()
    if not str(path).startswith(str(root)):
        raise HTTPException(400, "非法路径")
    if not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, media_type="application/vnd.apple.mpegurl" if filename.endswith(".m3u8") else "video/mp2t")


@app.get("/", response_class=HTMLResponse)
def index():
    html = STATIC_DIR / "index.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse("<h1>Magnet Player Server</h1><p>API 已运行。</p>")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
