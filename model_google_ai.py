import os

CREATE_CONTENT = False

# Pick API flavor depending on what is in .env
if not "GOOGLE_API_KEY" in os.environ:
    print(">> Using Vertex AI")
    import vertexai
    from vertexai.generative_models import Content, GenerativeModel, Part
    from vertexai.generative_models import HarmCategory, HarmBlockThreshold

    if not "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        raise ValueError("Missing keys")
    if not "GOOGLE_VERTEX_AI_PROJECT_ID" in os.environ:
        raise ValueError("Missing project ID")
    if not "GOOGLE_VERTEX_AI_REGION" in os.environ:
        raise ValueError("Missing project region")

    CREATE_CONTENT = True
    vertexai.init(project=os.environ["GOOGLE_VERTEX_AI_PROJECT_ID"],
                  location=os.environ["GOOGLE_VERTEX_AI_REGION"])
else:
    print(">> Using Gemini on Google AI")
    from google.generativeai import GenerativeModel
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
        self.add_knob("max_output_tokens", KnobFactory.create_knob("slider", name="Max Output Tokens", min_value=1, max_value=8192, default_value=8192))

        # Set model names depending on API
        if not "GOOGLE_API_KEY" in os.environ:
            self.add_knob("top_k", KnobFactory.create_knob("slider", name="Top K", min_value=1, max_value=40, default_value=40))
            self.add_knob("base_model", KnobFactory.create_knob("dropdown", name="Base Model", options=["gemini-2.0-pro-exp-02-05", "gemini-1.5-pro-002"], default_value="gemini-2.0-pro-exp-02-05"))
        else:
            self.add_knob("top_k", KnobFactory.create_knob("slider", name="Top K", min_value=1, max_value=64, default_value=64))
            self.add_knob("base_model", KnobFactory.create_knob("dropdown", name="Base Model", options=["gemini-2.0-pro-exp-02-05", "gemini-1.5-pro"], default_value="gemini-2.0-pro-exp-02-05"))

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

        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE
        }
        # not yet available in google.generativeai
        if not "GOOGLE_API_KEY" in os.environ:
            safety_settings[HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY] = HarmBlockThreshold.BLOCK_NONE

        model = GenerativeModel(
            model_name=self.knobs["base_model"].get_value(),
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=self.system_instructions
        )

        filtered_history = []
        for i in history:
            if CREATE_CONTENT:
                parts = []
                for j in i["parts"]:
                    parts.append(Part.from_text(j))
                filtered_i = Content(role=i["role"], parts=parts)
            else:
                to_copy = ["role", "parts"]
                filtered_i = {key: value for key, value in i.items() if key in to_copy}
            filtered_history.append(filtered_i)

        chat_session = model.start_chat(history=filtered_history)
        return chat_session
