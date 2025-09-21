import pickle, pandas as pd
from pathlib import Path
from sklearn.metrics import accuracy_score

# Load model
obj = pickle.load(open(Path("models")/"nlu.pkl","rb"))
model = obj["model"]

# Try loading CSV with error handling
with open("data/kaggle_training_data.csv", "r", encoding="utf-8") as f:
    first_line = f.readline().strip()
    print("🔎 CSV Header:", first_line)

# Force pandas to treat it as 3 columns: text,intent,response
df = pd.read_csv("data/kaggle_training_data.csv", 
                 names=["text","intent","response"], 
                 header=0, 
                 engine="python")

print("✅ Columns detected:", df.columns.tolist())

X = df["text"].astype(str).tolist()
y = df["intent"].astype(str).tolist()

# Predict + accuracy
pred = model.predict(X)
acc = accuracy_score(y, pred)
print(f"✅ Accuracy: {acc*100:.2f}%")
