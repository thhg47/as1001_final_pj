from pathlib import Path
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

print("1. Đang đọc dữ liệu train_bilingual.csv...")
df_train = pd.read_csv("train_bilingual.csv", encoding="utf-8-sig")
df_train = df_train.dropna(subset=["text", "label"]).copy()
df_train["text"] = df_train["text"].astype(str).str.strip()
df_train = df_train[df_train["text"] != ""]
df_train["label"] = pd.to_numeric(df_train["label"], errors="coerce")
df_train = df_train.dropna(subset=["label"])
df_train["label"] = df_train["label"].astype(int)

test_path = Path("test_fixed.csv")
if test_path.exists():
    print("   Tìm thấy test_fixed.csv — dùng làm tập kiểm tra...")
    df_test = pd.read_csv(test_path, encoding="utf-8-sig")
    df_test = df_test.dropna(subset=["text", "label"]).copy()
    df_test["text"] = df_test["text"].astype(str).str.strip()
    df_test = df_test[df_test["text"] != ""]
    df_test["label"] = pd.to_numeric(df_test["label"], errors="coerce")
    df_test = df_test.dropna(subset=["label"])
    df_test["label"] = df_test["label"].astype(int)

    X_train, y_train = df_train["text"], df_train["label"]
    X_test, y_test = df_test["text"], df_test["label"]
else:
    print("   Không thấy test_fixed.csv — tự tách 80% train / 20% test...")
    X_train, X_test, y_train, y_test = train_test_split(
        df_train["text"],
        df_train["label"],
        test_size=0.2,
        random_state=42,
        stratify=df_train["label"],
    )

print(f"   Số mẫu train: {len(X_train)} | Số mẫu test: {len(X_test)}")

print("2. Đang huấn luyện mô hình (TF-IDF + Logistic Regression)...")
vectorizer = TfidfVectorizer(max_features=10000, ngram_range=(1, 2))
X_train_vec = vectorizer.fit_transform(X_train)

model = LogisticRegression(max_iter=1000)
model.fit(X_train_vec, y_train)

# Đánh giá mô hình
X_test_vec = vectorizer.transform(X_test)
score = model.score(X_test_vec, y_test)
y_pred = model.predict(X_test_vec)
print(f"Huấn luyện hoàn tất! Độ chính xác trên tập kiểm tra: {score * 100:.2f}%")
print("\nBáo cáo chi tiết theo từng nhãn:")
print(classification_report(y_test, y_pred, digits=4))

# 3. Lưu mô hình và vectorizer ra file .pkl
joblib.dump(model, "safety_baseline_model.pkl")
joblib.dump(vectorizer, "tfidf_vectorizer.pkl")
print("Đã lưu thành công safety_baseline_model.pkl và tfidf_vectorizer.pkl!")