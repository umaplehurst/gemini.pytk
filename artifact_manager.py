from typing import Dict, List, Optional, Any, Tuple
import time
import copy

class ArtifactManager:   
    def __init__(self):
        # Main dictionary of artifacts (current version of each)
        self.artifacts: Dict[str, str] = {}
        
        # Dictionary mapping artifact_id -> list of (sequence_id, content) tuples
        # Each entry represents a version of the artifact at that sequence point
        self.artifact_history: Dict[str, List[Tuple[int, str]]] = {}
        
    def create_artifact(self, artifact_id: str, contents: str, sequence_id: int) -> Dict[str, Any]:
        """Create a new artifact with the given ID and contents"""
        if artifact_id in self.artifacts:
            return {
                "success": False,
                "message": f"Artifact with ID '{artifact_id}' already exists"
            }
        
        # Store current version
        self.artifacts[artifact_id] = contents
        
        # Initialize version history
        self.artifact_history[artifact_id] = [(sequence_id, contents)]
        
        return {
            "success": True,
            "message": f"Created artifact '{artifact_id}' with {len(contents)} characters",
            "artifact_id": artifact_id,
            "contents": contents
        }
    
    def edit_artifact_content(self, artifact_id: str, new_content: str, sequence_id: int) -> Dict[str, Any]:
        """
        Edit an existing artifact by directly replacing its content.
        Creates a new version in the history.
        
        Args:
            artifact_id: The ID of the artifact to edit
            new_content: The new content to set for the artifact
            sequence_id: The sequence ID for this version
            
        Returns:
            Dictionary with result information
        """
        if artifact_id not in self.artifacts:
            return {
                "success": False,
                "message": f"Artifact with ID '{artifact_id}' does not exist"
            }
        
        original_content = self.artifacts[artifact_id]
        
        # No changes needed if content is identical
        if original_content == new_content:
            return {
                "success": True,
                "message": f"No changes needed for artifact '{artifact_id}' (content identical)",
                "artifact_id": artifact_id,
                "original_content": original_content,
                "new_content": new_content
            }
        
        # Update current version
        self.artifacts[artifact_id] = new_content
        
        # Add to version history
        self.artifact_history[artifact_id].append((sequence_id, new_content))
        
        return {
            "success": True,
            "message": f"Updated content for artifact '{artifact_id}'",
            "artifact_id": artifact_id,
            "original_content": original_content,
            "new_content": new_content
        }
    
    def get_artifact(self, artifact_id: str) -> Optional[str]:
        """Get the current contents of an artifact"""
        return self.artifacts.get(artifact_id)
    
    def get_artifact_at_sequence(self, artifact_id: str, sequence_id: int) -> Optional[str]:
        """Get the contents of an artifact as it existed at a specific sequence point"""
        if artifact_id not in self.artifact_history:
            return None
        
        # Find the most recent version at or before the given sequence_id
        valid_versions = [(seq, content) for seq, content in self.artifact_history[artifact_id] 
                         if seq <= sequence_id]
        
        if not valid_versions:
            return None
        
        # Return the most recent valid version's content
        return sorted(valid_versions, key=lambda v: v[0])[-1][1]
    
    def get_artifact_before_sequence(self, artifact_id: str, sequence_id: int) -> Optional[str]:
        """Get the contents of an artifact as it existed just before a specific sequence point"""
        if artifact_id not in self.artifact_history:
            return None
        
        # Find the most recent version strictly before the given sequence_id
        valid_versions = [(seq, content) for seq, content in self.artifact_history[artifact_id] 
                         if seq < sequence_id]
        
        if not valid_versions:
            return None
        
        # Return the most recent valid version's content
        return sorted(valid_versions, key=lambda v: v[0])[-1][1]
    
    def get_all_artifacts_at_sequence(self, sequence_id: int) -> Dict[str, str]:
        """Get all artifacts as they existed at a specific sequence point"""
        result = {}
        for artifact_id in self.artifact_history:
            content = self.get_artifact_at_sequence(artifact_id, sequence_id)
            if content:
                result[artifact_id] = content
        return result
    
    def list_artifacts(self) -> List[str]:
        """List all artifact IDs"""
        return list(self.artifacts.keys())
    
    def get_version_count(self, artifact_id: str) -> int:
        """Get the number of versions for an artifact"""
        if artifact_id not in self.artifact_history:
            return 0
        return len(self.artifact_history[artifact_id])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "artifacts": self.artifacts.copy(),
            "artifact_history": {k: list(v) for k, v in self.artifact_history.items()}
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load from dictionary"""
        self.artifacts = data.get("artifacts", {}).copy()
        
        # Convert history from list format if present
        if "artifact_history" in data:
            self.artifact_history = {}
            for art_id, history in data["artifact_history"].items():
                self.artifact_history[art_id] = [(seq, content) for seq, content in history]
        else:
            # For backward compatibility, initialize history from current artifacts
            self.artifact_history = {art_id: [(0, content)] for art_id, content in self.artifacts.items()}