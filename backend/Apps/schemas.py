from ninja import Schema

class UserOut(Schema):
    id: int
    name: str

class UserCreate(schema):
    pass