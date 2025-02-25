from typing import Any, Dict, List, Optional
from llm_provider import LLMProvider
from llm_provider_google import GoogleAIProvider
from llm_provider_meta_groq import MetaLlamaGroqProvider

class UserUIModel:
    def __init__(self):
        self.providers: Dict[str, LLMProvider] = {}
        self.current_provider = None
        self.current_model = None
        self._initialize_providers()
        
    def _initialize_providers(self):
        # Initialize built-in providers
        providers = [
            GoogleAIProvider(),
            MetaLlamaGroqProvider()
        ]
        
        for provider in providers:
            provider.initialize()
            self.providers[provider.name] = provider
            
        # Set default provider
        if self.providers:
            self.current_provider = next(iter(self.providers.values()))
            self.current_model = self.current_provider.get_available_models()[0].id
    
    def get_providers(self) -> Dict[str, LLMProvider]:
        return self.providers
    
    def set_provider(self, provider_name: str) -> None:
        if provider_name in self.providers:
            self.current_provider = self.providers[provider_name]
            self.current_model = self.current_provider.get_available_models()[0].id
    
    def set_model(self, model_id: str) -> None:
        self.current_model = model_id
    
    def get_knobs(self) -> Dict[str, Any]:
        if self.current_provider:
            return self.current_provider.get_settings()
        return {}
    
    def generate_chat_session(self, history: List[Dict], system_prompt: Optional[str]) -> Any:
        if not self.current_provider:
            raise ValueError("No provider selected")
        return self.current_provider.create_chat_session(
            model_id=self.current_model,
            history=history,
            system_prompt=system_prompt
        )

# Example usage:
if __name__ == "__main__":
    user_model = UserUIModel()

    # Print all available knobs
    for key, knob in user_model.get_knobs().items():
        print(f"Knob: {key}, Type: {knob.get_ui_component()['type']}")
