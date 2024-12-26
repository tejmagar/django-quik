from dataclasses import dataclass
from typing import List


@dataclass
class Configuration:
    host: str
    port: int
    proxy_port: int
    watch_dirs: List[str]
