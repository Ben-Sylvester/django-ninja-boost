from core.router import AutoRouter
from .schemas import UserOut

router = AutoRouter(tags=["Users"])


@router.get("/", response=list[UserOut])
def list_users(request, ctx):
    return [
        UserOut(id=1, name="Alice"),
        UserOut(id=2, name="Bob"),
    ]
