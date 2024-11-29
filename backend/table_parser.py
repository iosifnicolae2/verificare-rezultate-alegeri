def parse_table_votes(table_data):
    """Parse candidate votes from table format"""
    # Skip header row and empty rows
    candidates = []
    if not table_data or len(table_data) < 2:
        return []
        
    for row in table_data[1:]:  # Skip header row
        if len(row) >= 3 and row[1] and row[2]:  # Ensure row has name and votes
            try:
                votes = int(row[2])
                name = row[1].strip()
                # Only add if name is in CANDIDATE_NAMES
                if name in CANDIDATE_NAMES:
                    candidates.append({
                        "name": name,
                        "votes": votes
                    })
            except ValueError:
                continue
    
    return candidates

def format_table_results(candidates):
    """Format the parsed table results"""
    if not candidates:
        return {
            "total_votes": 0,
            "candidates": []
        }
    
    total_votes = sum(c["votes"] for c in candidates)
    
    formatted_candidates = []
    for candidate in candidates:
        percentage = (candidate["votes"] / total_votes * 100) if total_votes > 0 else 0
        formatted_candidates.append({
            "name": candidate["name"],
            "votes": candidate["votes"],
            "percentage": round(percentage, 2)
        })
    
    # Sort by votes in descending order
    formatted_candidates.sort(key=lambda x: x["votes"], reverse=True)
    
    return {
        "total_votes": total_votes,
        "candidates": formatted_candidates
    }
from constants import CANDIDATE_NAMES
