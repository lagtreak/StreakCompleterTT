from dataclasses import dataclass


@dataclass
class User:
    username: str
    message: str = ""
    enabled: bool = True
