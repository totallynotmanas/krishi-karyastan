"""FIPA-ACL compliant message framing for inter-agent communication."""

from __future__ import annotations
import uuid
from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field


class Performative(str, Enum):
    """Standard FIPA-ACL speech act performatives."""
    INFORM = "INFORM"                    # Informing of state or observation
    QUERY_REF = "QUERY_REF"              # Querying information (e.g. asking KB)
    CFP = "CFP"                          # Call For Proposals (Contract Net Protocol)
    PROPOSE = "PROPOSE"                  # Submitting a bid/proposal
    ACCEPT_PROPOSAL = "ACCEPT_PROPOSAL"  # Accepting a proposed action
    REJECT_PROPOSAL = "REJECT_PROPOSAL"  # Rejecting an unsuitable proposal
    CONFIRM = "CONFIRM"                  # Confirming reservation / commitment
    CANCEL = "CANCEL"                    # Cancelling a previously agreed commitment
    FAILURE = "FAILURE"                  # Announcing inability to complete task


class ACLMessage(BaseModel):
    """FIPA-ACL communication envelope for all cooperative multi-agent messages."""
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    conversation_id: str = Field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:8]}")
    in_reply_to: Optional[str] = Field(default=None, description="ID of antecedent message")
    sender: str = Field(..., description="ID of transmitting agent")
    receiver: str = Field(..., description="ID of recipient agent, 'broadcast', or 'shared_knowledge_base'")
    performative: Performative = Field(..., description="FIPA-ACL speech act performative")
    ontology: str = Field(default="krishi-mas-v1", description="Semantic domain ontology")
    protocol: Optional[str] = Field(default=None, description="Interaction protocol e.g. fipa-contract-net")
    content: Union[Dict[str, Any], BaseModel, str] = Field(..., description="Structured message body")
    timestamp: int = Field(default=0, ge=0, description="Simulation tick timestamp")

    def create_reply(
        self,
        performative: Performative,
        content: Union[Dict[str, Any], BaseModel, str],
        sender: str,
        timestamp: int,
    ) -> ACLMessage:
        """Helper to create a properly chained reply message."""
        return ACLMessage(
            conversation_id=self.conversation_id,
            in_reply_to=self.message_id,
            sender=sender,
            receiver=self.sender,
            performative=performative,
            ontology=self.ontology,
            protocol=self.protocol,
            content=content,
            timestamp=timestamp,
        )

    def content_dict(self) -> Dict[str, Any]:
        """Returns message content as a standard dictionary."""
        if isinstance(self.content, BaseModel):
            return self.content.model_dump()
        elif isinstance(self.content, dict):
            return self.content
        return {"value": self.content}
