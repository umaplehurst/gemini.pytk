from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class ModelOption:
    id: str
    name: str

class LLMProvider(ABC):
    def __init__(self):
        self.name: str = ""
        self.models: List[ModelOption] = []
        self.settings: Dict[str, Any] = {}
        
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the provider with any required setup"""
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[ModelOption]:
        """Return list of available models for this provider"""
        pass
    
    @abstractmethod
    def get_settings(self) -> Dict[str, Any]:
        """Return provider-specific settings"""
        pass
        
    @abstractmethod
    def create_chat_session(self, model_id: str, history: List[Dict], system_prompt: Optional[str]) -> Any:
        """Create a chat session with the specified model"""
        pass