from typing import List, Tuple, Optional
from difflib import SequenceMatcher
import os

class EditContentNotFoundError(Exception):
    """Raised when edit content cannot be found in the file."""
    pass

SIMILARITY_THRESHOLD = 0.6  # Minimum similarity score (0.0-1.0) required for a line to match
GAP_PENALTY = -0.2  # No longer used since switching to sequential matching

def line_similarity(line1: str, line2: str) -> float:
    """Calculate how similar two lines are using difflib.SequenceMatcher.
    Returns a score between 0.0 (completely different) and 1.0 (identical)."""
    return SequenceMatcher(None, line1, line2).ratio()

def forward_pass(change_lines: List[str], full_lines: List[str], start: int = 0) -> Tuple[float, List[int]]:
    """Search for matches going forward through the file."""
    best_matches = []
    best_score = 0.0
    
    if os.environ.get('DEBUG'):
        print("\nDEBUG: Forward pass:")

    # Try each possible starting position
    for start_pos in range(start, len(full_lines) - len(change_lines) + 1):
        current_matches = []
        matched_count = 0
        
        # Try to match lines from this position
        for i, line in enumerate(change_lines):
            if line_similarity(line, full_lines[start_pos + i]) >= SIMILARITY_THRESHOLD:
                current_matches.append(start_pos + i)
                matched_count += 1
                
                # Early return for perfect sequential match
                if matched_count == len(change_lines):
                    if current_matches == list(range(start_pos, start_pos + len(change_lines))):
                        if os.environ.get('DEBUG'):
                            print(f"DEBUG:   Found perfect match at line {start_pos+1}")
                            for i, pos in enumerate(current_matches):
                                print(f"DEBUG:     {i+1}: '{full_lines[pos]}'")
                        return 1.0, current_matches

        # Calculate score for this match
        if current_matches:
            # Score based on how many lines matched and their sequentiality
            match_ratio = len(current_matches) / len(change_lines)
            gaps = sum(b - a - 1 for a, b in zip(current_matches, current_matches[1:])) if len(current_matches) > 1 else 0
            score = match_ratio + (GAP_PENALTY * gaps)
            
            if os.environ.get('DEBUG'):
                print(f"DEBUG:   Potential match at line {start_pos+1}")
                print(f"DEBUG:     Matched {len(current_matches)}/{len(change_lines)} lines, {gaps} gaps, score: {score}")
                for i, pos in enumerate(current_matches):
                    print(f"DEBUG:     {i+1}: '{full_lines[pos]}'")
            
            if score > best_score:
                best_score = score
                best_matches = current_matches

    if best_matches:
        if os.environ.get('DEBUG'):
            print(f"DEBUG:   Best match has score: {best_score}")
        return best_score, best_matches
    
    return 0.0, []

def backward_pass(change_lines: List[str], full_lines: List[str], end: int = None) -> Tuple[float, List[int]]:
    """Search for matches going backward through the file."""
    best_matches = []
    best_score = 0.0
    max_start = len(full_lines) - len(change_lines)
    current_index = len(full_lines) - 1 if end is None else end
    
    if os.environ.get('DEBUG'):
        print("\nDEBUG: Backward pass:")

    # Try each possible ending position
    for end_pos in range(current_index, len(change_lines) - 1, -1):
        current_matches = []
        matched_count = 0
        
        # Try to match lines from this position backwards
        for i, line in enumerate(reversed(change_lines)):
            pos = end_pos - i
            if pos < 0:
                break
                
            if line_similarity(line, full_lines[pos]) >= SIMILARITY_THRESHOLD:
                current_matches.insert(0, pos)  # Insert at start to maintain order
                matched_count += 1
                
                # Early return for perfect sequential match
                if matched_count == len(change_lines):
                    if current_matches == list(range(pos, pos + len(change_lines))):
                        if os.environ.get('DEBUG'):
                            print(f"DEBUG:   Found perfect match ending at line {end_pos+1}")
                            for i, pos in enumerate(current_matches):
                                print(f"DEBUG:     {i+1}: '{full_lines[pos]}'")
                        return 1.0, current_matches

        # Calculate score for this match
        if current_matches:
            # Score based on how many lines matched and their sequentiality
            match_ratio = len(current_matches) / len(change_lines)
            gaps = sum(b - a - 1 for a, b in zip(current_matches, current_matches[1:])) if len(current_matches) > 1 else 0
            score = match_ratio + (GAP_PENALTY * gaps)
            
            if os.environ.get('DEBUG'):
                print(f"DEBUG:   Potential match ending at line {end_pos+1}")
                print(f"DEBUG:     Matched {len(current_matches)}/{len(change_lines)} lines, {gaps} gaps, score: {score}")
                for i, pos in enumerate(current_matches):
                    print(f"DEBUG:     {i+1}: '{full_lines[pos]}'")
            
            if score > best_score:
                best_score = score
                best_matches = current_matches

    if best_matches:
        if os.environ.get('DEBUG'):
            print(f"DEBUG:   Best match has score: {best_score}")
        return best_score, best_matches
    
    return 0.0, []

