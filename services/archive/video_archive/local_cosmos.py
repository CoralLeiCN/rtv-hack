"""Loopback-only Cosmos Reasoner for local Transformers inference."""

import argparse
import base64
import binascii
import logging
import re
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import Settings


MAX_VIDEO_BYTES = 32 * 1024 * 1024


class CaptionRequest(BaseModel):
    model: str
    messages: list[dict]
    temperature: float = Field(default=0, ge=0, le=0)
    max_tokens: int = Field(default=4096, ge=1, le=4096)
    mm_processor_kwargs: dict = Field(default_factory=dict)


def decode_request(request, model_id):
    if request.model != model_id:
        raise ValueError('Model does not match the pinned deployment')
    if request.mm_processor_kwargs != {'fps': 4, 'do_sample_frames': True}:
        raise ValueError('Expected four-frame-per-second video sampling')
    if len(request.messages) != 1 or request.messages[0].get('role') != 'user':
        raise ValueError('Expected one user message')
    parts = request.messages[0].get('content')
    if not isinstance(parts, list) or len(parts) != 2 or not all(isinstance(p, dict) for p in parts):
        raise ValueError('Expected one video and one text prompt')
    videos = [p.get('video_url') for p in parts if p.get('type') == 'video_url']
    texts = [p.get('text') for p in parts if p.get('type') == 'text']
    if len(videos) != 1 or not isinstance(videos[0], dict) or len(texts) != 1:
        raise ValueError('Expected one video and one text prompt')
    url, prompt = videos[0].get('url'), texts[0]
    prefix = 'data:video/mp4;base64,'
    if not isinstance(url, str) or not url.startswith(prefix):
        raise ValueError('Only inline MP4 video is accepted')
    encoded = url[len(prefix):]
    if len(encoded) > 4 * ((MAX_VIDEO_BYTES + 2) // 3):
        raise ValueError('Video exceeds 32 MiB')
    try:
        video = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('Invalid video encoding') from error
    if not video or len(video) > MAX_VIDEO_BYTES:
        raise ValueError('Expected a nonempty video of at most 32 MiB')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2048:
        raise ValueError('Invalid caption prompt')
    return video, prompt


class Reasoner:
    def __init__(self, model_id, revision, device):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        if not re.fullmatch(r'[0-9a-f]{40}', revision):
            raise ValueError('Pin COSMOS_REVISION to an immutable model commit')
        repository, _, served_revision = model_id.partition('@')
        if served_revision and served_revision != revision:
            raise ValueError('Served model revision differs from COSMOS_REVISION')
        if repository not in {'nvidia/Cosmos3-Edge', 'nvidia/Cosmos3-Nano', 'nvidia/Cosmos3-Super'}:
            raise ValueError('Select an official Cosmos 3 Reasoner checkpoint')
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(repository, revision=revision, trust_remote_code=False)
        self.model = AutoModelForImageTextToText.from_pretrained(
            repository, revision=revision, trust_remote_code=False,
            device_map=device, dtype=torch.float32 if device == 'cpu' else torch.bfloat16,
            attn_implementation='sdpa',
        ).eval()

    def __call__(self, video, prompt, max_tokens):
        from transformers.video_utils import load_video

        with tempfile.TemporaryDirectory(prefix='microduck-cosmos-') as directory:
            path = Path(directory) / 'clip.mp4'
            path.write_bytes(video)
            frames, metadata = load_video(str(path), backend='pyav')
            messages = [{'role': 'user', 'content': [
                {'type': 'video', 'video': frames}, {'type': 'text', 'text': prompt},
            ]}]
            inputs = self.processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                return_tensors='pt', enable_thinking=False,
                processor_kwargs={'video_metadata': [metadata], 'fps': 4, 'do_sample_frames': True},
            ).to(self.model.device, self.model.dtype)
            with self.torch.inference_mode():
                output = self.model.generate(**inputs, do_sample=False, max_new_tokens=max_tokens)
            generated = output[0, inputs['input_ids'].shape[-1]:]
            eos = self.model.generation_config.eos_token_id
            eos = eos if isinstance(eos, list) else [eos]
            stopped = len(generated) > 0 and int(generated[-1]) in eos
            caption = self.processor.decode(generated, skip_special_tokens=True)
            return caption, 'stop' if stopped else 'length'


def create_app(model_id, revision, reasoner):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()

    @app.get('/health')
    def health():
        return {'status': 'loaded', 'revision': revision}

    @app.get('/v1/models')
    def models():
        return {'object': 'list', 'data': [{'id': model_id, 'object': 'model', 'revision': revision}]}

    @app.post('/v1/chat/completions')
    def caption(request: CaptionRequest):
        try:
            video, prompt = decode_request(request, model_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        if not lock.acquire(blocking=False):
            raise HTTPException(429, 'Local reasoner is busy')
        try:
            content, finish = reasoner(video, prompt, request.max_tokens)
            return {'model': model_id, 'choices': [{'index': 0, 'finish_reason': finish,
                    'message': {'role': 'assistant', 'content': content}}]}
        except Exception as error:
            logging.getLogger(__name__).warning('Local Cosmos inference failed (%s)', type(error).__name__)
            raise HTTPException(503, 'Local Cosmos inference failed') from None
        finally:
            lock.release()

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=['cpu', 'mps', 'cuda'], default='mps')
    parser.add_argument('--port', type=int, default=18002)
    args = parser.parse_args()
    settings = Settings.from_env()
    reasoner = Reasoner(settings.cosmos_model, settings.cosmos_revision, args.device)
    import uvicorn
    uvicorn.run(create_app(settings.cosmos_model, settings.cosmos_revision, reasoner),
                host='127.0.0.1', port=args.port, access_log=False, log_level='critical')


if __name__ == '__main__':
    main()
