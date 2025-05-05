import re


def remove_triple_backticks(text: str) -> str:
    text = text.strip()
    pattern_start = r'^\s*```(?:markdown)?\s*\n'
    pattern_end = r'\n\s*```\s*$'

    if re.match(pattern_start, text, flags=re.IGNORECASE):
        text = re.sub(pattern_start, '', text, flags=re.IGNORECASE)
        text = re.sub(pattern_end, '', text)

    return text.strip()
