import base64
import threading

import httpx

from .index import validate_vector


def embedding_identity(settings):
    return f'{settings.embedding_model}@{settings.embedding_revision}:768'


class Embedder:
    def __init__(self, settings):
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def encode(self, text, *, query=False):
        with self._lock:
            if self._model is None:
                import torch
                from sentence_transformers import SentenceTransformer
                device = self.settings.embedding_device
                dtype = torch.bfloat16 if device.startswith('cuda') and torch.cuda.is_bf16_supported() else torch.float32
                self._model = SentenceTransformer(self.settings.embedding_model,
                    revision=self.settings.embedding_revision, device=device, trust_remote_code=False,
                    config_kwargs={'vision_config': None, 'audio_config': None},
                    model_kwargs={'torch_dtype': dtype})
            vector = self._model.encode(text, prompt_name='SearchQuery' if query else 'Document',
                normalize_embeddings=True, show_progress_bar=False)
            return validate_vector(vector.tolist())


class Captioner:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def caption(self, path):
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Segment exceeds the caption request size limit; use shorter segments')
        video = 'data:video/mp4;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
        headers = {'Authorization': 'Bearer ' + self.settings.cosmos_api_key} if self.settings.cosmos_api_key else {}
        with httpx.Client(timeout=self.settings.model_timeout, transport=self.transport, trust_env=False) as client:
            response = client.post(self.settings.cosmos_url.rstrip('/') + '/chat/completions', headers=headers,
                json={'model': self.settings.cosmos_model, 'temperature': 0, 'max_tokens': 4096,
                      'mm_processor_kwargs': {'fps': 4, 'do_sample_frames': True},
                      'messages': [{'role': 'user', 'content': [
                          {'type': 'video_url', 'video_url': {'url': video}},
                          {'type': 'text', 'text': 'Describe the visible animals and their observable movements and interactions in this clip. Identify species only when supported. State uncertainty. Do not invent intent, timestamps, or unseen actions. Return only the final factual caption, without reasoning tags.'}]}]})
            response.raise_for_status()
            choice = response.json()['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise ValueError('Incomplete Cosmos caption')
            caption = choice['message']['content']
            if not isinstance(caption, str):
                raise ValueError('Invalid Cosmos caption')
            if '</think>' in caption:
                caption = caption.split('</think>', 1)[1]
            caption = caption.strip()
            if not caption or len(caption) > 16000 or '<think>' in caption:
                raise ValueError('Invalid Cosmos caption')
            return caption
