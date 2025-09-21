# nlu_train.py — trains intents and stores replies from CSV
import pickle
from pathlib import Path
from typing import Dict, List
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

CSV_PATH = Path("data") / "kaggle_training_data.csv"
MODEL_PATH = Path("models") / "nlu.pkl"

def train_and_save(model_path: Path = MODEL_PATH, csv_path: Path = CSV_PATH):
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # Read CSV (robust to commas/utf-8-sig)
    df = pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8-sig")

    for col in ("text", "intent", "response"):
        if col not in df.columns:
            raise ValueError(f"CSV must have columns: text,intent,response (missing: {col})")

    X: List[str] = df["text"].astype(str).tolist()
    y: List[str] = df["intent"].astype(str).tolist()

    # Intent classifier
    pipe = Pipeline([
        ("vec", TfidfVectorizer(ngram_range=(1,2), lowercase=True)),
        ("clf", LinearSVC())
    ])
    pipe.fit(X, y)

    # Build replies per intent from CSV (dedup, non-empty, min length)
    replies: Dict[str, List[str]] = {}
    for intent, grp in df.groupby("intent"):
        seen, lst = set(), []
        for r in grp["response"].astype(str):
            r = r.strip()
            if len(r) >= 4 and r not in seen:
                seen.add(r); lst.append(r)
        if lst:
            replies[intent] = lst

    # Always have a fallback
    replies.setdefault("fallback", ["I didn’t quite get that, but I’m here to help."])

    model_path.parent.mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({"model": pipe, "responses": replies}, f)

    print("✅ Trained on:", csv_path)
    print("   classes:", sorted(set(y)))
    print("💾 Saved →", model_path)

if __name__ == "__main__":
    train_and_save()
