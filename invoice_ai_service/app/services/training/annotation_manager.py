import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class AnnotationManager:
    def __init__(self, annotation_file: str = "training_data/annotated/labels.json"):
        self.annotation_file = annotation_file
        self.labels = {}
        self._load_annotations()

    def _load_annotations(self):
        if os.path.exists(self.annotation_file):
            try:
                with open(self.annotation_file, 'r', encoding='utf-8') as f:
                    self.labels = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load annotations from {self.annotation_file}: {e}")
                self.labels = {}
        else:
            self.labels = {}

    def _save_annotations(self):
        os.makedirs(os.path.dirname(self.annotation_file), exist_ok=True)
        try:
            with open(self.annotation_file, 'w', encoding='utf-8') as f:
                json.dump(self.labels, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save annotations to {self.annotation_file}: {e}")

    def get_annotation(self, file_id: str) -> Optional[Dict[str, Any]]:
        return self.labels.get(file_id)

    def add_annotation(self, file_id: str, data: Dict[str, Any]):
        self.labels[file_id] = data
        self._save_annotations()

    def get_all_annotations(self) -> Dict[str, Dict[str, Any]]:
        return self.labels
