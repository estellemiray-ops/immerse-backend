import io
import edge_tts

VOICE = "zh-CN-XiaoxiaoNeural"  # natural Mandarin female voice; zh-CN-YunxiNeural is a male alternative


async def synthesize(text: str) -> bytes:
    communicate = edge_tts.Communicate(text, VOICE, rate="-10%")
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()
