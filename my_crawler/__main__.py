import asyncio

from .main import main
from . import URL

if __name__ == '__main__':

    asyncio.run(main(URL))