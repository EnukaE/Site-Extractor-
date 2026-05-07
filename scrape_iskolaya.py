import requests
from bs4 import BeautifulSoup
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
    elif len(digits) == 9: return '94' + digits
    return None

def scrape_iskolaya_class(cid):
    url = f"https://iskolaya.lk/class/{cid}/"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        conducted_span = soup.find('span', string=re.compile("Conducted By:"))
        name = None
        if conducted_span:
            name_tag = conducted_span.find_next('span', class_='label-colour-4')
            if name_tag: name = clean_name(name_tag.get_text())
        if not name: return []
        phones = []
        contact_label = soup.find('td', string=re.compile("Contact:"))
        if contact_label:
            contact_val = contact_label.find_next_sibling('td')
            if contact_val:
                text = contact_val.get_text()
                raw_nums = re.split(r'[,/;\s]+', text)
                for rn in raw_nums:
                    norm = normalize_phone(rn)
                    if norm: phones.append(norm)
        desc = soup.find('p', class_='text-wrap')
        if desc:
            text = desc.get_text()
            matches = re.findall(r'(\d{3}\s?\d\s?\d{3}\s?\d{3}|0\d{9}|94\d{9})', text)
            for m in matches:
                norm = normalize_phone(m)
                if norm: phones.append(norm)
        return [{'Name': name, 'Phone Number': p} for p in set(phones)]
    except: return []

def get_max_cid():
    try:
        url = "https://iskolaya.lk/"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        cids = re.findall(r'/class/(\d+)/', response.text)
        if cids: return max(map(int, cids))
    except: pass
    return 22000

if __name__ == "__main__":
    phone_to_name = {}
    try:
        with open('teachers.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                phone_to_name[row['Phone Number']] = row['Name']
        print(f"Loaded {len(phone_to_name)} existing records.")
    except FileNotFoundError: pass

    max_cid = get_max_cid()
    start_cid = max(1, max_cid - 5000)
    print(f"Scraping iskolaya.lk from CID {start_cid} to {max_cid}...")

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(scrape_iskolaya_class, cid) for cid in range(start_cid, max_cid + 1)]
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
                if completed % 500 == 0:
                    print(f"Progress: {completed}/5000 CIDs checked... ({len(phone_to_name)} total unique phones)", flush=True)
            except: pass

    final_list = [{'Name': n, 'Phone Number': p} for p, n in phone_to_name.items()]
    final_list.sort(key=lambda x: (x['Name'], x['Phone Number']))
    with open('teachers.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Phone Number'])
        writer.writeheader()
        writer.writerows(final_list)
    print(f"Iskolaya scraping complete. Total unique records: {len(final_list)}")
