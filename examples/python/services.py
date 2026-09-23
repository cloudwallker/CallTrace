def validate(email):
    return email


async def find_user(email):
    return email


def issue_token(user):
    return user


def audit(n):
    if n:
        audit(n - 1)
