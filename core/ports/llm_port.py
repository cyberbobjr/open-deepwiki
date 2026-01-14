from abc import ABC, abstractmethod
from typing import Any, List, Optional, Sequence

from langchain_core.messages import BaseMessage


class LLMProvider(ABC):
    """Abstract interface for LLM interactions."""
    
    @abstractmethod
    def invoke(self, messages: Sequence[BaseMessage]) -> str:
        """
        Invoke the LLM with a list of messages.
        
        Args:
            messages: A sequence of messages (System, Human, AI).
            
        Returns:
            The string content of the LLM response.
        """
        pass

    @abstractmethod
    def invoke_with_tools(self, messages: Sequence[BaseMessage], tools: Sequence[Any]) -> BaseMessage:
        """
        Invoke the LLM with tools bound.
        
        Args:
            messages: A sequence of messages.
            tools: A sequence of tools (functions, Pydantic models, or LangChain tools).
            
        Returns:
            The BaseMessage response (which may contain tool_calls).
        """
        pass

    @abstractmethod
    def invoke_structured(self, messages: Sequence[BaseMessage], model_class: Any) -> Any:
        """
        Invoke the LLM and parse the output into a structured object.
        
        Args:
            messages: A sequence of messages.
            model_class: The Pydantic model class to parse into.
            
        Returns:
            An instance of model_class.
        """
        pass