def find_range(full_lines: List[str], changed_lines: List[str], start: int = 0) -> Tuple[int, int]:
    """Find the location of a code block within a file.
    
    Args:
        full_lines: The complete file content to search in
        changed_lines: The code block to find
        start: Line number to start searching from
    
    Returns:
        Tuple[int, int]: Start and end line numbers of the match
        
    Raises:
        EditContentNotFoundError: If the block can't be found or match score is too low
        ValueError: If start position is invalid
    
    The matching process:
    1. Validates inputs and checks content lengths
    2. Performs forward and backward passes to find matches
    3. Requires matches to be sequential (not just similar lines)
    4. Both passes must succeed with high similarity scores
    5. Returns the range that encompasses all matching lines
    """
    _validate_inputs(full_lines, changed_lines, start)
    
    # Add validation for content length
    if len(changed_lines) > len(full_lines):
        raise EditContentNotFoundError(
            f"Search pattern ({len(changed_lines)} lines) is longer than content ({len(full_lines)} lines).\n"
            f"Pattern starts with:\n{changed_lines[0]}\n"
            f"Content starts with:\n{full_lines[0]}"
        )
    
    if not changed_lines:
        return (start, start)
    
    # Perform bidirectional matching
    if os.environ.get('DEBUG'):
        print("\nDEBUG: Starting bidirectional matching")
    
    forward_score, forward_matches = forward_pass(changed_lines, full_lines, start)
    backward_score, backward_matches = backward_pass(changed_lines, full_lines)
    
    if os.environ.get('DEBUG'):
        print(f"\nDEBUG: Forward score: {forward_score}")
        print(f"DEBUG: Forward matches: {forward_matches}")
        print(f"DEBUG: Backward score: {backward_score}")
        print(f"DEBUG: Backward matches: {backward_matches}")

    if not forward_matches or not backward_matches:
        _raise_no_match_error(changed_lines, start, 0.0, full_lines)
    
    # Check if both passes found the same range
    forward_range = list(range(min(forward_matches), max(forward_matches) + 1))
    backward_range = list(range(min(backward_matches), max(backward_matches) + 1))
    
    if forward_range == backward_range:
        # Both passes found same range - use the better score
        cumulative_score = max(forward_score, backward_score)
        start_index = min(forward_matches)
        end_index = max(forward_matches) + 1
    else:
        # Different ranges - check for overlap and consistency
        overlap = set(forward_matches) & set(backward_matches)
        if overlap:
            # Use the overlapping range if it's sequential
            overlap_list = sorted(overlap)
            if overlap_list == list(range(min(overlap_list), max(overlap_list) + 1)):
                # Overlapping section is sequential - use it
                overlap_score = len(overlap) / len(changed_lines)  # Score based on overlap completeness
                cumulative_score = max(forward_score, backward_score) * overlap_score
                start_index = min(overlap)
                end_index = max(overlap) + 1
            else:
                # Overlapping matches aren't sequential - use better scoring range
                if forward_score > backward_score:
                    cumulative_score = forward_score
                    start_index = min(forward_matches)
                    end_index = max(forward_matches) + 1
                else:
                    cumulative_score = backward_score
                    start_index = min(backward_matches)
                    end_index = max(backward_matches) + 1
        else:
            # No overlap - average the scores
            cumulative_score = (forward_score + backward_score) / 2
            start_index = min(forward_matches)
            end_index = max(backward_matches) + 1
    
    if cumulative_score < SIMILARITY_THRESHOLD:
        _raise_no_match_error(changed_lines, start, cumulative_score, full_lines)
    
    if os.environ.get('DEBUG'):
        print(f"\nDEBUG: Final score: {cumulative_score}")
        print(f"DEBUG: Final range: {start_index+1}-{end_index}")
    
    return (start_index, end_index)

def _validate_inputs(full_lines: List[str], changed_lines: List[str], start: int) -> None:
    if start >= len(full_lines):
        raise ValueError(f"Start position {start} is beyond content length {len(full_lines)}")

