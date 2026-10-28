"""
Ses dönüştürme sunucusu (iki kişilik oda).
Çalıştırma:  pip install fastapi uvicorn numpy
             uvicorn server:app --host 0.0.0.0 --port 8000

Akış: Telefon A mikrofonu -> sunucu (convert) -> Telefon B hoparlörü
Sadece arayanın KENDİ mikrofonu işlenir. Kayıt/saklama yoktur, ses hiçbir yere yazılmaz.
Ses formatı: 16 kHz, mono, Int16 PCM, 640 örnek (40 ms) parçalar.
"""
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

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


@app.get("/")
def index():
    return FileResponse("index.html")


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
