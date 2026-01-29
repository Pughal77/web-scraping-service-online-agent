from bs4 import BeautifulSoup

async def process_data(html_content: str) -> str:
    """
    Parses a string of HTML and returns the human-readable text.
    """
    # 1. Initialize the soup object with the 'html.parser'
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 2. Optional: Remove script and style elements so their code 
    # doesn't show up in your final text.
    for script_or_style in soup(["script", "style"]):
        script_or_style.decompose()

    # 3. Get text, using a separator to ensure words don't 
    # stick together (e.g., between a </div> and a <div>)
    text = soup.get_text(separator=' ')

    # 4. Clean up extra whitespace/newlines
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    clean_text = '\n'.join(chunk for chunk in chunks if chunk)

    return clean_text

