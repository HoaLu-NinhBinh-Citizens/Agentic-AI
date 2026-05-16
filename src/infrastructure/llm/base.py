from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """Small abstraction for agent text generation backends."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError
