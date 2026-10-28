"""
Ses dönüştürme sunucusu (iki kişilik oda).
Çalıştırma:  pip install fastapi uvicorn numpy
             uvicorn server:app --host 0.0.0.0 --port 8000

Akış: Telefon A mikrofonu -> sunucu (convert) -> Telefon B hoparlörü
Sadece arayanın KENDİ mikrofonu işlenir. Kayıt/saklama yoktur, ses hiçbir yere yazılmaz.
Ses formatı: 16 kHz, mono, Int16 PCM, 640 örnek (40 ms) parçalar.
"""
import struct
import zlib

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response

app = FastAPI()
rooms: dict[str, dict[str, WebSocket]] = {}


class VoiceConverter:
    """Yapay zekâ modelinin takılacağı yer.
    voice: 'male' veya 'female' (yalnızca bu iki hedef ses desteklenir).

    ŞU AN: sesi aynen geçirir (hat testi için).
    SONRAKİ ADIM: RVC / benzeri gerçek zamanlı model buraya bağlanır:
        self.model.infer(chunk, target=voice)
    """

    SUPPORTED = {"male", "female"}

    def convert(self, pcm: np.ndarray, voice: str) -> np.ndarray:
        if voice not in self.SUPPORTED:
            return np.zeros_like(pcm)  # tanımsız ses: hiçbir şey geçmez
        return pcm  # TODO: model çıkarımı


converter = VoiceConverter()


def make_icon(size: int) -> bytes:
    """Yeşil zemin üzerine beyaz daire: basit PNG simgesi (ek dosya gerekmez)."""
    cx = cy = size / 2
    r2 = (size * 0.38) ** 2
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            inside = (x - cx) ** 2 + (y - cy) ** 2 < r2
            row += b"\xff\xff\xff" if inside else b"\x2e\x7d\x32"
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


ICONS = {192: make_icon(192), 512: make_icon(512)}

MANIFEST = {
    "name": "Ses Arama",
    "short_name": "Ses Arama",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#111111",
    "theme_color": "#2e7d32",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    ],
}

SERVICE_WORKER = "self.addEventListener('fetch', () => {});"


@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/manifest.json")
def manifest():
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@app.get("/sw.js")
def sw():
    return Response(SERVICE_WORKER, media_type="application/javascript")


@app.get("/icon-{size}.png")
def icon(size: int):
    return Response(ICONS.get(size, ICONS[192]), media_type="image/png")


@app.websocket("/ws/{room}")
async def ws(websocket: WebSocket, room: str, voice: str = "male"):
    await websocket.accept()
    peers = rooms.setdefault(room, {})
    if len(peers) >= 2:
        await websocket.close(code=1008)
        return
    me = str(id(websocket))
    peers[me] = websocket
    try:
        while True:
            data = await websocket.receive_bytes()
            pcm = np.frombuffer(data, dtype=np.int16)
            out = converter.convert(pcm, voice).astype(np.int16).tobytes()
            for pid, peer in list(peers.items()):
                if pid != me:
                    await peer.send_bytes(out)
    except WebSocketDisconnect:
        pass
    finally:
        peers.pop(me, None)
        if not peers:
            rooms.pop(room, None)
