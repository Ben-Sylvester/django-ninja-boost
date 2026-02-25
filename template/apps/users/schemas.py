
from ninja import Schema  # Capital S — was UserCreate(schema) in original template


class UserOut(Schema):
    id: int
    name: str
    email: str


class UserCreate(Schema):      # Bug fix: was `class UserCreate(schema):` — undefined name
    username: str
    email: str
    password: str


class UserUpdate(Schema):
    username: str | None = None
    email: str | None = None
