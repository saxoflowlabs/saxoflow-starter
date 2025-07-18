from abc import ABC, abstractmethod

class ModelGateway(ABC):
    @abstractmethod
    def query(self, prompt: str) -> str:
        pass
