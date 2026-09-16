from service import leaf


async def main(provider):
    if await leaf():
        for i in (1, 2):
            leaf()
    else:
        provider.missing()
    main(provider)
