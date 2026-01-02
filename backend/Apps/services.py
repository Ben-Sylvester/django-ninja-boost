from django.contrib.auth import get_user_model
from .schemas import UserCreate, UserOut

User = get_user_model()


class UserService:

    @staticmethod
    def list_users():
        users = User.objects.all()
        return [UserOut(id=u.id, name=u.username) for u in users]

    @staticmethod
    def create_user(data: UserCreate):
        user = User.objects.create_user(
            username=data.username,
            email=data.email,
            password=data.password,
        )
        return UserOut(id=user.id, name=user.username)

    @staticmethod
    def get_user(user_id: int):
        user = User.objects.get(id=user_id)
        return UserOut(id=user.id, name=user.username)


# from .repositories import UserRepository
# from .validators import ensure_username_available
# from .schemas import UserCreate, UserOut
# from django.db import transaction
# from utils.emails import send_welcome_email


# class UserService:

#     @staticmethod
#     @transaction.atomic
#     def create_user(data: UserCreate) -> UserOut:

#         # domain validation
#         ensure_username_available(data.username)

#         # persistence
#         user = UserRepository.create_user(data)

#         # side effects
#         send_welcome_email(user.email)

#         # output
#         return UserRepository.to_schema(user)

#     @staticmethod
#     def get_user(user_id: int) -> UserOut:
#         user = UserRepository.get_by_id(user_id)
#         return UserRepository.to_schema(user)

#     @staticmethod
#     def list_users():
#         queryset = UserRepository.get_all()
#         return UserRepository.to_list_schema(queryset)
