from pathlib import Path
from typing import List, Optional, Dict
import os

class PromptStackManager:
    def __init__(self, base_path: str = "prompt_stacks"):
        self.base_path = Path(base_path)
        self.current_stack: Optional[str] = None
        self.current_prompt: Optional[str] = None
        self.prompts: List[str] = []
        self.prompt_files: List[str] = []  # Store filenames
    
    def get_available_stacks(self) -> List[str]:
        """Get list of available prompt stacks"""
        if not self.base_path.exists():
            return []
        return [d.name for d in self.base_path.iterdir() if d.is_dir()]
    
    def load_stack(self, stack_name: str) -> List[str]:
        """Load all prompts in a stack"""
        stack_path = self.base_path / stack_name
        if not stack_path.exists():
            raise ValueError(f"Stack {stack_name} not found")
            
        self.prompts = []
        self.prompt_files = []
        # Use sorted to ensure consistent ordering
        for file in sorted(stack_path.glob("*.txt")):
            with open(file, "r", encoding='utf-8') as f:
                self.prompts.append(f.read().strip())
                # Store filename without .txt extension
                self.prompt_files.append(file.stem)
                
        self.current_stack = stack_name
        if self.prompts:
            self.current_prompt = self.prompts[0]
        return self.prompts

    def get_prompt_filename(self, index: int) -> str:
        """Get the filename for a prompt by index"""
        if 0 <= index < len(self.prompt_files):
            return self.prompt_files[index]
        return ""
    
    def get_current_stack(self) -> Optional[str]:
        """Get name of currently loaded stack"""
        return self.current_stack
    
    def get_current_prompt(self) -> Optional[str]:
        """Get current prompt text"""
        return self.current_prompt
    
    def set_current_prompt(self, index: int) -> None:
        """Set current prompt by index"""
        if 0 <= index < len(self.prompts):
            self.current_prompt = self.prompts[index]