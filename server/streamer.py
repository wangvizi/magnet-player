"""用 ffmpeg 把下载完成的视频转成 HLS，供 iOS AVPlayer 播放。"""
import json
import os
import subprocess
from pathlib import Path

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".ts", ".m2ts", ".webm", ".m4v",
    ".flv", ".wmv", ".mpg", ".mpeg", ".3gp", ".rmvb", ".rm",
}

# 可在 MPEG-TS 中直接封装的音频编码（-c copy 时无需转码）
TS_FRIENDLY_AUDIO = {None, "aac", "ac3", "eac3", "mp3", "mp2"}


class StreamerError(RuntimeError):
    pass


def pick_video_file(files):
    """从 aria2 返回的文件列表中挑出体积最大的视频文件。"""
    if not files:
        return None
    cands = [f for f in files if Path(f["path"]).suffix.lower() in VIDEO_EXTS]
    pool = cands or files
    pool = [f for f in pool if f.get("length")]
    if not pool:
        return None
    return max(pool, key=lambda f: int(f.get("length") or 0))


def _preferred_h264_encoder():
    """优先 libx264，缺失时回退 libopenh264；都没有则返回 None。"""
    try:
        r = subprocess.run(
            [FFMPEG, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30,
        )
        encoders = r.stdout
    except Exception:
        return None
    if "libx264" in encoders:
        return "libx264"
    if "libopenh264" in encoders:
        return "libopenh264"
    return None


def _probe(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise StreamerError(f"ffprobe 解析失败: {r.stderr[:400]}")
    return json.loads(r.stdout)


def _streams(info):
    v = a = None
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s
        elif s.get("codec_type") == "audio" and a is None:
            a = s
    return v, a


def _can_copy(v, a):
    if v is None:
        return False
    if v.get("codec_name") not in ("h264", "hevc"):
        return False
    ac = a.get("codec_name") if a else None
    return ac in TS_FRIENDLY_AUDIO


def _annexb_bsf(path, vcodec):
    ext = Path(path).suffix.lower()
    if ext in (".ts", ".m2ts", ".mts"):
        return None  # 已是 Annex-B 字节流
    if vcodec == "h264":
        return "h264_mp4toannexb"
    if vcodec == "hevc":
        return "hevc_mp4toannexb"
    return None


def generate_hls(input_path, out_dir):
    """把 input_path 转成 HLS（index.m3u8 + seg_*.ts）。

    优先无损封装（-c copy，速度快）；编码不兼容时回退为转码 H.264/AAC。
    """
    input_path = Path(input_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    playlist = out_dir / "index.m3u8"

    info = _probe(input_path)
    v, a = _streams(info)
    vcodec = v.get("codec_name") if v else None

    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path), "-sn", "-map", "0:v:0",
    ]
    if a is not None:
        cmd += ["-map", "0:a:0"]

    if _can_copy(v, a):
        cmd += ["-c:v", "copy"]
        if a is not None:
            cmd += ["-c:a", "copy"]
        bsf = _annexb_bsf(input_path, vcodec)
        if bsf:
            cmd += ["-bsf:v", bsf]
    else:
        enc = _preferred_h264_encoder()
        if enc is None:
            raise StreamerError("ffmpeg 缺少 H.264 编码器（libx264），请安装完整版 ffmpeg")
        if enc == "libx264":
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "libopenh264", "-b:v", "2000k", "-pix_fmt", "yuv420p"]
        if a is not None:
            cmd += ["-c:a", "aac", "-b:a", "128k"]
        else:
            cmd += ["-an"]

    cmd += [
        "-f", "hls", "-hls_time", "6", "-hls_list_size", "0",
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(out_dir / "seg_%05d.ts"),
        str(playlist),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8 * 3600)
    if proc.returncode != 0:
        raise StreamerError(f"ffmpeg 转码失败: {proc.stderr[-800:]}")
    if not playlist.exists():
        raise StreamerError("ffmpeg 未产出 HLS 文件")
    return playlist
