import json
import os
import pdfplumber
import requests
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from vote_parser import parse_candidate_votes, format_results, compare_vote_results
from table_parser import parse_table_votes, format_table_results
import pdf2image
from PIL import Image
import io
import base64
import sys
import subprocess
import pytesseract
from google.cloud import vision
from datetime import datetime

timestamp = int(datetime.now().timestamp())

def check_poppler_installation():
    """Check if poppler is installed and accessible"""
    try:
        # Try to run pdftoppm (part of poppler) with version flag
        subprocess.run(['pdftoppm', '-v'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        print("Error: Poppler is not installed or not in PATH!")
        print("Please install poppler:")
        print("  On macOS: brew install poppler")
        print("  On Linux: sudo apt-get install poppler-utils")
        print("  On Windows: download from http://blog.alivate.com.au/poppler-windows/")
        return False


def extract_pdf_content(pdf_path, use_google_vision=False, page_number=2):
    """
    Extract all content from a PDF file including text, tables, and images.
    Returns a JSON structure with all the content.
    """
    if not check_poppler_installation():
        sys.exit(1)
    """
    Extract all content from a PDF file including text, tables, and images.
    Returns a JSON structure with all the content.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    result = {
        "pages": []
    }

    # Extract text and tables using pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        if page_number > len(pdf.pages):
            raise ValueError(f"PDF only has {len(pdf.pages)} pages, requested page {page_number}")

        page = pdf.pages[page_number - 1]
        text_tables = [table.extract() for table in page.find_tables()]
        ocr_parsed_votes = parse_candidate_votes(page.extract_text() or "")
        text_parsed_votes = parse_table_votes(text_tables[0] if text_tables else [])
        page_content = {
            "page_number": page_number,
            "text": page.extract_text() or "",
            "text_tables": text_tables,
            "text_parsed_votes": text_parsed_votes,
            "text_formatted_results": format_table_results(text_parsed_votes),
            "ocr_parsed_votes": ocr_parsed_votes,
            "ocr_formatted_results": format_results(ocr_parsed_votes),
            "ocr_total_votes": sum(vote["votes"] for vote in ocr_parsed_votes),
            "vote_comparison": compare_vote_results(
                text_parsed_votes,
                ocr_parsed_votes
            )
        }
        result["pages"].append(page_content)

    # Extract images using pdf2image
    images = pdf2image.convert_from_path(pdf_path, first_page=page_number, last_page=page_number)
    for image in images:
        # Convert PIL Image to base64 and bytes
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr_val = img_byte_arr.getvalue()
        img_base64 = base64.b64encode(img_byte_arr_val).decode('utf-8')

        # Add image to the corresponding page
        result["pages"][0]["image"] = "img_base64"

        # Perform OCR
        if use_google_vision:
            # Use Google Vision API
            vision_client = vision.ImageAnnotatorClient()
            vision_image = vision.Image(content=img_byte_arr_val)

            document_response = vision_client.document_text_detection(image=vision_image)
            handwriting_response = vision_client.text_detection(image=vision_image)

            result["pages"][0]["ocr"] = {
                "provider": "google_vision",
                "document_text": document_response.full_text_annotation.text,
                "handwritten_text": handwriting_response.full_text_annotation.text,
                "confidence": document_response.full_text_annotation.pages[
                    0].confidence if document_response.full_text_annotation.pages else 0
            }
        else:
            # Use Tesseract OCR
            try:
                ocr_text = pytesseract.image_to_string(image)
                result["pages"][0]["ocr"] = {
                    "provider": "tesseract",
                    "text": ocr_text,
                }
            except Exception as e:
                result["pages"][0]["ocr"] = {
                    "provider": "tesseract",
                    "error": str(e)
                }

    return result


def save_to_json(pdf_path, output_path=None, use_google_vision=False, page_number=2):
    """
    Extract PDF content and save it to a JSON file.
    If output_path is not specified, uses the PDF filename with .json extension.
    """
    content = extract_pdf_content(pdf_path, use_google_vision=use_google_vision, page_number=page_number)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)

    return content


def cli():
    import argparse

    parser = argparse.ArgumentParser(description='Extract PDF content to JSON')
    parser.add_argument('--pdf_path', default="sample_data.pdf", help='Path to the PDF file')
    parser.add_argument('--output', '-o', help='Output JSON file path (optional)')
    parser.add_argument('--use-google-vision', action='store_true', help='Use Google Vision API for OCR')
    parser.add_argument('--page', type=int, default=2, help='Page number to extract (default: 2)')

    args = parser.parse_args()

    if args.use_google_vision:
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'google_credentials.json'

    output_file = save_to_json(
        args.pdf_path,
        args.output,
        use_google_vision=args.use_google_vision,
        page_number=args.page
    )
    print(f"PDF content extracted to: {output_file}")


def process_file(file_data, headers, processed_files):
    """Worker function to process a single file"""
    id, f = file_data
    if not f:
        print(f"File not found for {id}")
        return

    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    pdf_url = f"https://prezenta.roaep.ro/prezidentiale24112024/{f[0].get('url')}"
    
    # Generate a unique filename based on the URL
    pdf_file = pdf_url.split("/")[-1]
    os.makedirs("data/pdfs", exist_ok=True)
    saved_filename = f"data/pdfs/{pdf_file}"
    
    # Check if file was already processed
    if pdf_file in processed_files:
        print(f"Skipping already processed file: {id}")
        return
    
    print(f"Downloading {pdf_url}")
    
    # Download pdf file if it doesn't exist
    if not os.path.exists(saved_filename):
        pdf_file = requests.request("GET", pdf_url, headers=headers)
        with open(saved_filename, "wb") as f:
            f.write(pdf_file.content)
    
    print(f"Processing {saved_filename}")
    try:
        content = extract_pdf_content(saved_filename, use_google_vision=False, page_number=2)
        is_matching = content.get('pages')[0].get('vote_comparison').get('all_match')
        
        if not is_matching:
            print(f"The votes don't match for {id}")
            os.makedirs("data/problems", exist_ok=True)
            with open(f"data/problems/{id}.json", 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False)
        
        # Mark file as processed
        processed_files.add(pdf_file)
    except Exception as e:
        print(f"Error processing {id}: {str(e)}")

def parse_county(url, headers={}):
    # Load previously processed files if tracking file exists
    processed_files = set()
    for file in os.listdir("data/pdfs"):
        processed_files.add(file)

    print(f"Processing {url}")
    response = requests.request("GET", url, headers=headers)
    data = response.json()
    
    # Prepare the list of files to process
    files_to_process = []
    for id, files in data.get('scopes', {}).get('PRCNCT', {}).get('categories', {}).get('PRSD', {}).get('files', {}).items():
        f = [file for file in files if file.get('type') == 'A3SGND' and 
             file.get('scope_code') == 'PRCNCT' and 
             file.get('report_stage_code') == 'FINAL']
        files_to_process.append((id, f))
    
    # Process files using thread pool
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_file, file_data, headers, processed_files)
                  for file_data in files_to_process]
        
        # Wait for all tasks to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"An error occurred: {str(e)}")

def process_entire_country():
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,ro;q=0.7',
        'cache-control': 'no-cache',
        'cookie': 'route=d8c9549ecf4e236d36476adf0dd66c05; CONSENT=YES+; route=d8c9549ecf4e236d36476adf0dd66c05',
        'dnt': '1',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'sec-gpc': '1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    }

    url = f"https://prezenta.roaep.ro/prezidentiale24112024/data/json/sicpv/lists/counties.json?_={timestamp}"
    response = requests.request("GET", url, headers=headers)
    data = response.json()
    for county in data:
        county_url = f"https://prezenta.roaep.ro/prezidentiale24112024/data/json/sicpv/pv/pv_{county.get('code').lower()}.json?_={timestamp}"
        parse_county(county_url, headers)


if __name__ == '__main__':
    process_entire_country()
