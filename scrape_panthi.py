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
    found = re.findall(r'(\+?94[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|0\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|0\d{9}|94\d{9})', text)

    normalized = []
    for num in found:
        digits = re.sub(r'\D', '', num)

        if digits.startswith('94'):
            if len(digits) == 11:
                normalized.append(digits)
            elif len(digits) > 11:
                normalized.append(digits[:11])
        elif digits.startswith('0'):
            if len(digits) == 10:
                normalized.append('94' + digits[1:])
        elif len(digits) == 9:
            normalized.append('94' + digits)

    return list(set(normalized))

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
            for phone in set(phones):
                listings.append({
                    'Name': cleaned_name,
                    'Phone Number': phone
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
    print(f"Total pages to scrape: {total_pages}")

    all_data_map = {} # Phone Number -> Name

    with ThreadPoolExecutor(max_workers=10) as executor:
        pages_to_scrape = range(1, total_pages + 1)
        future_to_page = {executor.submit(scrape_page, p): p for p in pages_to_scrape}

        completed = 0
        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                page_data = future.result()
                for item in page_data:
                    phone = item['Phone Number']
                    name = item['Name']

                    # Heuristic: if phone exists, keep the longer name (likely more complete)
                    if phone in all_data_map:
                        if len(name) > len(all_data_map[phone]):
                            all_data_map[phone] = name
                    else:
                        all_data_map[phone] = name

                completed += 1
                if completed % 50 == 0:
                    print(f"Progress: {completed}/{total_pages} pages scraped... ({len(all_data_map)} unique phone numbers)")
            except Exception as exc:
                print(f"Page {page_num} generated an exception: {exc}")

    # Convert map to list of dicts for sorting and writing
    final_data = [{'Name': name, 'Phone Number': phone} for phone, name in all_data_map.items()]
    final_data.sort(key=lambda x: (x['Name'], x['Phone Number']))

    with open('teachers.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Phone Number'])
        writer.writeheader()
        writer.writerows(final_data)

    print(f"Scraping complete. Total unique records: {len(final_data)}")
