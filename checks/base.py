from dataclasses import dataclass
from typing import Optional


@dataclass
class CheckExecution:
    name: str
    report: str
    success: bool = True
    should_stop: bool = False
    error: Optional[str] = None


class CheckRunner:
    name: str = "unnamed"

    def run(self, *, json_path: str, runtime_cfg, stop_event=None, embedder=None) -> CheckExecution:
        raise NotImplementedError
