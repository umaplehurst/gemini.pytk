import os
from openai import AsyncOpenAI

class UsageMetadataWrapper:
    def __init__(self):
        self.total_token_count = 0

# To not create a bunch of different classes, we just do everything in this one
class ModelMetaLlamaGroq:
    def __init__(self, system_instructions):
        self.client = None
        self.messages = None
        self.model = "llama-3.3-70b-versatile"
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

        API_KEY=os.environ["GROQ_API_KEY"]
        if not API_KEY:
            raise ValueError("missing GROQ_API_KEY")

        self.client = AsyncOpenAI(api_key=API_KEY, base_url=f"https://api.groq.com/openai/v1")
        return self

    async def send_message_async(self, message):
        self.messages.append({"role": "user", "content": (message)})

        # FIXME: Need to set temperature + top_p
        # Requires change in top-level UI to render settings depending on LLM species
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
        )
        # print(self.messages)
        # print(response)

        self.text = response.choices[0].message.content
        self.usage_metadata.total_token_count = response.usage.total_tokens
        return self