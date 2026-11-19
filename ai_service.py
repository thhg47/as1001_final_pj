import joblib
from fastapi import FastAPI

app = FastAPI()

# Nạp mô hình vào bộ nhớ khi khởi động server
model = joblib.load("safety_baseline_model.pkl")
vectorizer = joblib.load("tfidf_vectorizer.pkl")


@app.post("/predict")
def predict_safety(data: dict):
  text = data.get("text", "")
  if not text:
    return {"error": "Thiếu văn bản đầu vào"}

  # Dự đoán nhãn an toàn
  X_input = vectorizer.transform([text])
  prediction = model.predict(X_input)[0]
  probability = model.predict_proba(X_input).max()

  labels = {0: "Safe", 1: "Warning", 2: "Danger"}

  return {
      "text": text,
      "label": int(prediction),
      "category": labels.get(int(prediction), "Unknown"),
      "confidence": round(float(probability), 4),
  }