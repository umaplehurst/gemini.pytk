from llm_provider import LLMProvider, ModelOption
from knob_factory import KnobFactory, Knob
from typing import Dict, List, Any, Optional
import os
from conversation_manager import ConversationManager

from icecream import ic
DEBUG = True

from google import genai
from google.genai.types import HarmCategory, HarmBlockThreshold, SafetySetting
from google.genai.types import GenerateContentConfig, Content, Part, Tool, FunctionDeclaration

class GoogleAIProvider(LLMProvider):
    def __init__(self):
        super().__init__()
        self.name = "google_ai"
        self.settings = {}
        self.conversation_manager = ConversationManager()

        # Import based on API flavor
        if not "GOOGLE_API_KEY" in os.environ:
            print(">> Using Gen AI SDK on Vertex AI Gemini API")
            self.client = genai.Client(vertexai=True,
                                       project=os.environ["GOOGLE_VERTEX_AI_PROJECT_ID"],
                                       location=os.environ["GOOGLE_VERTEX_AI_REGION"])
        else:
            print(">> Using Gen AI SDK on Gemini Developer API")
            self.client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])

    def initialize(self):
        # Initialize settings with knobs
        self.settings = {
            "temperature": KnobFactory.create_knob("slider", 
                name="Temperature", 
                min_value=0.0, 
                max_value=2.0, 
                default_value=1.25
            ),
            "top_k": KnobFactory.create_knob("slider", 
                name="Top K", 
                min_value=1, 
                max_value=40, 
                default_value=40
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
            ),
            "enable_artifact_gizmos": KnobFactory.create_knob("checkbox",
                name="Function Calling: Artifact Gizmos",
                default_value=False
            )
        }

        # Vertex AI model list
        if not "GOOGLE_API_KEY" in os.environ:
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
        # Gemini Developer API model list
        else:
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
    
    def _get_function_declarations(self):
        """Define the function declarations for the model to use"""
        create_artifact_function = FunctionDeclaration(
            name="create_artifact",
            description="Create a new artifact with the given ID and contents",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The ID of the artifact to create"
                    },
                    "contents": {
                        "type": "string",
                        "description": "The contents of the artifact"
                    }
                },
                "required": ["id", "contents"]
            }
        )
        
        edit_artifact_function = FunctionDeclaration(
            name="edit_artifact",
            description="Edit an existing artifact by replacing text; global_substitutions are applied before single_substitutions",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The ID of the artifact to edit"
                    },
                    "global_substitutions": {
                        "type": "array",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "from_str": {"type": "STRING"},
                                "to_str": {"type": "STRING"},
                            },
                            "required": ["from_str", "to_str"],
                        },
                        "description": "An array of global substitution objects. Each substitution will be applied for every match."
                    },
                    "single_substitutions": {
                        "type": "array",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "from_str": {"type": "STRING"},
                                "to_str": {"type": "STRING"},
                            },
                            "required": ["from_str", "to_str"],
                        },
                        "description": "An array of single substitution objects. Each substitution needs to be globally unique in order for it to succeed, so include sufficient context for there to be a single match in the artifact."
                    },
                },
                "required": ["id"]
            }
        )
        
        return [create_artifact_function, edit_artifact_function]
        
    def create_chat_session(self, model_id: str, conversation_manager: ConversationManager, system_prompt: Optional[str]) -> Any:
        # Update the conversation manager with the provided history
        self.conversation_manager = conversation_manager
        safety_settings = [
            SafetySetting(category='HARM_CATEGORY_CIVIC_INTEGRITY', threshold='BLOCK_NONE'),
            SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
            SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
            SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
            SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
            SafetySetting(category='HARM_CATEGORY_UNSPECIFIED', threshold='BLOCK_NONE'),
        ]
        
        # Check if function calling is enabled
        tools = None
        if self.settings["enable_artifact_gizmos"].get_value():
            function_declarations = self._get_function_declarations()
            tools = [Tool(function_declarations=function_declarations)]

        generation_config: GenerateContentConfig = {
            "system_instruction": system_prompt,
            "safety_settings": safety_settings,
            "response_mime_type": "text/plain",
            "tools": tools,

            "temperature": self.settings["temperature"].get_value(),
            "top_p": self.settings["top_p"].get_value(),
            "top_k": self.settings["top_k"].get_value(),
            "max_output_tokens": self.settings["max_output_tokens"].get_value(),
        }

        # Get the LLM-compatible history
        llm_history = self.conversation_manager.get_llm_history()
        
        filtered_history = []
        for item in llm_history:
            if item["role"] == "user" or item["role"] == "model":
                # Process user and model messages
                parts = []
                for part in item["parts"]:
                    if isinstance(part, str):
                        parts.append(Part.from_text(text=part))
                    elif isinstance(part, dict) and "mime_type" in part and "data" in part:
                        parts.append(Part.from_bytes(data=part["data"], mime_type=part["mime_type"]))
                filtered_item = Content(role=item["role"], parts=parts)
            elif item["role"] == "function" and "function_call" in item:
                # Process function calls
                function_call = item["function_call"]
                part = Part.from_function_call(
                    name=function_call["name"],
                    args=function_call["args"]
                )
                filtered_item = Content(role="function", parts=[part])
            elif item["role"] == "function_response" and "name" in item:
                # Process function responses
                part = Part.from_function_response(
                    name=item["function_response"]["name"],
                    response=item["function_response"]["response"]
                )
                filtered_item = Content(role="function", parts=[part])
            filtered_history.append(filtered_item)

        # Debug
        if DEBUG:
            ic("LLM chat_history:", filtered_history)

        # Create a chat session with function calling support
        chat_session = self.client.aio.chats.create(
            model=model_id,
            config=generation_config,
            history=filtered_history
        )
        
        # Wrap the chat session to handle function calls if enabled
        if self.settings["enable_artifact_gizmos"].get_value():
            return FunctionCallingChatSession(chat_session, self.conversation_manager)
        
        return SimpleChatSession(chat_session, self.conversation_manager)

