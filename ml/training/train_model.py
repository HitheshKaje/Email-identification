"""Train and save JobMail's TF-IDF + LogisticRegression email classifier."""

import json
from pathlib import Path
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

ML_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = ML_DIR / "dataset" / "training_emails.json"
DEFAULT_MODEL_PATH = ML_DIR / "models" / "email_classifier.joblib"


def format_email_features(subject: str, body: str, sender: str = "") -> str:
    """Combine weighted subject, sender domain/name, and body into classification text."""
    clean_subject = (subject or "").strip()
    clean_sender = (sender or "").strip()
    clean_body = (body or "").strip()
    # Repeat subject to increase signal weight relative to long email bodies.
    return f"{clean_subject} {clean_subject} | sender: {clean_sender} | {clean_body}".strip()


def load_training_dataset(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    extra_samples: list[dict[str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if extra_samples:
        raw = list(raw) + list(extra_samples)
    texts = [
        format_email_features(
            row.get("subject", ""),
            row.get("body", ""),
            row.get("sender", ""),
        )
        for row in raw
    ]
    labels = [str(row["category"]).strip().upper() for row in raw]
    return texts, labels


def build_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 3),
                    sublinear_tf=True,
                    min_df=1,
                    max_features=12000,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    C=5.0,
                    random_state=42,
                ),
            ),
        ]
    )


def train_and_save_model(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    extra_samples: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    texts, labels = load_training_dataset(
        dataset_path=dataset_path,
        extra_samples=extra_samples,
    )
    x_train, x_val, y_train, y_val = train_test_split(
        texts,
        labels,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )
    eval_pipeline = build_pipeline()
    eval_pipeline.fit(x_train, y_train)
    val_preds = eval_pipeline.predict(x_val)
    val_accuracy = float(accuracy_score(y_val, val_preds))
    report = classification_report(y_val, val_preds, zero_division=0)

    # Fit final production pipeline on 100% of available labeled examples.
    final_pipeline = build_pipeline()
    final_pipeline.fit(texts, labels)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_pipeline, model_path)
    return {
        "model_path": str(model_path),
        "sample_count": len(texts),
        "validation_accuracy": val_accuracy,
        "report": report,
    }


if __name__ == "__main__":
    summary = train_and_save_model()
    print(f"Trained model on {summary['sample_count']} samples")
    print(f"Validation accuracy: {summary['validation_accuracy']:.3f}")
    print(f"Saved model to: {summary['model_path']}")
    print(summary["report"])
