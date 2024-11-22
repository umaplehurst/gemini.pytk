import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from knob_factory import KnobFactory, Knob
from typing import Dict

class ModelGoogleGenerativeAI:
    def __init__(self):
        self.system_instructions = None
        self.knobs: Dict[str, Knob] = {}
        self._initialize_knobs()

    def _initialize_knobs(self):
        # Add default knobs
        self.add_knob("temperature", KnobFactory.create_knob("slider", name="Temperature", min_value=0.0, max_value=2.0, default_value=1.5))
        self.add_knob("top_p", KnobFactory.create_knob("slider", name="Top P", min_value=0.0, max_value=1.0, default_value=0.95))
        self.add_knob("top_k", KnobFactory.create_knob("slider", name="Top K", min_value=1, max_value=64, default_value=64))
        self.add_knob("max_output_tokens", KnobFactory.create_knob("slider", name="Max Output Tokens", min_value=1, max_value=8192, default_value=8192))
        self.add_knob("base_model", KnobFactory.create_knob("dropdown", name="Base Model", options=["gemini-1.5-pro-exp-0827", "gemini-exp-1121"], default_value="gemini-1.5-pro-exp-0827"))

    def add_knob(self, key: str, knob: Knob):
        self.knobs[key] = knob

    def get_knobs(self) -> Dict[str, Knob]:
        return self.knobs

    def generate_chat_session(self, history):
        generation_config = {
            "temperature": self.knobs["temperature"].get_value(),
            "top_p": self.knobs["top_p"].get_value(),
            "top_k": self.knobs["top_k"].get_value(),
            "max_output_tokens": self.knobs["max_output_tokens"].get_value(),
            "response_mime_type": "text/plain",
        }

        model = genai.GenerativeModel(
            model_name=self.knobs["base_model"].get_value(),
            generation_config=generation_config,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                # -- not available in the upstream SDK yet:
                # HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY: HarmBlockThreshold.BLOCK_NONE,
            },
            system_instruction=self.system_instructions
        )

        filtered_history = []
        for i in history:
            to_copy = ["role", "parts"]
            filtered_i = {key: value for key, value in i.items() if key in to_copy}
            filtered_history.append(filtered_i)

        chat_session = model.start_chat(history=filtered_history)
        return chat_session
