from ninja_boost import AutoRouter

from .schemas import UserCreate, UserOut
from .services import UserService

router = AutoRouter(tags=["Users"])


@router.get("/", response=list[UserOut])
def list_users(request, ctx):
    """List users. Auto-paginated via ?page=&size=. ctx injected automatically."""
    return UserService.list_users()   # returns QuerySet — paginated efficiently


@router.get("/{user_id}", response=UserOut, paginate=False)
def get_user(request, ctx, user_id: int):
    """Get a single user by ID."""
    return UserService.get_user(user_id)


@router.post("/", response=UserOut, paginate=False)
def create_user(request, ctx, payload: UserCreate):
    """Create a new user."""
    return UserService.create_user(payload)
