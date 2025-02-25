from llm_provider import LLMProvider, ModelOption
from knob_factory import KnobFactory, Knob
from typing import Dict, List, Any, Optional
import os

# Import based on API flavor
if not "GOOGLE_API_KEY" in os.environ:
    print(">> Using Vertex AI")
    import vertexai
    from vertexai.generative_models import Content, GenerativeModel, Part
    from vertexai.generative_models import HarmCategory, HarmBlockThreshold

    CREATE_CONTENT = True
    if not all(key in os.environ for key in ["GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_VERTEX_AI_PROJECT_ID", "GOOGLE_VERTEX_AI_REGION"]):
        raise ValueError("Missing required Vertex AI environment variables")
        
    vertexai.init(project=os.environ["GOOGLE_VERTEX_AI_PROJECT_ID"],
                  location=os.environ["GOOGLE_VERTEX_AI_REGION"])
else:
    print(">> Using Gemini on Google AI")
    from google.generativeai import GenerativeModel
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    CREATE_CONTENT = False

class GoogleAIProvider(LLMProvider):
    def __init__(self):
        super().__init__()
        self.name = "google_ai"
        self.settings = {}
        
    def initialize(self):
        # Initialize settings with knobs
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
            ),
            "max_output_tokens": KnobFactory.create_knob("slider", 
                name="Max Output Tokens", 
                min_value=1, 
                max_value=8192, 
                default_value=8192
            )
        }

        # Add API-specific settings
        if not "GOOGLE_API_KEY" in os.environ:
            self.settings.update({
                "top_k": KnobFactory.create_knob("slider", 
                    name="Top K", 
                    min_value=1, 
                    max_value=40, 
                    default_value=40
                )
            })
            self.models = [
                ModelOption(
                    id="gemini-2.0-pro-exp-02-05",
                    name="Gemini 2.0 Pro Experimental"
                ),
                ModelOption(
                    id="gemini-1.5-pro-002",
                    name="Gemini 1.5 Pro"
                )
            ]
        else:
            self.settings.update({
                "top_k": KnobFactory.create_knob("slider", 
                    name="Top K", 
                    min_value=1, 
                    max_value=64, 
                    default_value=64
                )
            })
            self.models = [
                ModelOption(
                    id="gemini-2.0-pro-exp-02-05",
                    name="Gemini 2.0 Pro Experimental"
                ),
                ModelOption(
                    id="gemini-1.5-pro",
                    name="Gemini 1.5 Pro"
                )
            ]

    def get_available_models(self) -> List[ModelOption]:
        return self.models
        
    def get_settings(self) -> Dict[str, Any]:
        return self.settings
        
    def create_chat_session(self, model_id: str, history: List[Dict], system_prompt: Optional[str]) -> Any:
        generation_config = {
            "temperature": self.settings["temperature"].get_value(),
            "top_p": self.settings["top_p"].get_value(),
            "top_k": self.settings["top_k"].get_value(),
            "max_output_tokens": self.settings["max_output_tokens"].get_value(),
            "response_mime_type": "text/plain",
        }

        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE
        }
        
        if not "GOOGLE_API_KEY" in os.environ:
            safety_settings[HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY] = HarmBlockThreshold.BLOCK_NONE

        model = GenerativeModel(
            model_name=model_id,
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=system_prompt
        )

        filtered_history = []
        for item in history:
            if CREATE_CONTENT:
                parts = []
                for part in item["parts"]:
                    parts.append(Part.from_text(part))
                filtered_item = Content(role=item["role"], parts=parts)
            else:
                to_copy = ["role", "parts"]
                filtered_item = {key: value for key, value in item.items() if key in to_copy}
            filtered_history.append(filtered_item)

        return model.start_chat(history=filtered_history)