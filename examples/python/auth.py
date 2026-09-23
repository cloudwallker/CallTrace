from services import validate, find_user, issue_token, audit


class UserService:
    @staticmethod
    async def login(email, provider):
        validate(email)
        user = await find_user(email)
        if user:
            audit(2)
            issue_token(user)
        else:
            provider.notify(email)
