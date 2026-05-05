import requests
from bs4 import BeautifulSoup
import re
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def clean_name(name):
    # Remove "Conducted By :" prefix if present
    name = re.sub(r'Conducted By\s*:\s*', '', name, flags=re.IGNORECASE)

    # Remove text in parentheses
    name = re.sub(r'\(.*?\)', '', name)

    # Common qualifications and junk to remove
    qualifications = [
        r'BSc', r'MSc', r'PhD', r'BBA', r'MBA', r'MBBS', r'Eng', r'B\.Sc', r'M\.Sc',
        r'Graduated', r'Graduate', r'University', r'Lecturer', r'Teacher',
        r'ACCA', r'CIMA', r'AAT', r'CA', r'B\.E', r'M\.E', r'B\.Tech', r'M\.Tech',
        r'Experience', r'Conducted by', r'qualified', r'international school',
        r'Chartered', r'Mathematician', r'years Experienced', r'Government School',
        r'University of', r'B.A', r'B.Com', r'B\.A', r'B\.Com', r'M\.A', r'M\.Com',
        r'leading school', r'institute', r'B\.Ed', r'M\.Ed', r'Reading for', r'Reading'
    ]
    for qual in qualifications:
        name = re.sub(r'\b' + qual + r'\b.*', '', name, flags=re.IGNORECASE)

    # Remove leading/trailing symbols commonly found in these listings
    name = re.sub(r'^[\. \- \*\+]+', '', name)
    name = re.sub(r'[\. \- \*\+ \|]+$', '', name)

    # Remove extra spaces and trailing punctuation
    name = name.strip().rstrip(',- :|.')

    # If the name is too generic or empty, return None
    if not name or len(name) < 3:
        return None

    # Filter out common junk phrases
    junk_phrases = ['experience', 'teacher', 'lecturer', 'experienced', 'conducting', 'visit', 'online', 'classes']
    if any(jp in name.lower() for jp in junk_phrases) and len(name.split()) < 3:
        return None

    return name

def get_phone_numbers(text):
    # Match various phone number formats
    # Sri Lankan numbers often start with 0 or +94 or 94
    # Improved regex to handle spaces and dashes more robustly
    found = re.findall(r'(\+?94[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|0\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|0\d{9}|94\d{9})', text)

    cleaned = []
    for num in found:
        c = re.sub(r'[\s\+\-]', '', num)
        # Standardize: we'll keep it as found but deduplicate based on digits
        # Actually, let's keep the original format for better readability but deduplicate
        if len(c) >= 9:
            cleaned.append(num.strip())

    # Deduplicate based on digits
    unique_nums = {}
    for n in cleaned:
        digits = re.sub(r'\D', '', n)
        if digits.startswith('94'):
             digits = '0' + digits[2:] # normalize 94... to 0...
        if digits not in unique_nums:
            unique_nums[digits] = n

    return list(unique_nums.values())

def scrape_page(page_num):
    url = f"https://panthi.lk/?page={page_num}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception:
        try:
            time.sleep(2)
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except:
            return []

    soup = BeautifulSoup(response.text, 'html.parser')
    listings = []

    conducted_by_tags = soup.find_all(string=re.compile("Conducted By"))

    for tag in conducted_by_tags:
        parent_div = tag.find_parent('div')
        if not parent_div:
            continue

        name_text = parent_div.get_text().strip()
        cleaned_name = clean_name(name_text)

        phones = []
        phones.extend(get_phone_numbers(parent_div.get_text()))

        next_sibling = parent_div.find_next_sibling('div')
        while next_sibling:
            txt = next_sibling.get_text().strip()
            if any(k in txt for k in ["Conducted By", "Published On"]):
                 break
            phones.extend(get_phone_numbers(txt))
            next_sibling = next_sibling.find_next_sibling('div')

        description_div = parent_div.find_previous_sibling('div', id='new')
        if description_div:
            phones.extend(get_phone_numbers(description_div.get_text()))

        if cleaned_name and phones:
            listings.append({
                'Name': cleaned_name,
                'Phone Numbers': "; ".join(sorted(list(set(phones))))
            })

    return listings

def get_total_pages():
    try:
        response = requests.get("https://panthi.lk/", timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        last_link = soup.find('a', string='Last')
        if last_link and 'page=' in last_link.get('href'):
            return int(last_link.get('href').split('page=')[1])
    except:
        pass
    return 1

if __name__ == "__main__":
    total_pages = get_total_pages()
    # For demonstration/safety, I'll limit to 50 pages for now OR I can just run all if I have time.
    # The instructions say "From the entire website".
    # I will run for 100 pages to show progress and then decide.
    # Actually, I'll try to run for ALL but I'll add a way to stop if it takes too long.

    print(f"Total pages to scrape: {total_pages}")

    all_data = []
    seen = set()

    # Using 10 workers for faster extraction
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Start with a subset to ensure everything is fine
        pages_to_scrape = range(1, total_pages + 1)
        future_to_page = {executor.submit(scrape_page, p): p for p in pages_to_scrape}

        completed = 0
        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                page_data = future.result()
                for item in page_data:
                    # Deduplicate based on Name + Phones
                    identifier = (item['Name'], item['Phone Numbers'])
                    if identifier not in seen:
                        all_data.append(item)
                        seen.add(identifier)

                completed += 1
                if completed % 50 == 0:
                    print(f"Progress: {completed}/{total_pages} pages scraped... ({len(all_data)} unique records)")
            except Exception as exc:
                print(f"Page {page_num} generated an exception: {exc}")

    # Final sort
    all_data.sort(key=lambda x: x['Name'])

    with open('teachers.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Phone Numbers'])
        writer.writeheader()
        writer.writerows(all_data)

    print(f"Scraping complete. Total unique records: {len(all_data)}")
