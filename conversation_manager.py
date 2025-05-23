from typing import Dict, List, Any, Optional
from artifact_manager import ArtifactManager

class ConversationManager:
    """Manages the conversation history and artifacts"""
    
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.artifact_manager = ArtifactManager()
        self.seq_user = 0
        self.system_prompt = ""
        self.system_prompt_setup = ""
        self.system_memories = {}  # Dictionary of {id: memory_text}
        self.next_memory_id = 1
    
    def add_user_message(self, parts: List[Any]) -> int:
        """Add a user message to the history and return its sequence number"""
        self.seq_user += 1
        self.history.append({
            "role": "user",
            "parts": parts,
            "sequence": self.seq_user
        })
        return self.seq_user
    
    def add_model_message(self, message: str, sequence: int) -> None:
        """Add a model message to the history"""
        self.history.append({
            "role": "model",
            "parts": [message],
            "sequence": sequence
        })
    
    def add_function_call(self, function_name: str, args: Dict[str, Any], sequence: int) -> None:
        """Add a function call to the history"""
        self.history.append({
            "role": "function",
            "parts": [],  # Empty parts array for consistency
            "function_call": {
                "name": function_name,
                "args": args
            },
            "sequence": sequence
        })

    def add_function_response(self, function_name: str, result: Dict[str, Any], sequence: int) -> None:
        """Add a function result to the history"""
        self.history.append({
            "role": "function_response",
            "parts": [],  # Empty parts array for consistency
            "function_response": {
                "name": function_name,
                "response": result
            },
            "sequence": sequence
        })
    
    def create_artifact(self, artifact_id: str, contents: str, sequence: int) -> Dict[str, Any]:
        """Create a new artifact and record it in the history"""
        # Add the function call to the history
        self.add_function_call("create_artifact", {
            "id": artifact_id,
            "contents": contents
        }, sequence)
        
        # Create the artifact with version tracking
        result = self.artifact_manager.create_artifact(artifact_id, contents, sequence)
        
        # Add the function result to the history
        if not result.get("success", False):
            self.add_function_response("create_artifact", result, sequence)
        
        return result
    
    def edit_artifact(self, artifact_id: str, 
                    global_substitutions: List[Dict[str, str]] = None, 
                    single_substitutions: List[Dict[str, str]] = None, 
                    sequence: int = None) -> Dict[str, Any]:
        """
        Edit an artifact and record it in the history with version tracking.
        
        Supports two types of substitutions:
        - global_substitutions: Applied to all occurrences of a pattern
        - single_substitutions: Applied only when there's exactly one occurrence
        
        Args:
            artifact_id: The ID of the artifact to edit
            global_substitutions: List of {from, to} mappings for global substitution
            single_substitutions: List of {from, to} mappings for single occurrence substitution
            sequence: The sequence number of this operation
        
        Returns:
            Dictionary with result information
        """
        
        # Initialize substitution lists if not provided
        global_substitutions = global_substitutions or []
        single_substitutions = single_substitutions or []
        
        # Add the function call to the history with new parameter format
        args = {"id": artifact_id}
        if global_substitutions:
            args["global_substitutions"] = global_substitutions
        if single_substitutions:
            args["single_substitutions"] = single_substitutions
        
        self.add_function_call("edit_artifact", args, sequence)
        
        # Get the current content of the artifact
        original_content = self.artifact_manager.get_artifact(artifact_id)
        if original_content is None:
            result = {
                "success": False,
                "message": f"Artifact with ID '{artifact_id}' does not exist"
            }
            self.add_function_response("edit_artifact", result, sequence)
            return result
        
        # Make a copy of the content to track changes
        current_content = original_content
        changes_made = 0
        
        # Apply global substitutions first (replace all occurrences)
        for subst in global_substitutions:
            from_str = subst.get("from_str", "")
            to_str = subst.get("to_str", "")
            
            if from_str:
                # Count occurrences
                occurrences = current_content.count(from_str)
                
                if occurrences == 0:
                    # Log warning but continue with other substitutions
                    print(f"Warning: Global substitution string '{from_str}' not found in artifact '{artifact_id}'")
                    continue
                
                # Perform global replacement
                current_content = current_content.replace(from_str, to_str)
                changes_made += occurrences
        
        # Apply single substitutions next (only if exactly one occurrence)
        failed_subst = None
        for subst in single_substitutions:
            from_str = subst.get("from_str", "")
            to_str = subst.get("to_str", "")
            
            if from_str:
                # Count occurrences
                occurrences = current_content.count(from_str)
                
                if occurrences == 0:
                    # Fail immediately on first error
                    failed_subst = {
                        "success": False,
                        "message": f"String '{from_str}' not found in artifact '{artifact_id}'"
                    }
                    break
                
                if occurrences > 1:
                    # Fail immediately on first error
                    failed_subst = {
                        "success": False,
                        "message": f"Found {occurrences} occurrences of '{from_str}' in artifact '{artifact_id}'. Exactly one occurrence is required."
                    }
                    break
                
                # Perform single replacement
                current_content = current_content.replace(from_str, to_str, 1)
                changes_made += 1
        
        # If any single substitution failed, return the error
        if failed_subst:
            self.add_function_response("edit_artifact", failed_subst, sequence)
            return failed_subst
        
        # If no changes were made at all, return failure
        if changes_made == 0:
            result = {
                "success": False,
                "message": "No substitutions were made. Check that your 'from' values match text in the artifact."
            }
            self.add_function_response("edit_artifact", result, sequence)
            return result
        
        # Update the artifact with the new content
        new_version_result = self.artifact_manager.edit_artifact_content(
            artifact_id, current_content, sequence)
        
        result = {
            "success": True,
            "message": f"Edited artifact '{artifact_id}' with {changes_made} substitutions",
            "artifact_id": artifact_id,
            "original_content": original_content,
            "new_content": current_content,
            "changes_made": changes_made
        }
        
        # Only add function response if there was an error
        if not new_version_result.get("success", True):
            self.add_function_response("edit_artifact", new_version_result, sequence)
            return new_version_result
        
        return result
    
    def get_artifact_at_sequence(self, artifact_id: str, sequence: int) -> Optional[str]:
        """Get the content of an artifact as it existed at a specific sequence point"""
        return self.artifact_manager.get_artifact_at_sequence(artifact_id, sequence)
    
    def get_artifact_before_sequence(self, artifact_id: str, sequence: int) -> Optional[str]:
        """Get the content of an artifact as it existed just before a sequence point"""
        return self.artifact_manager.get_artifact_before_sequence(artifact_id, sequence)
    
    def get_all_artifacts_at_sequence(self, sequence: int) -> Dict[str, str]:
        """Get all artifacts as they existed at a specific sequence point"""
        return self.artifact_manager.get_all_artifacts_at_sequence(sequence)

    def import_history(self, history: List[Dict[str, Any]]) -> None:
        """Import history from an external source and reconstruct artifacts"""
        self.history = []       
        for item in history:
            if item["role"] == "user":
                # Update sequence counter
                seq = item.get("sequence", self.seq_user + 1)
                self.seq_user = max(self.seq_user, seq)
                
                # Add to history
                self.history.append({
                    "role": "user",
                    "parts": item["parts"],
                    "sequence": seq
                })
                current_seq = seq
            elif item["role"] == "model":
                # Update sequence counter
                seq = item.get("sequence", self.seq_user + 1)
                
                # Add to history
                self.history.append({
                    "role": "model",
                    "parts": item["parts"],
                    "sequence": seq
                })
            elif item["role"] == "function":
                # Update sequence counter
                seq = item.get("sequence", self.seq_user + 1)

                # Extract function details
                function_name = None
                args = {}
                
                if "function_call" in item:
                    function_name = item["function_call"].get("name")
                    args = item["function_call"].get("args", {})
                else:
                    function_name = item.get("function_name")
                    args = item.get("args", {})
                
                # Add to history
                self.history.append({
                    "role": "function",
                    "parts": [],
                    "function_call": {
                        "name": function_name,
                        "args": args
                    },
                    "sequence": seq
                })
                
                # Reconstruct artifacts for create_artifact calls
                if function_name == "create_artifact":
                    artifact_id = args.get("id")
                    contents = args.get("contents")
                    
                    if artifact_id and contents:
                        # Skip the function call recording since we're already adding to history
                        self.artifact_manager.create_artifact(artifact_id, contents, seq)
                        
                # Reconstruct artifact edits
                elif function_name == "edit_artifact":
                    artifact_id = args.get("id")
                    
                    # Handle the new format with global and single substitutions
                    global_subst = args.get("global_substitutions", [])
                    single_subst = args.get("single_substitutions", [])
                                       
                    if artifact_id:
                        # Get current content of the artifact
                        current_content = self.artifact_manager.get_artifact(artifact_id)
                        if current_content is not None:
                            # Apply global substitutions first
                            for subst in global_subst:
                                from_str = subst.get("from_str", "")
                                to_str = subst.get("to_str", "")
                                if from_str:
                                    current_content = current_content.replace(from_str, to_str)
                            
                            # Apply single substitutions
                            for subst in single_subst:
                                from_str = subst.get("from_str", "")
                                to_str = subst.get("to_str", "")
                                if from_str and current_content.count(from_str) == 1:
                                    current_content = current_content.replace(from_str, to_str, 1)
                            
                            # Update the artifact with new content
                            print("import: edited artifact ID", artifact_id, "sequence", seq)
                            self.artifact_manager.edit_artifact_content(
                                artifact_id, current_content, seq)

                # Handle system prompt edits
                elif function_name == "edit_system_prompt":
                    # Handle substitutions for the system prompt
                    single_subst = args.get("substitutions", [])
                    
                    if self.system_prompt:
                        current_content = self.system_prompt
                        
                        # Apply single substitutions
                        for subst in single_subst:
                            from_str = subst.get("from_str", "")
                            to_str = subst.get("to_str", "")
                            if from_str and current_content.count(from_str) == 1:
                                current_content = current_content.replace(from_str, to_str, 1)
                        
                        # Update the system prompt with new content
                        self.system_prompt = current_content
                
                # Handle memory_twizzle operations
                elif function_name == "memory_twizzle":
                    mode = args.get("mode", "")
                    memory_id = args.get("memory_id")
                    contents = args.get("contents")
                    
                    if mode == "new":
                        # If ID is not specified, generate one
                        if memory_id is None:
                            memory_id = self.next_memory_id
                            self.next_memory_id += 1
                        else:
                            # If ID is provided, ensure next_memory_id is updated
                            self.next_memory_id = max(self.next_memory_id, memory_id + 1)
                        
                        if contents:
                            self.system_memories[memory_id] = contents
                    
                    elif mode == "edit":
                        if memory_id is not None and memory_id in self.system_memories and contents:
                            self.system_memories[memory_id] = contents
                    
                    elif mode == "delete":
                        if memory_id is not None and memory_id in self.system_memories:
                            del self.system_memories[memory_id]

            elif item["role"] == "function_response":
                # Extract function details
                function_name = None
                result = {}
                
                if "function_response" in item:
                    function_name = item["function_response"].get("name")
                    result = item["function_response"].get("response", {})
                else:
                    function_name = item.get("function_name")
                    result = item.get("result", {})
                
                # Add to history
                self.history.append({
                    "role": "function_response",
                    "parts": [],
                    "function_response": {
                        "name": function_name,
                        "response": result
                    },
                    "sequence": current_seq
                })
    
    def get_llm_history(self, include_functions=True) -> List[Dict[str, Any]]:
        llm_history = []      
        for item in self.history:
            if item["role"] == "user":
                msg = {
                    "role": "user",
                    "parts": item["parts"]
                }
                llm_history.append(msg)               
            elif item["role"] == "model":
                llm_history.append({
                    "role": "model",
                    "parts": item["parts"]
                })
            elif include_functions and item["role"] == "function":
                llm_history.append({
                    "role": "function",
                    "function_call": item["function_call"],
                    "parts": []  # Empty parts for compatibility
                })
            elif include_functions and item["role"] == "function_response":
                llm_history.append({
                    "role": "function",
                    "function_response": item["function_response"],
                    "parts": []  # Empty parts for compatibility
                })
        
        return llm_history
    
    def get_full_history(self) -> List[Dict[str, Any]]:
        """Get the full history including function calls and results"""
        return self.history
    
    def get_artifacts(self) -> Dict[str, str]:
        """Get all current artifacts"""
        return self.artifact_manager.artifacts

    def edit_system_prompt(self, 
                        single_substitutions: List[Dict[str, str]] = None, 
                        sequence: int = None) -> Dict[str, Any]:
        """
        Edit the system prompt and record it in the history with version tracking.
        
        Args:
            single_substitutions: List of {from_str, to_str} mappings for single occurrence substitution
            sequence: The sequence number of this operation
        
        Returns:
            Dictionary with result information
        """
        
        # Initialize substitution lists if not provided
        single_substitutions = single_substitutions or []
        
        # Add the function call to the history with new parameter format
        args = {}
        if single_substitutions:
            args["substitutions"] = single_substitutions
        
        self.add_function_call("edit_system_prompt", args, sequence)
        
        # Get the current content of the system prompt
        original_content = self.system_prompt
        if not original_content:
            result = {
                "success": False,
                "message": "System prompt is empty"
            }
            self.add_function_response("edit_system_prompt", result, sequence)
            return result
        
        # Make a copy of the content to track changes
        current_content = original_content
        changes_made = 0
        
        # Apply single substitutions next (only if exactly one occurrence)
        failed_subst = None
        for subst in single_substitutions:
            from_str = subst.get("from_str", "")
            to_str = subst.get("to_str", "")
            
            if from_str:
                # Count occurrences
                occurrences = current_content.count(from_str)
                
                if occurrences == 0:
                    # Fail immediately on first error
                    failed_subst = {
                        "success": False,
                        "message": f"String '{from_str}' not found in system prompt"
                    }
                    break
                
                if occurrences > 1:
                    # Fail immediately on first error
                    failed_subst = {
                        "success": False,
                        "message": f"Found {occurrences} occurrences of '{from_str}' in system prompt. Exactly one occurrence is required."
                    }
                    break
                
                # Perform single replacement
                current_content = current_content.replace(from_str, to_str, 1)
                changes_made += 1
        
        # If any single substitution failed, return the error
        if failed_subst:
            self.add_function_response("edit_system_prompt", failed_subst, sequence)
            return failed_subst
        
        # If no changes were made at all, return failure
        if changes_made == 0:
            result = {
                "success": False,
                "message": "No substitutions were made. Check that your 'from' values match text in the system prompt."
            }
            self.add_function_response("edit_system_prompt", result, sequence)
            return result
        
        # Update the system prompt with the new content
        self.system_prompt = current_content
        
        result = {
            "success": True,
            "message": f"Edited system prompt with {changes_made} substitutions",
            "original_content": original_content,
            "new_content": current_content,
            "changes_made": changes_made
        }
        
        return result

    def memory_twizzle(self, mode: str, memory_id: Optional[int] = None, contents: Optional[str] = None, sequence: int = None) -> Dict[str, Any]:
        """
        Generic function to handle all system memory operations.
        
        Args:
            mode: The operation mode - 'new', 'edit', or 'delete'
            memory_id: The ID of the memory (required for 'edit' and 'delete', ignored for 'new')
            contents: The content of the memory (required for 'new' and 'edit', ignored for 'delete')
            sequence: The sequence number of this operation
        
        Returns:
            Dictionary with result information
        """
        
        # Add the function call to the history
        args = {
            "mode": mode
        }
        if memory_id is not None:
            args["memory_id"] = memory_id
        if contents is not None:
            args["contents"] = contents
        
        self.add_function_call("memory_twizzle", args, sequence)
        
        # Process based on mode
        if mode == "new":
            # Generate a new memory ID
            if memory_id is None:
                memory_id = self.next_memory_id
                self.next_memory_id += 1
            else:
                # If ID is provided, ensure next_memory_id is updated
                self.next_memory_id = max(self.next_memory_id, memory_id + 1)
            
            # Validate contents
            if not contents:
                result = {
                    "success": False,
                    "message": "Contents are required for new memories"
                }
                self.add_function_response("memory_twizzle", result, sequence)
                return result
            
            # Store the memory
            self.system_memories[memory_id] = contents
            
            result = {
                "success": True,
                "message": f"Added system memory with ID {memory_id}",
                "memory_id": memory_id,
                "contents": contents
            }
            
            return result
        
        elif mode == "edit":
            # Validate ID
            if memory_id is None:
                result = {
                    "success": False,
                    "message": "Memory ID is required for edit mode"
                }
                self.add_function_response("memory_twizzle", result, sequence)
                return result
            
            # Validate that memory exists
            if memory_id not in self.system_memories:
                result = {
                    "success": False,
                    "message": f"System memory with ID {memory_id} does not exist"
                }
                self.add_function_response("memory_twizzle", result, sequence)
                return result
            
            # Validate contents
            if not contents:
                result = {
                    "success": False,
                    "message": "Contents are required for edit mode"
                }
                self.add_function_response("memory_twizzle", result, sequence)
                return result
            
            # Store old content for response
            original_content = self.system_memories[memory_id]
            
            # Update the memory
            self.system_memories[memory_id] = contents
            
            result = {
                "success": True,
                "message": f"Edited system memory with ID {memory_id}",
                "memory_id": memory_id,
                "original_content": original_content,
                "new_content": contents
            }
            
            return result
        
        elif mode == "delete":
            # Validate ID
            if memory_id is None:
                result = {
                    "success": False,
                    "message": "Memory ID is required for delete mode"
                }
                self.add_function_response("memory_twizzle", result, sequence)
                return result
            
            # Validate that memory exists
            if memory_id not in self.system_memories:
                result = {
                    "success": False,
                    "message": f"System memory with ID {memory_id} does not exist"
                }
                self.add_function_response("memory_twizzle", result, sequence)
                return result
            
            # Store original content for response
            original_content = self.system_memories[memory_id]
            
            # Delete the memory
            del self.system_memories[memory_id]
            
            result = {
                "success": True,
                "message": f"Deleted system memory with ID {memory_id}",
                "memory_id": memory_id,
                "original_content": original_content
            }
            
            return result
        
        else:
            # Invalid mode
            result = {
                "success": False,
                "message": f"Invalid mode: {mode}. Must be 'new', 'edit', or 'delete'."
            }
            self.add_function_response("memory_twizzle", result, sequence)
            return result

    def get_full_system_prompt(self) -> str:
        """
        Get the full system prompt with all system memories appended.
        
        Returns:
            The full system prompt
        """
        full_prompt = self.system_prompt
        
        # Append all system memories
        if self.system_memories:
            if full_prompt:
                full_prompt += "\n\nYour memories are as follows:"
            
            # Add each memory with its ID and a separator
            memories_text = []
            for memory_id, memory_content in self.system_memories.items():
                memories_text.append(f"[MEMORY ID: {memory_id}]\n{memory_content}")
            
            full_prompt += "\n\n".join(memories_text)

        # Keeps Gen AI SDK happy
        if len(full_prompt) == 0:
            return None

        return full_prompt

    def to_dict(self) -> Dict[str, Any]:
        """Convert the conversation to a dictionary for serialization"""
        return {
            "history": self.history,
            "artifacts": self.artifact_manager.to_dict(),
            "seq_user": self.seq_user,
            "system_prompt": self.system_prompt,
            "system_memories": self.system_memories,
            "next_memory_id": self.next_memory_id
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load the conversation from a dictionary"""
        self.history = data.get("history", [])
        self.artifact_manager.from_dict(data.get("artifacts", {}))
        self.seq_user = data.get("seq_user", 0)
        self.system_prompt = data.get("system_prompt", "")
        self.system_memories = data.get("system_memories", {})
        self.next_memory_id = data.get("next_memory_id", 1)