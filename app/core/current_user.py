from fastapi import Header


def get_current_user_id(x_user_id: int | None = Header(default=None)) -> int:
    return x_user_id or 1
