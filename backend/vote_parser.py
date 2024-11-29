import re
from constants import CANDIDATE_NAMES

def parse_candidate_votes(text):
    """
    Parse votes for each candidate from the text.
    Returns a list of tuples (name, votes)
    """
    # Pattern to match fully uppercase candidate name followed by number
    pattern = r'([A-ZĂÎÂȘȚ][A-ZĂÎÂȘȚ\s\-\.]+)\s+(\d+)'
    
    # Find all matches in text
    matches = re.findall(pattern, text)
    
    # Process matches into dictionary format
    results = []
    for name, votes in matches:
        # Clean up name and convert votes to int
        name = name.strip()
        votes = int(votes)
        # Validate against CANDIDATE_NAMES
        if name in CANDIDATE_NAMES and votes >= 0:
            results.append({
                "name": name,
                "votes": votes
            })
            
    return results

def format_results(results):
    """Format results as a readable string"""
    output = []
    for i, result in enumerate(results, 1):
        output.append(f"{i} {result['name']} {result['votes']}")
    return "\n".join(output)

def compare_vote_results(text_votes, ocr_votes):
    """Compare two sets of voting results and return differences"""
    differences = []
    all_match = True
    
    # Create dictionaries for easier comparison
    text_dict = {v["name"]: v["votes"] for v in text_votes}
    ocr_dict = {v["name"]: v["votes"] for v in ocr_votes}
    
    # Check all expected candidate names
    for name in CANDIDATE_NAMES:
        text_votes = text_dict.get(name)
        ocr_votes = ocr_dict.get(name)
        
        if text_votes is None or ocr_votes is None:
            all_match = False
            differences.append({
                "name": name,
                "text_votes": text_votes,
                "ocr_votes": ocr_votes
            })
        elif text_votes != ocr_votes:
            all_match = False
            differences.append({
                "name": name,
                "text_votes": text_votes,
                "ocr_votes": ocr_votes
            })
    
    # Check for names in OCR that weren't in text
    for name, votes in ocr_dict.items():
        if name not in text_dict:
            all_match = False
            differences.append({
                "name": name,
                "text_votes": None,
                "ocr_votes": votes
            })
    
    return {
        "all_match": all_match,
        "differences": differences
    }