def _raise_no_match_error(changed_lines: List[str], start: int, best_score: float, full_lines: List[str]) -> None:
    sample = "\n".join(changed_lines[:3]) + ("..." if len(changed_lines) > 3 else "")
    
    if os.environ.get('DEBUG'):
        print("\nDEBUG: Match failure analysis:")
        print(f"DEBUG: Search started from line {start}")
        print(f"DEBUG: Best match score ({best_score:.3f}) below threshold {SIMILARITY_THRESHOLD}")
        print("DEBUG: Content being searched for:")
        
        # Track all matches with their scores
        matches_with_scores = []
        
        for i, line in enumerate(changed_lines, 1):
            # Find best matching line for each changed line
            best_match_line = None
            best_line_score = 0.0
            
            for full_idx, full_line in enumerate(full_lines):
                score = line_similarity(line, full_line)
                if score > best_line_score:
                    best_line_score = score
                    best_match_line = full_idx
            
            print(f"DEBUG: {i}: '{line}' (Best match: line {best_match_line + 1}, score: {best_line_score:.3f})")
            matches_with_scores.append((best_match_line, best_line_score))
        
        # Find best continuous sequence close to the length we want
        target_length = len(changed_lines)
        best_sequence = []
        best_sequence_score = 0.0
        
        for start_idx in range(len(full_lines)):
            current_sequence = []
            total_score = 0.0
            
            # Try to build a sequence starting here
            for i, (match_line, score) in enumerate(matches_with_scores):
                if match_line == start_idx + len(current_sequence):
                    current_sequence.append(match_line)
                    total_score += score
                else:
                    break
            
            # Score this sequence based on length and average match quality
            if current_sequence:
                sequence_score = (len(current_sequence) / target_length) * (total_score / len(current_sequence))
                if sequence_score > best_sequence_score:
                    best_sequence = current_sequence
                    best_sequence_score = sequence_score
        
        if best_sequence:
            best_start = best_sequence[0]
            best_end = best_sequence[-1]
            
            print(f"\nDEBUG: Best matching range: lines {best_start + 1}-{best_end + 1}")
            print(f"DEBUG: Sequence of matching lines: {[x + 1 for x in best_sequence]}")
            print("DEBUG: Content at best matching range:")
            for line_num in range(best_start, best_end + 1):
                print(f"DEBUG: {line_num + 1}: {full_lines[line_num]}")
    
    raise EditContentNotFoundError(
        f"Could not find matching block after line {start}. "
        f"Looking for:\n{sample}\n"
        f"Best match score: {best_score:.2f}"
    )

def _parse_debug_file(debug_file_path: str) -> Tuple[List[str], List[str]]:
    """Parse a debug file containing FIND: and ORIGINAL: sections.
    
    Returns:
        Tuple[List[str], List[str]]: (original_content, find_pattern)
        - original_content: The file content to search in
        - find_pattern: The code block to find
        
    The debug file format helps diagnose matching failures by showing:
    - What we're trying to find (FIND: section)
    - Where we're trying to find it (ORIGINAL: section)
    - What went wrong if it failed (ERROR: section)
    """
    with open(debug_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split into sections using the headers
    sections = {}
    current_section = None
    current_lines = []
    
    for line in content.splitlines():
        # Check for section headers
        if line in ["FIND:", "ORIGINAL:", "ERROR:"]:
            if current_section:
                sections[current_section] = current_lines
            current_section = line.rstrip(':')
            current_lines = []
            continue
            
        # Only collect lines if we're in a section
        if current_section:
            current_lines.append(line)
    
    # Store the last section
    if current_section:
        sections[current_section] = current_lines
    
    if 'FIND' not in sections or 'ORIGINAL' not in sections:
        raise ValueError("Debug file must contain both 'FIND:' and 'ORIGINAL:' sections")
    
    # Remove empty lines at start/end of each section but keep empty lines in middle
    find_content = _trim_empty_lines(sections['FIND'])
    original_content = _trim_empty_lines(sections['ORIGINAL'])
    
    # Return original_content first (the content to search in), then find_content (the pattern to find)
    return original_content, find_content

def _trim_empty_lines(lines: List[str]) -> List[str]:
    """Remove empty lines from start and end but keep them in the middle."""
    # Find first non-empty line
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
        
    # Find last non-empty line
    end = len(lines)
    while end > start and not lines[end - 1].strip():
        end -= 1
        
    return lines[start:end]

def main():
    import sys
    import argparse
    
    # Set DEBUG flag when running directly
    os.environ['DEBUG'] = '1'
    
    parser = argparse.ArgumentParser(description='Test content finding in a debug file')
    parser.add_argument('debug_file', help='Path to the debug file')
    args = parser.parse_args()
    
    try:
        full_content, search_content = _parse_debug_file(args.debug_file)
        
        print(f"Searching for {len(search_content)} lines in content of {len(full_content)} lines")
        print("\nSearch content:")
        print("-" * 40)
        print("\n".join(search_content))
        print("-" * 40)
        
        try:
            match_range = find_range(full_content, search_content)
            print(f"\nFound match at lines {match_range[0]+1}-{match_range[1]}")
            print("\nMatched content:")
            print("-" * 40)
            print("\n".join(full_content[match_range[0]:match_range[1]]))
            print("-" * 40)
        except EditContentNotFoundError as e:
            print(f"\nError: {str(e)}")
            
    except Exception as e:
        print(f"Error processing debug file: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()