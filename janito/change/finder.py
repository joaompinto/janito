from typing import List, Tuple
from difflib import SequenceMatcher

class EditContentNotFoundError(ValueError):
    """Raised when edit content cannot be found in the target file."""
    pass

SIMILARITY_THRESHOLD = 0.8  # Minimum similarity required for a match

def find_range(full_lines: List[str], changed_lines: List[str], start: int = 0) -> Tuple[int, int]:
    """Find the range of the first occurrence of the changed_lines in the full_lines list.
    
    Args:
        full_lines: The complete text content to search within
        changed_lines: The block of lines to find
        start: The line number to start searching from
        
    Returns:
        Tuple of (start_line, end_line) where the block was found
        
    Raises:
        ValueError: If no matching block is found with sufficient similarity
    """
    _validate_inputs(full_lines, changed_lines, start)
    
    if not changed_lines:
        return (start, start)

    best_match, best_score = _find_best_matching_block(full_lines, changed_lines, start)
    
    if not best_match or best_score < SIMILARITY_THRESHOLD:
        _raise_no_match_error(changed_lines, start, best_score)
        
    return best_match

def _validate_inputs(full_lines: List[str], changed_lines: List[str], start: int) -> None:
    if start >= len(full_lines):
        raise ValueError(f"Start position {start} is beyond content length {len(full_lines)}")

def _find_best_matching_block(full_lines: List[str], changed_lines: List[str], start: int) -> Tuple[Tuple[int, int], float]:
    best_match = None
    best_score = 0.0
    
    for i in range(start, len(full_lines) - len(changed_lines) + 1):
        window = full_lines[i:i + len(changed_lines)]
        if len(window) != len(changed_lines):
            continue
            
        similarity = _calculate_similarity(window, changed_lines)
        
        if similarity > best_score:
            best_score = similarity
            best_match = (i, i + len(changed_lines))
            
            if similarity == 1.0:  # Early exit on perfect match
                break
    
    return best_match, best_score

def _calculate_similarity(window: List[str], changed_lines: List[str]) -> float:
    return sum(
        SequenceMatcher(None, a, b).ratio() 
        for a, b in zip(window, changed_lines)
    ) / len(changed_lines)

def _raise_no_match_error(changed_lines: List[str], start: int, best_score: float) -> None:
    sample = "\n".join(changed_lines[:3]) + ("..." if len(changed_lines) > 3 else "")
    raise EditContentNotFoundError(
        f"Could not find matching block after line {start}. "
        f"Looking for:\n{sample}\n"
        f"Best match score: {best_score:.2f}"
    )