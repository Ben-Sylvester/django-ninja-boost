from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from .schemas import UserCreate, UserOut

User = get_user_model()


class UserService:

    @staticmethod
    def list_users():
        """Return a QuerySet — auto_paginate will COUNT + slice efficiently."""
        return User.objects.all()

    @staticmethod
    def get_user(user_id: int) -> UserOut:
        user = get_object_or_404(User, id=user_id)
        return UserOut(id=user.id, name=user.username, email=user.email)

    @staticmethod
    def create_user(data: UserCreate) -> UserOut:
        user = User.objects.create_user(
            username=data.username,
            email=data.email,
            password=data.password,
        )
        return UserOut(id=user.id, name=user.username, email=user.email)
