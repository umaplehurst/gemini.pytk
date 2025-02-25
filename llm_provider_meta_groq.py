from llm_provider import LLMProvider, ModelOption
from knob_factory import KnobFactory
from typing import Dict, List, Any, Optional

import os
from openai import AsyncOpenAI

class UsageMetadataWrapper:
    def __init__(self):
        self.total_token_count = 0

class MetaLlamaGroqProvider(LLMProvider):
    def __init__(self):
        super().__init__()
        self.name = "meta_llama_groq"
        self.client = None
        self.settings = {}
        
    def initialize(self):
        if not "GROQ_API_KEY" in os.environ:
            raise ValueError("Missing GROQ_API_KEY environment variable")
            
        self.settings = {
            "temperature": KnobFactory.create_knob("slider", 
                name="Temperature", 
                min_value=0.0, 
                max_value=2.0, 
                default_value=1.25
            ),
            "top_p": KnobFactory.create_knob("slider", 
                name="Top P", 
                min_value=0.0, 
                max_value=1.0, 
                default_value=0.95
            )
        }
        
        self.models = [
            ModelOption(
                id="llama-3.3-70b-versatile",
                name="Llama 3.3 70B Versatile"
            )
        ]
        
        self.client = AsyncOpenAI(
            api_key=os.environ["GROQ_API_KEY"], 
            base_url="https://api.groq.com/openai/v1"
        )

    def get_available_models(self) -> List[ModelOption]:
        return self.models
        
    def get_settings(self) -> Dict[str, Any]:
        return self.settings
        
    def create_chat_session(self, model_id: str, history: List[Dict], system_prompt: Optional[str]) -> Any:
        messages = []
        if system_prompt:
            self.messages.append(
                {
                    "role": "system",
                    "content": (self.system_prompt),
                }
            )

        for item in history:
            # Text only!
            if len(item["parts"]) == 1 and isinstance(item["parts"][0], str):
                messages.append({
                    "role": item["role"], 
                    "content": item["parts"][0]
                })
            else:
                print("!!! message ignored --", item)
                
        return ChatSession(
            client=self.client,
            model=model_id,
            messages=messages,
            settings=self.settings
        )

class ChatSession:
    def __init__(self, client, model, messages, settings):
        self.client = client
        self.model = model
        self.messages = messages
        self.settings = settings
        self.text = None
        self.usage_metadata = UsageMetadataWrapper()
        
    async def send_message_async(self, message):
        self.messages.append({
            "role": "user",
            "content": message
        })
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            temperature=self.settings["temperature"].get_value(),
            top_p=self.settings["top_p"].get_value()
        )
        
        self.text = response.choices[0].message.content
        self.usage_metadata.total_token_count = response.usage.total_tokens
        return self