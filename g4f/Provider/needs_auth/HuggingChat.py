from __future__ import annotations

import json
import re
import os
import requests
from typing import AsyncIterator

try:
    from curl_cffi.requests import Session, CurlMime
    has_curl_cffi = True
except ImportError:
    has_curl_cffi = False

from ..base_provider import ProviderModelMixin, AsyncAuthedProvider, AuthResult
from ..helper import format_prompt
from ...typing import AsyncResult, Messages, Cookies
from ...errors import MissingRequirementsError, MissingAuthError, ResponseError
from ...requests import get_args_from_nodriver, DEFAULT_HEADERS
from ...requests.raise_for_status import raise_for_status
from ...providers.response import JsonConversation, ImageResponse, Sources, TitleGeneration, Reasoning, RequestLogin
from ...cookies import get_cookies
from ... import debug

class Conversation(JsonConversation):
    def __init__(self, models: dict):
        self.models: dict = models

class HuggingChat(AsyncAuthedProvider, ProviderModelMixin):
    url = "https://huggingface.co/chat"
    
    working = True
    supports_stream = True
    needs_auth = True
    
    default_model = "Qwen/Qwen2.5-72B-Instruct"
    default_image_model = "black-forest-labs/FLUX.1-dev"
    image_models = [    
       default_image_model,
        "black-forest-labs/FLUX.1-schnell",
    ]
    fallback_models = [
        default_model,
        'meta-llama/Llama-3.3-70B-Instruct',
        'CohereForAI/c4ai-command-r-plus-08-2024',
        'Qwen/QwQ-32B-Preview',
        'nvidia/Llama-3.1-Nemotron-70B-Instruct-HF',
        'Qwen/Qwen2.5-Coder-32B-Instruct',
        'meta-llama/Llama-3.2-11B-Vision-Instruct',
        'mistralai/Mistral-Nemo-Instruct-2407',
        'microsoft/Phi-3.5-mini-instruct',
    ] + image_models
    model_aliases = {
        ### Chat ###
        "qwen-2.5-72b": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "llama-3.3-70b": "meta-llama/Llama-3.3-70B-Instruct",
        "command-r-plus": "CohereForAI/c4ai-command-r-plus-08-2024",
        "qwq-32b": "Qwen/QwQ-32B-Preview",
        "nemotron-70b": "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        "qwen-2.5-coder-32b": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "llama-3.2-11b": "meta-llama/Llama-3.2-11B-Vision-Instruct",
        "mistral-nemo": "mistralai/Mistral-Nemo-Instruct-2407",
        "phi-3.5-mini": "microsoft/Phi-3.5-mini-instruct",

        ### Image ###
        "flux-dev": "black-forest-labs/FLUX.1-dev",
        "flux-schnell": "black-forest-labs/FLUX.1-schnell",
    }

    @classmethod
    def get_models(cls):
        if not cls.models:
            try:
                text = requests.get(cls.url).text
                text = re.sub(r',parameters:{[^}]+?}', '', text)
                text = re.search(r'models:(\[.+?\]),oldModels:', text).group(1)
                text = text.replace('void 0', 'null')
                def add_quotation_mark(match):
                    return f'{match.group(1)}"{match.group(2)}":'
                text = re.sub(r'([{,])([A-Za-z0-9_]+?):', add_quotation_mark, text)
                models = json.loads(text)
                cls.text_models = [model["id"] for model in models] 
                cls.models = cls.text_models + cls.image_models
                cls.vision_models = [model["id"] for model in models if model["multimodal"]]
            except Exception as e:
                debug.log(f"HuggingChat: Error reading models: {type(e).__name__}: {e}")
                cls.models = [*cls.fallback_models]
        return cls.models

    @classmethod
    async def on_auth_async(cls, cookies: Cookies = None, proxy: str = None, **kwargs) -> AsyncIterator:
        if cookies is None:
            cookies = get_cookies("huggingface.co")
        if "hf-chat" in cookies:
            yield AuthResult(
                cookies=cookies,
                impersonate="chrome",
                headers=DEFAULT_HEADERS
            )
            return
        login_url = os.environ.get("G4F_LOGIN_URL")
        if login_url:
            yield RequestLogin(cls.__name__, login_url)
        yield AuthResult(
            **await get_args_from_nodriver(
                cls.url,
                proxy=proxy,
                wait_for='form[action="/chat/logout"]'
            )
        )

    @classmethod
    async def create_authed(
        cls,
        model: str,
        messages: Messages,
        auth_result: AuthResult,
        prompt: str = None,
        return_conversation: bool = False,
        conversation: Conversation = None,
        web_search: bool = False,
        **kwargs
    ) -> AsyncResult:
        if not has_curl_cffi:
            raise MissingRequirementsError('Install "curl_cffi" package | pip install -U curl_cffi')
        model = cls.get_model(model)

        session = Session(**auth_result.get_dict())

        if conversation is None or not hasattr(conversation, "models"):
            conversation = Conversation({})

        if model not in conversation.models:
            conversationId = cls.create_conversation(session, model)
            messageId = cls.fetch_message_id(session, conversationId)
            conversation.models[model] = {"conversationId": conversationId, "messageId": messageId}
            if return_conversation:
                yield conversation
            inputs = format_prompt(messages)
        else:
            conversationId = conversation.models[model]["conversationId"]
            conversation.models[model]["messageId"] = cls.fetch_message_id(session, conversationId)
            inputs = messages[-1]["content"]

        debug.log(f"Use: {json.dumps(conversation.models[model])}")

        settings = {
            "inputs": inputs,
            "id": conversation.models[model]["messageId"],
            "is_retry": False,
            "is_continue": False,
            "web_search": web_search,
            "tools": ["000000000000000000000001"] if model in cls.image_models else [],
        }

        headers = {
            'accept': '*/*',
            'accept-language': 'en',
            'cache-control': 'no-cache',
            'origin': 'https://huggingface.co',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': f'https://huggingface.co/chat/conversation/{conversationId}',
            'sec-ch-ua': '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        }

        data = CurlMime()
        data.addpart('data', data=json.dumps(settings, separators=(',', ':')))

        response = session.post(
            f'https://huggingface.co/chat/conversation/{conversationId}',
            cookies=session.cookies,
            headers=headers,
            multipart=data,
            stream=True
        )
        raise_for_status(response)

        sources = None
        for line in response.iter_lines():
            if not line:
                continue
            try:
                line = json.loads(line)
            except json.JSONDecodeError as e:
                debug.log(f"Failed to decode JSON: {line}, error: {e}")
                continue
            if "type" not in line:
                raise RuntimeError(f"Response: {line}")
            elif line["type"] == "stream":
                yield line["token"].replace('\u0000', '')
            elif line["type"] == "finalAnswer":
                break
            elif line["type"] == "file":
                url = f"https://huggingface.co/chat/conversation/{conversationId}/output/{line['sha']}"
                prompt = messages[-1]["content"] if prompt is None else prompt
                yield ImageResponse(url, alt=prompt, options={"cookies": cookies})
            elif line["type"] == "webSearch" and "sources" in line:
                sources = Sources(line["sources"])
            elif line["type"] == "title":
                yield TitleGeneration(line["title"])
            elif line["type"] == "reasoning":
                yield Reasoning(line.get("token"), line.get("status"))
            else:
                pass #print(line)

        if sources is not None:
            yield sources

    @classmethod
    def create_conversation(cls, session: Session, model: str):
        if model in cls.image_models:
            model = cls.default_model
        json_data = {
            'model': model,
        }
        response = session.post('https://huggingface.co/chat/conversation', json=json_data)
        if response.status_code == 401:
            raise MissingAuthError(response.text)
        raise_for_status(response)
        return response.json().get('conversationId')

    @classmethod
    def fetch_message_id(cls, session: Session, conversation_id: str):
        # Get the data response and parse it properly
        response = session.get(f'https://huggingface.co/chat/conversation/{conversation_id}/__data.json?x-sveltekit-invalidated=11')
        raise_for_status(response)

        # Split the response content by newlines and parse each line as JSON
        try:
            json_data = None
            for line in response.text.split('\n'):
                if line.strip():
                    try:
                        parsed = json.loads(line)
                        if isinstance(parsed, dict) and "nodes" in parsed:
                            json_data = parsed
                            break
                    except json.JSONDecodeError:
                        continue
                        
            if not json_data:
                raise RuntimeError("Failed to parse response data")

            if json_data["nodes"][-1]["type"] == "error":
                if json_data["nodes"][-1]["status"] == 403:
                    raise MissingAuthError(json_data["nodes"][-1]["error"]["message"])
                raise ResponseError(json.dumps(json_data["nodes"][-1]))

            data = json_data["nodes"][1]["data"]
            keys = data[data[0]["messages"]]
            message_keys = data[keys[-1]]
            return data[message_keys["id"]]

        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Failed to extract message ID: {str(e)}")
