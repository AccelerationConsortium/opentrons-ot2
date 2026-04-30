import asyncio

from unitelabs.cdk import run

from . import create_app


async def main() -> None:
    """Run the connector application."""

    await run(create_app)


if __name__ == "__main__":
    asyncio.run(main())
