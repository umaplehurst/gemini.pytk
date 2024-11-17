import os

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from openai import AsyncOpenAI

class UsageMetadataWrapper:
    def __init__(self):
        self.total_token_count = 0

# To not create a bunch of different classes, we just do everything in this one
class ModelMetaLlamaVertexAI:
    def __init__(self, system_instructions):
        self.client = None
        self.messages = None
        self.model = "meta/llama-3.1-405b-instruct-maas"
        self.system_instructions = system_instructions

        # Reply properties
        self.text = None
        self.usage_metadata = UsageMetadataWrapper()

        # Authentication object
        self.credentials = None

    def generate_chat_session(self, history):
        self.messages = []
        if self.system_instructions:
            self.messages.append(
                {
                    "role": "system",
                    "content": (self.system_instructions),
                }
            )

        for i in history:
            # Text only!
            if len(i["parts"]) == 1 and isinstance(i["parts"][0], str):
                self.messages.append({"role": i["role"], "content": (i["parts"][0])})
            else:
                # Unsupported content
                print("!!! message ignored --", i)
            to_copy = ["role", "parts"]

        if not self.credentials:
            json_path = os.environ["GOOGLE_VERTEX_AI_JSON"]
            if not json_path:
                raise ValueError("missing GOOGLE_VERTEX_AI_JSON")

            AUTH_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
            self.credentials = service_account.Credentials.from_service_account_file(os.environ["GOOGLE_VERTEX_AI_JSON"], scopes=AUTH_SCOPES)

        self.credentials.refresh(Request())
        access_token = self.credentials.token

        ENDPOINT=os.environ["GOOGLE_VERTEX_AI_MAAS_ENDPOINT"]
        if not ENDPOINT:
            raise ValueError("missing ENDPOINT")

        PROJECT_ID=os.environ["GOOGLE_VERTEX_AI_MAAS_PROJECT_ID"]
        if not PROJECT_ID:
            raise ValueError("missing PROJECT_ID")

        REGION=os.environ["GOOGLE_VERTEX_AI_MAAS_REGION"]
        if not REGION:
            raise ValueError("missing REGION")

        self.client = AsyncOpenAI(api_key=access_token, base_url=f"https://{ENDPOINT}/v1/projects/{PROJECT_ID}/locations/{REGION}/endpoints/openapi")
        return self

    async def send_message_async(self, message):
        self.messages.append({"role": "user", "content": (message)})

        # FIXME: Need to set temperature + top_p
        # Requires change in top-level UI to render settings depending on LLM species
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            extra_body={
                "extra_body": {
                    "google": {
                        "model_safety_settings": {
                            "enabled": False, # True,
                            "llama_guard_settings": {},
                        }
                    }
                }
            }
        )
        # print(self.messages)
        # print(response)

        self.text = response.choices[0].message.content
        self.usage_metadata.total_token_count = response.usage.total_tokens
        return self