import requests
import re
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def clean_name(name):
    name = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss\.|Dr\.|Rev\.|Ven\.|Eng\.)\s*', '', name, flags=re.IGNORECASE)
    qualifications = [
        r'BSc', r'MSc', r'PhD', r'BBA', r'MBA', r'MBBS', r'Eng', r'B\.Sc', r'M\.Sc',
        r'Graduated', r'Graduate', r'University', r'Lecturer', r'Teacher',
        r'ACCA', r'CIMA', r'AAT', r'CA', r'B\.E', r'M\.E', r'B\.Tech', r'M\.Tech',
        r'Experience', r'Conducted by', r'qualified', r'international school',
        r'Chartered', r'Mathematician', r'years Experienced', r'Government School',
        r'University of', r'B.A', r'B.Com', r'B\.A', r'B\.Com', r'M\.A', r'M\.Com',
        r'leading school', r'institute', r'B\.Ed', r'M\.Ed', r'Reading for', r'Reading',
        r'Attorney-at-Law', r'AMIE', r'C\.Eng'
    ]
    for qual in qualifications:
        name = re.sub(r'\b' + qual + r'\b.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^[\. \- \*\+ \! \(\)]+', '', name)
    name = re.sub(r'[\. \- \*\+ \| \(\)]+$', '', name)
    name = name.strip()
    if not name or len(name) < 3: return None
    if any(inst in name.lower() for inst in ['academy', 'institute', 'college', 'school', 'center', 'centre']):
        return None
    return name

def normalize_phone(num):
    digits = re.sub(r'\D', '', num)
    if digits.startswith('94'):
        if len(digits) == 11: return digits
        elif len(digits) > 11: return digits[:11]
    elif digits.startswith('0'):
        if len(digits) == 10: return '94' + digits[1:]
    elif len(digits) == 9:
        return '94' + digits
    return None

def scrape_studyway_page(page_num):
    print(f"Starting studyway page {page_num}...")
    url = f"https://www.studyway.lk/tuition?page={page_num}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=20)

        # New pattern found: name:"Name",email:"...",phone:"Number"
        matches = re.findall(r'name:"([^"]*)",email:"[^"]*",phone:"([^"]*)"', response.text)

        results = []
        for name_raw, phone_raw in matches:
            name = clean_name(name_raw)
            phone = normalize_phone(phone_raw)
            if name and phone:
                results.append({'Name': name, 'Phone Number': phone})

        # Also include the tutors in the detail pages if needed,
        # but the main page seems to have many already.
        # Let's try to get more from slugs just in case the list is incomplete.
        slugs = re.findall(r'href="/tuition/([a-z0-9-]+)"', response.text)

        print(f"Finished studyway page {page_num}. Found {len(results)} records from state.")
        return results, slugs
    except Exception as e:
        print(f"Error on studyway page {page_num}: {e}")
        return [], []

def get_studyway_tutor(slug):
    url = f"https://www.studyway.lk/tuition/{slug}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        name_match = re.search(r'i\.name="([^"]+)"', response.text)
        phone_match = re.search(r'i\.phone="([^"]+)"', response.text)
        if name_match and phone_match:
            name = clean_name(name_match.group(1))
            phone = normalize_phone(phone_match.group(2))
            if name and phone:
                return [{'Name': name, 'Phone Number': phone}]
    except: pass
    return []

if __name__ == "__main__":
    phone_to_name = {}
    try:
        with open('teachers.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                phone_to_name[row['Phone Number']] = row['Name']
        print(f"Loaded {len(phone_to_name)} existing records.")
    except FileNotFoundError: pass

    all_slugs = set()
    print("Scraping Studyway pages...")
    for p in range(1, 26):
        data, slugs = scrape_studyway_page(p)
        for item in data:
            phone = item['Phone Number']
            name = item['Name']
            if phone in phone_to_name:
                if len(name) > len(phone_to_name[phone]): phone_to_name[phone] = name
            else: phone_to_name[phone] = name
        for s in slugs:
            if s not in ['register']: all_slugs.add(s)

    print(f"Found {len(all_slugs)} tutor slugs. Scraping details for missing ones...")
    # Only scrape slugs that we haven't found phones for yet if possible,
    # but we don't know which slug corresponds to which phone yet.
    # To be safe and thorough, scrape all slugs.

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(get_studyway_tutor, s) for s in all_slugs]
        completed = 0
        for future in as_completed(futures):
            try:
                data = future.result()
                for item in data:
                    phone = item['Phone Number']
                    name = item['Name']
                    if phone in phone_to_name:
                        if len(name) > len(phone_to_name[phone]): phone_to_name[phone] = name
                    else: phone_to_name[phone] = name
                completed += 1
                if completed % 50 == 0:
                    print(f"Progress: {completed}/{len(all_slugs)} tutors checked... ({len(phone_to_name)} total unique phones)", flush=True)
            except: pass

    final_list = [{'Name': n, 'Phone Number': p} for p, n in phone_to_name.items()]
    final_list.sort(key=lambda x: (x['Name'], x['Phone Number']))
    with open('teachers.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Phone Number'])
        writer.writeheader()
        writer.writerows(final_list)
    print(f"Studyway scraping complete. Total unique records: {len(final_list)}")
