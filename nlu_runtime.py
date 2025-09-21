# nlu_runtime.py
import pickle, random
from pathlib import Path

class TinyNLU:
    def __init__(self, model_path: Path):
        with open(Path(model_path), "rb") as f:
            obj = pickle.load(f)
        # Required keys from trainer
        self.model = obj["model"]
        self.responses = obj["responses"]  # intent -> List[str]

    def parse(self, text: str) -> str:
        try:
            return self.model.predict([text])[0]
        except Exception:
            return "fallback"

    def respond(self, intent: str) -> str:
        opts = self.responses.get(intent) or self.responses.get("fallback") or ["Sorry, I didn’t understand that."]
        return random.choice(opts)
