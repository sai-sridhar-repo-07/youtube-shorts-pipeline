import json
import uuid
from pathlib import Path
from datetime import datetime

from pipeline.config import JOBS_DIR

STAGES = [
    "research",
    "draft",
    "broll",
    "voiceover",
    "captions",
    "music",
    "assemble",
    "thumbnail",
    "upload",
]


class PipelineState:
    def __init__(self, job_id: str = None):
        self.job_id = job_id or uuid.uuid4().hex[:8]
        self._path = JOBS_DIR / f"{self.job_id}.json"
        self._data: dict = {
            "job_id": self.job_id,
            "created_at": datetime.now().isoformat(),
            "completed_stages": [],
            "artifacts": {},
            "draft": {},
            "topic": "",
        }
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, job_id: str) -> "PipelineState":
        state = cls(job_id)
        if not state._path.exists():
            raise FileNotFoundError(f"No job found with ID: {job_id}")
        with open(state._path) as f:
            state._data = json.load(f)
        return state

    @classmethod
    def new(cls, topic: str) -> "PipelineState":
        state = cls()
        state._data["topic"] = topic
        state.save()
        return state

    def mark_done(self, stage: str, **artifacts) -> None:
        if stage not in self._data["completed_stages"]:
            self._data["completed_stages"].append(stage)
        self._data["artifacts"].update(artifacts)
        self.save()

    def is_done(self, stage: str) -> bool:
        return stage in self._data["completed_stages"]

    def artifact(self, key: str) -> str:
        return self._data["artifacts"].get(key, "")

    @property
    def topic(self) -> str:
        return self._data.get("topic", "")

    @property
    def draft(self) -> dict:
        return self._data.get("draft", {})

    @draft.setter
    def draft(self, value: dict) -> None:
        self._data["draft"] = value
        self.save()

    def save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        tmp.rename(self._path)

    @property
    def job_dir(self) -> Path:
        d = JOBS_DIR / self.job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def __repr__(self) -> str:
        return f"PipelineState(job_id={self.job_id}, done={self._data['completed_stages']})"
