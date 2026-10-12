"""Train and evaluate a Random Forest using extracted Sentinel-2 pixel CSVs."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPOSITORY_ROOT / "data" / "csv" / "split_dataset"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
FEATURES = ["B02", "B03", "B04", "B08", "B11", "NDVI", "NDWI", "NDBI"]
REQUIRED_COLUMNS = {"ID_Poligon", "kelas", "status_split", *FEATURES}


def load_split(path: Path, expected_split: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(
            f"CSV {expected_split} belum tersedia: {path}. "
            "Jalankan ekstraksi Sentinel-2 terlebih dahulu."
        )
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"Kolom wajib tidak ada pada {path.name}: {missing}")
    if frame.empty:
        raise ValueError(f"CSV {path.name} kosong.")
    if set(frame["status_split"].dropna().unique()) != {expected_split}:
        raise ValueError(
            f"Kolom status_split pada {path.name} harus hanya berisi {expected_split!r}."
        )
    frame = frame.dropna(subset=["ID_Poligon", "kelas", *FEATURES]).copy()
    frame[FEATURES] = frame[FEATURES].apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES)
    if frame.empty:
        raise ValueError(f"CSV {path.name} tidak memiliki baris fitur numerik yang valid.")
    return frame


def main() -> None:
    train = load_split(DATASET_DIR / "train_dataset.csv", "train")
    test = load_split(DATASET_DIR / "test_dataset.csv", "test")
    overlap = set(train["ID_Poligon"].astype(str)) & set(test["ID_Poligon"].astype(str))
    if overlap:
        examples = sorted(overlap)[:10]
        raise ValueError(
            "Data leakage: ID_Poligon yang sama ditemukan pada train dan test. "
            f"Contoh: {examples}"
        )

    model = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train[FEATURES], train["kelas"].astype(str))
    predictions = model.predict(test[FEATURES])
    class_names = sorted(
        set(train["kelas"].astype(str)) | set(test["kelas"].astype(str))
    )
    report = classification_report(
        test["kelas"].astype(str),
        predictions,
        labels=class_names,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(
        test["kelas"].astype(str),
        predictions,
        labels=class_names,
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ARTIFACT_DIR / "random_forest_lulc.joblib")
    (ARTIFACT_DIR / "classification_report.json").write_text(
        json.dumps(
            {
                "accuracy": accuracy_score(test["kelas"].astype(str), predictions),
                "train_rows": len(train),
                "test_rows": len(test),
                "train_polygons": int(train["ID_Poligon"].nunique()),
                "test_polygons": int(test["ID_Poligon"].nunique()),
                "classes": class_names,
                "classification_report": report,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        matrix,
        index=[f"actual_{name}" for name in class_names],
        columns=[f"predicted_{name}" for name in class_names],
    ).to_csv(ARTIFACT_DIR / "confusion_matrix.csv")
    pd.DataFrame(
        {"feature": FEATURES, "importance": model.feature_importances_}
    ).sort_values("importance", ascending=False).to_csv(
        ARTIFACT_DIR / "feature_importance.csv",
        index=False,
    )

    print(f"Akurasi test: {accuracy_score(test['kelas'].astype(str), predictions):.4f}")
    print(f"Baris train/test: {len(train)} / {len(test)}")
    print(f"Poligon train/test: {train['ID_Poligon'].nunique()} / {test['ID_Poligon'].nunique()}")
    print(f"Artefak tersimpan di: {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
