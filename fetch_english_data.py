import csv
from pathlib import Path
import pandas as pd

search_dirs = [Path.home() / "Downloads", Path(".")]


def find_parquet(candidates):
    for name in candidates:
        for folder in search_dirs:
            p = folder / name
            if p.exists():
                return p
    return None


hate_path = find_parquet(
    ["hate_train.parquet", "train-00000-of-00001.parquet"]
)
off_path = find_parquet(["offensive_train.parquet"])

# Nếu cả 2 file tải về đều đang tên giống nhau là train-00000-of-00001.parquet trong Downloads,
# bạn nên đổi tên thành hate_train.parquet và offensive_train.parquet cho rõ ràng.
if hate_path is None or off_path is None:
    raise FileNotFoundError(
        "Hãy đặt/đổi tên file hate_train.parquet và offensive_train.parquet trong thư mục Downloads hoặc AI."
    )

rows = []

# 1. Hate: label 1 -> 2 (Danger), 0 -> 0 (Safe)
df_hate = pd.read_parquet(hate_path)
for _, item in df_hate.iterrows():
    txt = str(item["text"]).strip()
    if txt:
        lbl = 2 if int(item["label"]) == 1 else 0
        rows.append({"text": txt, "label": lbl})

# 2. Offensive: label 1 -> 1 (Warning), 0 -> 0 (Safe)
df_off = pd.read_parquet(off_path)
for _, item in df_off.iterrows():
    txt = str(item["text"]).strip()
    if txt:
        lbl = 1 if int(item["label"]) == 1 else 0
        rows.append({"text": txt, "label": lbl})

df_en = (
    pd.DataFrame(rows)
    .dropna(subset=["text", "label"])
    .drop_duplicates(subset=["text"])
)
df_en["label"] = df_en["label"].astype(int)

# Cân bằng tối đa 4.000 dòng mỗi nhãn
balanced = []
for lbl_val in [0, 1, 2]:
    part = df_en[df_en["label"] == lbl_val]
    balanced.append(part.sample(n=min(len(part), 4000), random_state=42))

df_en_bal = (
    pd.concat(balanced, ignore_index=True)
    .sample(frac=1, random_state=42)
    .reset_index(drop=True)
)
df_en_bal.to_csv(
    "en_train_fixed.csv",
    index=False,
    encoding="utf-8-sig",
    quoting=csv.QUOTE_ALL,
)
print(f"Đã tạo en_train_fixed.csv: {len(df_en_bal)} dòng")
print(df_en_bal["label"].value_counts())

# Gộp với train_fixed.csv thành train_bilingual.csv
df_vi = pd.read_csv("train_fixed.csv", encoding="utf-8-sig")
df_bilingual = (
    pd.concat([df_vi, df_en_bal], ignore_index=True)
    .dropna(subset=["text", "label"])
    .drop_duplicates(subset=["text"])
)
df_bilingual["label"] = df_bilingual["label"].astype(int)
df_bilingual = df_bilingual.sample(frac=1, random_state=42).reset_index(
    drop=True
)

df_bilingual.to_csv(
    "train_bilingual.csv",
    index=False,
    encoding="utf-8-sig",
    quoting=csv.QUOTE_ALL,
)
print(f"Đã tạo train_bilingual.csv: {len(df_bilingual)} dòng")
print(df_bilingual["label"].value_counts())