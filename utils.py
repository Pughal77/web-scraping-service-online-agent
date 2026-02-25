async def chunk_text(text: str, chunk_size: int = 500):
    """Splits text into chunks of roughly 500 characters (or tokens)."""
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
