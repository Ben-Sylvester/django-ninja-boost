from ninja import Schema   # Capital S — was UserCreate(schema) in original template
from typing import Optional


class UserOut(Schema):
    id: int
    name: str
    email: str


class UserCreate(Schema):      # Bug fix: was `class UserCreate(schema):` — undefined name
    username: str
    email: str
    password: str


class UserUpdate(Schema):
    username: Optional[str] = None
    email: Optional[str] = None
