from __future__ import annotations

import json
import uuid

from ...typing import AsyncResult, Messages, Cookies, ImagesType
from ..base_provider import AsyncGeneratorProvider, ProviderModelMixin
from ..helper import format_prompt, format_image_prompt
from ...providers.response import JsonConversation
from ...requests.aiohttp import StreamSession, StreamResponse, FormData
from ...requests.raise_for_status import raise_for_status
from ...image import to_bytes, is_accepted_format, is_data_an_wav
from ...errors import ResponseError
from ... import debug
from .Janus_Pro_7B import get_zerogpu_token
from .raise_for_status import raise_for_status

class Phi_4(AsyncGeneratorProvider, ProviderModelMixin):
    space = "microsoft/phi-4-multimodal"
    url = f"https://huggingface.co/spaces/{space}"
    api_url = "https://microsoft-phi-4-multimodal.hf.space"
    referer = f"{api_url}?__theme=light"

    working = True
    supports_stream = True
    supports_system_message = True
    supports_message_history = True

    default_model = "phi-4-multimodal"
    default_vision_model = default_model
    models = [default_model]

    @classmethod
    def run(cls, method: str, session: StreamSession, prompt: str, conversation: JsonConversation, images: list = None):
            headers = {
                "content-type": "application/json",
                "x-zerogpu-token": conversation.zerogpu_token,
                "x-zerogpu-uuid": conversation.zerogpu_uuid,
                "referer": cls.referer,
            }
            if method == "predict":
                return session.post(f"{cls.api_url}/gradio_api/run/predict", **{
                    "headers": {k: v for k, v in headers.items() if v is not None},
                    "json": {
                        "data":[
                            [],
                            {
                                "text": prompt,
                                "files": images,
                            },
                            None
                        ],
                        "event_data": None,
                        "fn_index": 10,
                        "trigger_id": 8,
                        "session_hash": conversation.session_hash
                    },
                })
            if method == "post":
                return session.post(f"{cls.api_url}/gradio_api/queue/join?__theme=light", **{
                    "headers": {k: v for k, v in headers.items() if v is not None},
                    "json": {
                        "data": [[
                                {
                                "role": "user",
                                "content": prompt,
                                }
                            ]] + [[
                                {
                                    "role": "user",
                                    "content": {"file": image}
                                } for image in images
                            ]],
                        "event_data": None,
                        "fn_index": 11,
                        "trigger_id": 8,
                        "session_hash": conversation.session_hash
                    },
                })
            return session.get(f"{cls.api_url}/gradio_api/queue/data?session_hash={conversation.session_hash}", **{
                "headers": {
                    "accept": "text/event-stream",
                    "content-type": "application/json",
                    "referer": cls.referer,
                }
            })

    @classmethod
    async def create_async_generator(
        cls,
        model: str,
        messages: Messages,
        images: ImagesType = None,
        prompt: str = None,
        proxy: str = None,
        cookies: Cookies = None,
        api_key: str = None,
        zerogpu_uuid: str = "[object Object]",
        return_conversation: bool = False,
        conversation: JsonConversation = None,
        **kwargs
    ) -> AsyncResult:
        prompt = format_prompt(messages) if prompt is None and conversation is None else prompt
        prompt = format_image_prompt(messages, prompt)

        session_hash = uuid.uuid4().hex if conversation is None else getattr(conversation, "session_hash", uuid.uuid4().hex)
        async with StreamSession(proxy=proxy, impersonate="chrome") as session:
            if api_key is None:
                zerogpu_uuid, api_key = await get_zerogpu_token(cls.space, session, conversation, cookies)
            if conversation is None or not hasattr(conversation, "session_hash"):
                conversation = JsonConversation(session_hash=session_hash, zerogpu_token=api_key, zerogpu_uuid=zerogpu_uuid)
            else:
                conversation.zerogpu_token = api_key
            if return_conversation:
                yield conversation

            if images is not None:
                data = FormData()
                mimi_types = [None for i in range(len(images))]
                for i in range(len(images)):
                    mimi_types[i] = is_data_an_wav(images[i][0], images[i][1])
                    images[i] = (to_bytes(images[i][0]), images[i][1])
                for image, image_name in images:
                    data.add_field(f"files", to_bytes(image), filename=image_name)
                async with session.post(f"{cls.api_url}/gradio_api/upload", params={"upload_id": session_hash}, data=data) as response:
                    await raise_for_status(response)
                    image_files = await response.json()
                images = [{
                    "path": image_file,
                    "url": f"{cls.api_url}/gradio_api/file={image_file}",
                    "orig_name": images[i][1],
                    "size": len(images[i][0]),
                    "mime_type": mimi_types[i] or is_accepted_format(images[i][0]),
                    "meta": {
                        "_type": "gradio.FileData"
                    }
                } for i, image_file in enumerate(image_files)]
            
            
            async with cls.run("predict", session, prompt, conversation, images) as response:
                await raise_for_status(response)

            async with cls.run("post", session, prompt, conversation, images) as response:
                await raise_for_status(response)

            async with cls.run("get", session, prompt, conversation) as response:
                response: StreamResponse = response
                async for line in response.iter_lines():
                    if line.startswith(b'data: '):
                        try:
                            json_data = json.loads(line[6:])
                            if json_data.get('msg') == 'process_completed':
                                if 'output' in json_data and 'error' in json_data['output']:
                                    raise ResponseError("Missing images input" if json_data['output']['error'] and "AttributeError" in json_data['output']['error'] else json_data['output']['error'])
                                if 'output' in json_data and 'data' in json_data['output']:
                                    yield json_data['output']['data'][0][-1]["content"]
                                break

                        except json.JSONDecodeError:
                            debug.log("Could not parse JSON:", line.decode(errors="replace"))