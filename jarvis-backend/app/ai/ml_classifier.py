import os
import json
import logging
from typing import Tuple, List, Dict, Optional

logger = logging.getLogger("jarvis.ai.ml_classifier")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available. ML Intent Classifier operating in fallback mode.")


class MLIntentClassifier:
    """
    Genuine ML Intent Classifier for JARVIS Agent.
    Implements TF-IDF feature extraction and Logistic Regression probability distribution
    over labeled training data in data/intents.json.
    
    Treated as a baseline statistical classifier designed to grow with additional user traces.
    """

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or os.path.join(
            os.path.dirname(__file__), "data", "intents.json"
        )
        self.vectorizer: Optional[Any] = None
        self.classifier: Optional[Any] = None
        self.classes: List[str] = []
        self.is_trained = False
        self._train_baseline()

    def _train_baseline(self) -> None:
        if not SKLEARN_AVAILABLE:
            return

        if not os.path.exists(self.data_path):
            logger.warning(f"Training dataset not found at {self.data_path}")
            return

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data: List[Dict[str, str]] = json.load(f)

            if not data:
                return

            texts = [item["text"] for item in data]
            labels = [item["intent"] for item in data]

            self.vectorizer = TfidfVectorizer(
                ngram_range=(1, 2),
                lowercase=True,
                strip_accents="unicode",
                sublinear_tf=True
            )
            X = self.vectorizer.fit_transform(texts)

            self.classifier = LogisticRegression(
                C=1.0,
                max_iter=400,
                random_state=42,
                class_weight="balanced"
            )
            self.classifier.fit(X, labels)
            self.classes = list(self.classifier.classes_)
            self.is_trained = True
            logger.info(f"ML Intent Classifier trained on {len(texts)} samples across {len(self.classes)} intents.")
        except Exception as e:
            logger.error(f"Error training ML Intent Classifier: {e}")
            self.is_trained = False

    def predict(self, text: str) -> Tuple[str, float]:
        """
        Predicts intent and calibrated confidence for a user utterance.
        Returns: (predicted_intent, confidence_score)
        """
        cleaned = text.strip()
        if not cleaned:
            return "UNKNOWN", 0.0

        if not self.is_trained or not self.vectorizer or not self.classifier:
            return "UNKNOWN", 0.0

        try:
            X = self.vectorizer.transform([cleaned])
            probs = self.classifier.predict_proba(X)[0]
            max_idx = probs.argmax()
            predicted_intent = str(self.classifier.classes_[max_idx])
            confidence = float(probs[max_idx])
            return predicted_intent, round(confidence, 3)
        except Exception as e:
            logger.warning(f"ML intent prediction error: {e}")
            return "UNKNOWN", 0.0

    def retrain(self, additional_samples: Optional[List[Dict[str, str]]] = None) -> bool:
        """Allows dynamic training as new user traces and verified corrections arrive."""
        if not SKLEARN_AVAILABLE:
            return False

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data: List[Dict[str, str]] = json.load(f)

            if additional_samples:
                data.extend(additional_samples)
                with open(self.data_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

            self._train_baseline()
            return self.is_trained
        except Exception as e:
            logger.error(f"Failed to retrain classifier: {e}")
            return False


ml_intent_classifier = MLIntentClassifier()
