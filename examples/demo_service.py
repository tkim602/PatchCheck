"""Small fixture used by the repository's live pull-request demo."""


def format_status(value: str, *, strict: bool = True) -> str:
    normalized = value.strip().lower()
    if strict and not normalized:
        raise ValueError("status cannot be empty")
    return normalized
