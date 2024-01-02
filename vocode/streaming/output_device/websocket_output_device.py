from __future__ import annotations

from pydub import AudioSegment
import asyncio
import io
import base64
from fastapi import WebSocket
from vocode.streaming.models.audio_encoding import AudioEncoding
from vocode.streaming.output_device.base_output_device import BaseOutputDevice
from vocode.streaming.models.websocket import AudioMessage
from vocode.streaming.models.websocket import TranscriptMessage
from vocode.streaming.models.transcript import TranscriptEvent



class WebsocketOutputDevice(BaseOutputDevice):
    def __init__(
        self, ws: WebSocket, sampling_rate: int, audio_encoding: AudioEncoding
    ):
        super().__init__(sampling_rate, audio_encoding)
        self.ws = ws
        self.active = False
        self.queue: asyncio.Queue[str] = asyncio.Queue()

    # TODO: Edit to send raw data instead of mp3
    # Github issue:
    #
    # audio is delayed and often cut off
    # we need to send the raw audio data instead of converting to mp3, this may be the cause of the delay. 
    # maybe there is some data being cut off when converting to mp3    
    
    def convert_to_mp3(self, chunk: bytes) -> bytes:
            audio = AudioSegment.from_raw(io.BytesIO(chunk), 
                                        sample_width=2,
                                        frame_rate=self.sampling_rate, 
                                        channels=1) 
            buffer = io.BytesIO()
            audio.export(buffer, format="mp3")
            return buffer.getvalue()

    def consume_nonblocking(self, chunk: bytes):
        if self.active:
            mp3_data = self.convert_to_mp3(chunk)
            base64_encoded_mp3 = base64.b64encode(mp3_data).decode('utf-8')
            audio_message = AudioMessage(data=base64_encoded_mp3)
            self.queue.put_nowait(audio_message.json())

    def start(self):
        self.active = True
        self.process_task = asyncio.create_task(self.process())

    def mark_closed(self):
        self.active = False

    async def process(self):
        while self.active:
            message = await self.queue.get()
            await self.ws.send(message)

    def consume_transcript(self, event: TranscriptEvent):
        if self.active:
            transcript_message = TranscriptMessage.from_event(event)
            self.queue.put_nowait(transcript_message.json())

    def terminate(self):
        self.process_task.cancel()
