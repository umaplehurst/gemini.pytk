from model_meta_llama_vertexai import ModelMetaLlamaVertexAI
from model_google_ai import ModelGoogleGenerativeAI
from knob_factory import KnobFactory

from enum import Enum
import os

class ModelChoice(Enum):
    TEST_MODEL_GEMINI = "Test Model (Gemini)"
    TEST_MODEL_LLAMA = "Test Model (Llama)"

DEFAULT_MODEL = ModelChoice.TEST_MODEL_GEMINI.value

class UserUIModel(ModelGoogleGenerativeAI):
    def __init__(self):
        super().__init__()
        self._add_custom_knobs()

        # Load system instructions per ModelChoice
        self.system_instructions_options = {
            ModelChoice.TEST_MODEL_GEMINI: None,
            ModelChoice.TEST_MODEL_LLAMA: None,
        }
        for i in ModelChoice:
            module_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(module_dir, f'model_{i.name.lower()}.txt')
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as fh:
                    self.system_instructions_options[i] = fh.read()
            else:
                print("!!! missing system instructions:", file_path)

        # Persist Llama objects
        self.instance_tm_llama = ModelMetaLlamaVertexAI(self.system_instructions_options[ModelChoice.TEST_MODEL_LLAMA])

    def _add_custom_knobs(self):
        # Add the model_choice knob
        self.add_knob("model_choice", KnobFactory.create_knob("dropdown", name="Model", options=[m.value for m in ModelChoice], default_value=DEFAULT_MODEL))

        # Add your custom knobs here
        # self.add_knob("custom_temperature", KnobFactory.create_knob("slider", name="Custom Temperature", min_value=0.0, max_value=2.0, default_value=0.7))

    def generate_chat_session(self, history):
        # Apply model-specific configurations
        model_choice = ModelChoice(self.knobs["model_choice"].get_value())

        if model_choice == ModelChoice.TEST_MODEL_GEMINI:
            self.system_instructions = self.system_instructions_options[model_choice]
        elif model_choice == ModelChoice.TEST_MODEL_LLAMA:
            self.system_instructions = self.system_instructions_options[model_choice]
        else:
            raise ValueError(f"Unknown model choice: {model_choice}")

        # Divert to Llama
        instance = super()
        if model_choice == ModelChoice.TEST_MODEL_LLAMA:
            instance = self.instance_tm_llama

        # Get the chat session
        chat_session = instance.generate_chat_session(history)
        return chat_session

    def add_custom_model_choice(self, model_name):
        # Add a new model choice to the existing ModelChoice enum
        ModelChoice[model_name.upper()] = model_name

        # Update the model_choice knob with the new option
        current_options = self.knobs["model_choice"].get_ui_component()["options"]
        current_options.append(model_name)
        self.knobs["model_choice"] = KnobFactory.create_knob("dropdown", name="Model", options=current_options, default_value=self.knobs["model_choice"].get_value())

    # Add any other custom methods or overrides here

# Example usage:
if __name__ == "__main__":
    user_model = UserUIModel()

    # Print all available knobs
    for key, knob in user_model.get_knobs().items():
        print(f"Knob: {key}, Type: {knob.get_ui_component()['type']}")
