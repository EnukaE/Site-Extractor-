import requests
from bs4 import BeautifulSoup
import re
import csv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

# Config
BASE_URL = "https://www.fat.lk/"
CATEGORIES_URL = "https://www.fat.lk/en/tuition-class/"
CSV_FILE = 'teachers.csv'
MAX_THREADS = 5

def normalize_phone(phone_str):
    if not phone_str:
        return []
    phone_str = phone_str.replace('\u200b', '').replace('\ufeff', '')
    digits = re.sub(r'\D', '', phone_str)
    if not digits:
        return []
    if digits.startswith('94') and len(digits) == 11:
        return [digits]
    elif digits.startswith('0') and len(digits) == 10:
        return ['94' + digits[1:]]
    elif len(digits) == 9:
        return ['94' + digits]
    return []

def clean_name(name):
    if not name:
        return ""
    titles = [
        r'Mr\.', r'Mrs\.', r'Ms\.', r'Miss\.', r'Dr\.', r'Prof\.', r'Rev\.', r'Eng\.', r'Lecturer',
        r'BSc', r'MSc', r'PhD', r'MBBS', r'BA', r'MA', r'BEd', r'MEd', r'CIMA', r'ACCA', r'AAT'
    ]
    name = re.sub(r'\(.*?\)', '', name)
    for title in titles:
        name = re.sub(r'\b' + title + r'\b', '', name, flags=re.IGNORECASE)

    name = re.sub(r'\s+', ' ', name).strip()
    return name.strip(',.- ')

def get_categories():
    print("Fetching categories...")
    try:
        response = requests.get(CATEGORIES_URL, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=re.compile(r'/en/tuition-class/'))
        cat_links = set()
        for link in links:
            href = link.get('href')
            if href:
                full_url = urljoin(BASE_URL, href)
                if '/en/tuition-class/' in full_url:
                    base_cat = full_url.split('?')[0].rstrip('/')
                    cat_links.add(base_cat)
        return list(cat_links)
    except Exception as e:
        print(f"Error fetching categories: {e}")
        return []

def extract_ad_links(cat_url):
    ad_links = set()
    page = 1
    while True:
        url = f"{cat_url}/?p={page}"
        try:
            response = requests.get(url, timeout=20)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')
            forms = soup.find_all('form', action=re.compile(r'/en/ad/'))
            if not forms:
                break

            count_before = len(ad_links)
            for form in forms:
                ad_links.add(form['action'])

            if len(ad_links) == count_before:
                break

            if not soup.find('a', title='Next') and not soup.find('a', string=re.compile('Show more Ads', re.I)):
                break

            page += 1
            if page > 100:
                break
        except:
            break
    return ad_links

def scrape_ad(ad_url):
    try:
        response = requests.get(ad_url, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')

        name = ""
        name_elem = soup.find('b', string=re.compile('Tutor :', re.I))
        if name_elem:
            parent = name_elem.find_parent('div')
            if parent:
                next_div = parent.find_next_sibling('div')
                if next_div:
                    name = next_div.get_text(separator=' ').strip()

        if not name:
            review_sec = soup.find('div', id='reviews')
            if review_sec:
                rev_body = review_sec.find('div', class_='card-body')
                if rev_body:
                    rev_text = rev_body.get_text()
                    match = re.search(r'about\s+([^<]+)', rev_text, re.I)
                    if match:
                        name = match.group(1).strip()

        phone_numbers = []
        phone_elem = soup.find('b', string=re.compile('Phone :', re.I))
        if phone_elem:
            parent = phone_elem.find_parent('div')
            if parent:
                next_div = parent.find_next_sibling('div')
                if next_div:
                    phone_numbers.extend(normalize_phone(next_div.get_text()))

        wa_links = soup.find_all('a', href=re.compile(r'api\.whatsapp\.com/send\?phone='))
        for link in wa_links:
            match = re.search(r'phone=(\d+)', link['href'])
            if match:
                phone_numbers.extend(normalize_phone(match.group(1)))

        about_body = soup.find('div', class_='card-body lower4')
        if about_body:
            text = about_body.get_text()
            matches = re.findall(r'0\d{9}', text)
            for m in matches:
                phone_numbers.extend(normalize_phone(m))

        phone_numbers = list(set(phone_numbers))

        if name and phone_numbers:
            cleaned_name = clean_name(name)
            if cleaned_name:
                return [{'Name': cleaned_name, 'Phone Number': p} for p in phone_numbers]
    except:
        pass
    return []

def main():
    phone_to_name = {}
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    phone_to_name[row['Phone Number']] = row['Name']
            print(f"Loaded {len(phone_to_name)} existing records.")
        except:
            pass

    categories = get_categories()
    all_ad_links = set()

    print(f"Found {len(categories)} categories. Collecting ad links...")
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(extract_ad_links, cat): cat for cat in categories}
        for future in as_completed(futures):
            all_ad_links.update(future.result())

    print(f"Found {len(all_ad_links)} unique ads. Scraping...")
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(scrape_ad, url): url for url in all_ad_links}
        for future in as_completed(futures):
            res = future.result()
            if res:
                for item in res:
                    p, n = item['Phone Number'], item['Name']
                    if p in phone_to_name:
                        if len(n) > len(phone_to_name[p]):
                            phone_to_name[p] = n
                    else:
                        phone_to_name[p] = n

    final_list = [{'Name': n, 'Phone Number': p} for p, n in phone_to_name.items()]
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Phone Number'])
        writer.writeheader()
        writer.writerows(final_list)
    print(f"Fat.lk scraping complete. Total records: {len(final_list)}")

if __name__ == "__main__":
    main()
