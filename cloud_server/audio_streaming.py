"""Project Claw 端到端语音流式响应系统 - cloud_server/audio_streaming.py"""
import asyncio, logging, json, time, uuid, base64
from typing import Dict, List, Optional, AsyncGenerator, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np
import httpx

logger = logging.getLogger(__name__)

class AudioFormat(str, Enum):
    PCM_16K = "pcm_16k"
    PCM_24K = "pcm_24k"
    OPUS = "opus"
    AAC = "aac"

class AudioStreamState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    PLAYING = "playing"
    ERROR = "error"

@dataclass
class AudioChunk:
    chunk_id: str
    session_id: str
    timestamp: float
    audio_data: bytes
    sample_rate: int
    channels: int
    duration_ms: int
    is_final: bool = False

@dataclass
class AudioStreamConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_ms: int = 100
    format: AudioFormat = AudioFormat.PCM_16K
    vad_enabled: bool = True
    echo_cancellation: bool = True

class AudioProcessor:
    def __init__(self, config: AudioStreamConfig):
        self.config = config
        self.buffer = bytearray()
    
    def add_audio_chunk(self, audio_data: bytes) -> None:
        self.buffer.extend(audio_data)
    
    def get_audio_chunk(self, chunk_size: int) -> Optional[bytes]:
        if len(self.buffer) >= chunk_size:
            chunk = bytes(self.buffer[:chunk_size])
            del self.buffer[:chunk_size]
            return chunk
        return None
    
    def detect_speech_activity(self, audio_data: bytes) -> bool:
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            energy = np.sqrt(np.mean(audio_array ** 2))
            threshold = 500
            return energy > threshold
        except Exception as e:
            logger.error(f"VAD 检测失败: {e}")
            return True
    
    def apply_echo_cancellation(self, audio_data: bytes) -> bytes:
        try:
            return audio_data
        except Exception as e:
            logger.error(f"回声消除失败: {e}")
            return audio_data
    
    def resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        try:
            if from_rate == to_rate:
                return audio_data
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            ratio = to_rate / from_rate
            new_length = int(len(audio_array) * ratio)
            indices = np.linspace(0, len(audio_array) - 1, new_length)
            resampled = np.interp(indices, np.arange(len(audio_array)), audio_array)
            resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
            return resampled.tobytes()
        except Exception as e:
            logger.error(f"重采样失败: {e}")
            return audio_data

class LLMAudioInterface:
    def __init__(self, api_key: str, model: str = "gpt-4o-audio-preview"):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=None)
        self.base_url = "https://api.openai.com/v1"
    
    async def process_audio_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        system_prompt: str,
        session_id: str
    ) -> AsyncGenerator[Tuple[bytes, Dict[str, Any]], None]:
        try:
            logger.info(f"开始处理音频流: {session_id}")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            request_body = {
                "model": self.model,
                "modalities": ["text", "audio"],
                "audio": {"voice": "alloy", "format": "pcm16"},
                "system": system_prompt,
                "messages": []
            }
            
            audio_chunks = []
            async for chunk in audio_stream:
                audio_chunks.append(chunk)
            
            full_audio = b"".join(audio_chunks)
            audio_base64 = base64.b64encode(full_audio).decode()
            
            request_body["messages"] = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_base64, "format": "pcm16"}
                        }
                    ]
                }
            ]
            
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=request_body,
                stream=True
            )
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data)
                        if "choices" in chunk_data:
                            choice = chunk_data["choices"][0]
                            if "delta" in choice and "audio" in choice["delta"]:
                                audio_chunk = choice["delta"]["audio"]
                                audio_bytes = base64.b64decode(audio_chunk)
                                metadata = {
                                    "session_id": session_id,
                                    "timestamp": time.time(),
                                    "chunk_id": str(uuid.uuid4())
                                }
                                yield audio_bytes, metadata
                    except json.JSONDecodeError:
                        continue
            
            logger.info(f"音频流处理完成: {session_id}")
        except Exception as e:
            logger.error(f"处理音频流失败: {e}")
            raise