class SimpleChatSession:
    """Basic chat session that updates the conversation manager"""
    
    def __init__(self, chat_session, conversation_manager):
        self.chat_session = chat_session
        self.conversation_manager = conversation_manager
  
    async def send_message_async(self, message):
        """Send a message and update the conversation manager"""
        # Track the initial history length to identify new items
        initial_history_length = len(self.conversation_manager.history)

        # Add user message to conversation
        sequence = self.conversation_manager.seq_user + 1
        
        # Send to LLM
        response = await self.chat_session.send_message(message)
        if DEBUG:
            ic("LLM response:", response)
        
        # Add model response to conversation
        self.conversation_manager.add_model_message(response.text, sequence)

        # Bump conversation manager's sequence number
        self.conversation_manager.seq_user += 1

        # Attach the new history items to the response
        new_history_items = self.conversation_manager.history[initial_history_length:]

        return (response, new_history_items)

class FunctionCallingChatSession(SimpleChatSession):
    """Chat session that handles function calling and updates the conversation manager"""
    
    async def send_message_async(self, message):
        """Send a message, handle any function calls, and update the conversation manager"""
        # Track the initial history length to identify new items
        initial_history_length = len(self.conversation_manager.history)

        # Get sequence number for responses
        sequence = self.conversation_manager.seq_user + 1
        
        # Send to LLM
        response = await self.chat_session.send_message(message)
        if DEBUG:
            print(response)
        
        # Check if the response contains function calls
        # FIXME: We only deal with a single candidate reply here
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        # Handle function call
                        function_call = part.function_call
                        function_name = function_call.name
                        function_args = function_call.args
                        
                        # Execute the function
                        result = self._execute_function(function_name, function_args, sequence)
                        
                        # Only send the function result back to the model if the operation failed
                        if not result.get("success", False):
                            content = Part.from_function_response(
                                name=function_name,
                                response={"content": result}
                            )
                            response = await self.chat_session.send_message_async(content)
                    elif hasattr(part, 'text') and part.text:
                        self.conversation_manager.add_model_message(part.text, sequence)

        # Bump conversation manager's sequence number
        self.conversation_manager.seq_user += 1

        # Attach the new history items to the response
        new_history_items = self.conversation_manager.history[initial_history_length:]

        return (response, new_history_items)
    
    def _execute_function(self, function_name, args, sequence):
        """Execute the function and return the result"""
        if function_name == "create_artifact":
            return self.conversation_manager.create_artifact(
                args.get('id', ''),
                args.get('contents', ''),
                sequence
            )
        elif function_name == "edit_artifact":
            return self.conversation_manager.edit_artifact(
                args.get('id', ''),
                args.get('global_substitutions', []),
                args.get('single_substitutions', []),
                sequence
            )
        else:
            return {
                "success": False,
                "message": f"Unknown function: {function_name}"
            }

