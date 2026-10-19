"""aria2 下载引擎封装（JSON-RPC over HTTP）。"""
import os
import subprocess
import time
import uuid
from pathlib import Path

import requests


class Aria2Error(RuntimeError):
    pass


class Aria2Downloader:
    def __init__(self, host="127.0.0.1", port=6800, secret="", download_dir=None):
        self.host = host
        self.port = port
        self.secret = secret or ""
        self.download_dir = download_dir or str(Path.cwd() / "data" / "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        self.url = f"http://{self.host}:{self.port}/jsonrpc"
        self.proc = None
        self.session_file = os.path.join(self.download_dir, "aria2.session")

    def start(self):
        if not os.path.exists(self.session_file):
            Path(self.session_file).touch()

        args = [
            "aria2c",
            "--enable-rpc",
            "--rpc-listen-all=false",
            f"--rpc-listen-port={self.port}",
            f"--dir={self.download_dir}",
            "--seed-time=0",
            "--bt-max-peers=100",
            "--bt-request-peer-speed-limit=512K",
            "--max-concurrent-downloads=5",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=1M",
            "--file-allocation=none",
            "--enable-dht=true",
            "--dht-listen-port=6881-6999",
            "--listen-port=6881-6999",
            "--bt-enable-lpd=true",
            "--follow-torrent=mem",
            "--bt-save-metadata=true",
            "--allow-overwrite=true",
            "--disable-ipv6",
            "--save-session=" + self.session_file,
            "--input-file=" + self.session_file,
            "--log=-",
        ]
        if self.secret:
            args.append("--rpc-secret=" + self.secret)

        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # 等待 RPC 就绪
        for _ in range(100):
            try:
                self.rpc("aria2.getVersion", self._params([]))
                return
            except Exception:
                time.sleep(0.1)
        raise Aria2Error("aria2 RPC 启动失败")

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def rpc(self, method, params, timeout=60):
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        try:
            r = requests.post(self.url, json=payload, timeout=timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise Aria2Error(f"aria2 连接失败: {e}") from e
        data = r.json()
        if "error" in data:
            raise Aria2Error(f"aria2 错误: {data['error']}")
        return data.get("result")

    def _params(self, extra):
        p = []
        if self.secret:
            p.append("token:" + self.secret)
        p.extend(extra)
        return p

    def add_magnet(self, magnet):
        return self.rpc(
            "aria2.addUri", self._params([[magnet], {"seed-time": "0"}])
        )

    def add_torrent(self, b64_torrent):
        return self.rpc(
            "aria2.addTorrent", self._params([b64_torrent, [], {"seed-time": "0"}])
        )

    def status(self, gid):
        keys = [
            "gid", "status", "totalLength", "completedLength", "downloadSpeed",
            "uploadSpeed", "numSeeders", "connections", "errorCode",
            "errorMessage", "files", "bittorrent", "dir", "followedBy",
        ]
        return self.rpc("aria2.tellStatus", self._params([gid, keys]))

    def list_all(self):
        out = []
        keys = [
            "gid", "status", "totalLength", "completedLength", "downloadSpeed",
            "files", "bittorrent", "dir",
        ]
        for m in ("aria2.tellActive", "aria2.tellWaiting", "aria2.tellStopped"):
            try:
                out.extend(self.rpc(m, self._params([keys])))
            except Aria2Error:
                pass
        return out

    def remove(self, gid):
        try:
            return self.rpc("aria2.remove", self._params([gid]))
        except Aria2Error:
            try:
                return self.rpc("aria2.forceRemove", self._params([gid]))
            except Aria2Error:
                return None

    def remove_download_result(self, gid):
        """移除任务并删除已下载的文件。"""
        try:
            return self.rpc("aria2.removeDownloadResult", self._params([gid]))
        except Aria2Error:
            return self.remove(gid)
