from ninja.security import HttpBearer


class default_auth(HttpBearer):
    def authenticate(self, request, token):
        if token == "demo":
            return {"user_id": 1}
        return None
