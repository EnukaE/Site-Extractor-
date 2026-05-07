import requests
from bs4 import BeautifulSoup
import re
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def clean_name(name):
    # Remove titles
    name = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss\.|Dr\.|Rev\.|Ven\.|Eng\.)\s*', '', name, flags=re.IGNORECASE)

    # Common qualifications and junk to remove
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

    # Remove leading/trailing symbols
    name = re.sub(r'^[\. \- \*\+ \! \(\)]+', '', name)
    name = re.sub(r'[\. \- \*\+ \| \(\)]+$', '', name)

    # Remove extra spaces
    name = name.strip()

    if not name or len(name) < 3:
        return None
    return name

def normalize_phone(num):
    digits = re.sub(r'\D', '', num)
    if digits.startswith('94'):
        if len(digits) == 11:
            return digits
        elif len(digits) > 11:
            return digits[:11]
    elif digits.startswith('0'):
        if len(digits) == 10:
            return '94' + digits[1:]
    elif len(digits) == 9:
        return '94' + digits
    return None

def get_tutor_contacts(tid):
    url = f"https://www.mytutor.lk/ajx/load_contact.php?tid={tid}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        phones = []
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if 'tel:' in href or 'wa.me' in href:
                norm = normalize_phone(a.get_text())
                if norm:
                    phones.append(norm)
        text_phones = re.findall(r'(\d{10})', soup.get_text())
        for tp in text_phones:
             norm = normalize_phone(tp)
             if norm:
                 phones.append(norm)
        return list(set(phones))
    except:
        return []

def scrape_mytutor_page(page_num):
    print(f"Starting mytutor page {page_num}...")
    url = f"https://www.mytutor.lk/teachers_and_tuition_classes_in_sri_lanka.php?page={page_num}&ipp=20"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')

        listings = []
        tutor_links = soup.find_all('a', href=re.compile(r'more_details_tutor\.php\?tid='))

        processed_tids = set()

        for link in tutor_links:
            href = link.get('href')
            tid_match = re.search(r'tid=([^&]+)', href)
            if not tid_match: continue
            tid = tid_match.group(1)
            if tid in processed_tids: continue
            processed_tids.add(tid)

            detail_url = f"https://www.mytutor.lk/more_details_tutor.php?tid={tid}"
            try:
                det_resp = requests.get(detail_url, headers=headers, timeout=15)
                det_soup = BeautifulSoup(det_resp.text, 'html.parser')

                exp_tag = det_soup.find(string=re.compile("Experience :"))
                name = None
                if exp_tag:
                    parent = exp_tag.find_parent('div')
                    if parent:
                        text = parent.get_text()
                        name_match = re.search(r'^(.*?)\n', text.strip())
                        if name_match:
                            name = clean_name(name_match.group(1))

                if not name:
                    h2 = det_soup.find('h2')
                    if h2: name = clean_name(h2.get_text())

                if name:
                    phones = get_tutor_contacts(tid)
                    for p in phones:
                        listings.append({'Name': name, 'Phone Number': p})
            except:
                continue

        print(f"Finished mytutor page {page_num}. Found {len(listings)} records.")
        return listings
    except Exception as e:
        print(f"Error on mytutor page {page_num}: {e}")
        return []

def get_total_pages():
    try:
        url = "https://www.mytutor.lk/teachers_and_tuition_classes_in_sri_lanka.php"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()
        match = re.search(r'Page: 1 of (\d+)', text)
        if match:
            return int(match.group(1))
    except:
        pass
    return 1

if __name__ == "__main__":
    total_pages = get_total_pages()
    print(f"Total pages to scrape: {total_pages}", flush=True)

    phone_to_name = {}

    try:
        with open('teachers.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                phone_to_name[row['Phone Number']] = row['Name']
        print(f"Loaded {len(phone_to_name)} existing records.", flush=True)
    except FileNotFoundError:
        print("No existing teachers.csv found.", flush=True)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(scrape_mytutor_page, p) for p in range(1, total_pages + 1)]

        completed = 0
        for future in as_completed(futures):
            try:
                page_data = future.result()
                for item in page_data:
                    phone = item['Phone Number']
                    name = item['Name']
                    if phone in phone_to_name:
                        if len(name) > len(phone_to_name[phone]):
                            phone_to_name[phone] = name
                    else:
                        phone_to_name[phone] = name
                completed += 1
                print(f"Mytutor Progress: {completed}/{total_pages} pages scraped... ({len(phone_to_name)} total unique phones)", flush=True)
            except Exception as e:
                print(f"Page failed: {e}", flush=True)

    final_list = [{'Name': n, 'Phone Number': p} for p, n in phone_to_name.items()]
    final_list.sort(key=lambda x: (x['Name'], x['Phone Number']))

    with open('teachers.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Phone Number'])
        writer.writeheader()
        writer.writerows(final_list)

    print(f"Mytutor scraping complete. Total unique records: {len(final_list)}", flush=True)