class LocalLLMAudioInterface:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=None)
    
    async def transcribe_audio(self, audio_data: bytes) -> str:
        try:
            logger.info("转录音频...")
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = await self.client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files={"file": ("audio.wav", audio_data)},
                data={"model": "whisper-1"}
            )
            result = response.json()
            text = result.get("text", "")
            logger.info(f"转录完成: {text}")
            return text
        except Exception as e:
            logger.error(f"转录失败: {e}")
            return ""
    
    async def generate_audio_response(self, text: str, voice: str = "alloy") -> AsyncGenerator[bytes, None]:
        try:
            logger.info(f"生成音频响应: {text}")
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = await self.client.post(
                "https://api.openai.com/v1/audio/speech",
                headers=headers,
                json={"model": "tts-1", "input": text, "voice": voice, "response_format": "pcm"}
            )
            chunk_size = 4096
            async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                yield chunk
            logger.info("音频生成完成")
        except Exception as e:
            logger.error(f"生成音频失败: {e}")

class AudioStreamManager:
    def __init__(self, config: AudioStreamConfig):
        self.config = config
        self.processor = AudioProcessor(config)
        self.sessions: Dict[str, Dict[str, Any]] = {}
    
    async def create_session(self, session_id: str, llm_interface: LLMAudioInterface, system_prompt: str) -> None:
        self.sessions[session_id] = {
            "state": AudioStreamState.IDLE,
            "llm_interface": llm_interface,
            "system_prompt": system_prompt,
            "audio_chunks": [],
            "created_at": time.time(),
            "last_activity": time.time()
        }
        logger.info(f"创建音频流会话: {session_id}")
    
    async def add_audio_chunk(self, session_id: str, audio_data: bytes, is_final: bool = False) -> None:
        if session_id not in self.sessions:
            logger.warning(f"会话不存在: {session_id}")
            return
        
        session = self.sessions[session_id]
        session["last_activity"] = time.time()
        
        if self.config.echo_cancellation:
            audio_data = self.processor.apply_echo_cancellation(audio_data)
        
        if self.config.vad_enabled:
            has_speech = self.processor.detect_speech_activity(audio_data)
            if not has_speech and not is_final:
                return
        
        session["audio_chunks"].append(audio_data)
        logger.info(f"添加音频块: {session_id} ({len(audio_data)} bytes)")
    
    async def process_audio_stream(self, session_id: str) -> AsyncGenerator[Tuple[bytes, Dict[str, Any]], None]:
        if session_id not in self.sessions:
            logger.warning(f"会话不存在: {session_id}")
            return
        
        session = self.sessions[session_id]
        session["state"] = AudioStreamState.PROCESSING
        
        try:
            full_audio = b"".join(session["audio_chunks"])
            
            async def audio_stream_generator():
                chunk_size = self.config.sample_rate * self.config.chunk_duration_ms // 1000 * 2
                for i in range(0, len(full_audio), chunk_size):
                    yield full_audio[i:i + chunk_size]
            
            llm_interface = session["llm_interface"]
            system_prompt = session["system_prompt"]
            
            async for audio_chunk, metadata in llm_interface.process_audio_stream(
                audio_stream_generator(),
                system_prompt,
                session_id
            ):
                session["state"] = AudioStreamState.PLAYING
                yield audio_chunk, metadata
            
            session["state"] = AudioStreamState.IDLE
            logger.info(f"音频流处理完成: {session_id}")
        except Exception as e:
            session["state"] = AudioStreamState.ERROR
            logger.error(f"处理音频流失败: {e}")
    
    async def close_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"关闭音频流会话: {session_id}")
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        return {
            "session_id": session_id,
            "state": session["state"].value,
            "audio_chunks": len(session["audio_chunks"]),
            "created_at": session["created_at"],
            "last_activity": session["last_activity"],
            "uptime": time.time() - session["created_at"]
        }
