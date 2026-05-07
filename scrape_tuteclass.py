import requests
import csv
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

CSV_FILE = 'teachers.csv'

def normalize_phone(phone_str):
    if not phone_str: return []
    digits = re.sub(r'\D', '', str(phone_str))
    if not digits: return []
    if digits.startswith('94') and len(digits) == 11: return [digits]
    elif digits.startswith('0') and len(digits) == 10: return ['94' + digits[1:]]
    elif len(digits) == 9: return ['94' + digits]
    return []

def clean_name(name):
    if not name: return ""
    titles = [r'Mr\.', r'Mrs\.', r'Ms\.', r'Miss\.', r'Dr\.', r'Prof\.', r'Rev\.', r'Eng\.', r'Lecturer', r'BSc', r'MSc', r'PhD']
    name = re.sub(r'\(.*?\)', '', name)
    for title in titles: name = re.sub(r'\b' + title + r'\b', '', name, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', name).strip().strip(',.- ')

def fetch_ad_details(ad_id):
    url = f"https://tuteclass.com/api/tuitions/tuition-ad?tuitionAdId={ad_id}&languageCode=ENG"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            name = data.get("teacherName")
            wa = data.get("whatsappNo")
            if name and wa:
                return name, wa
    except:
        pass
    return None, None

def main():
    search_url = "https://tuteclass.com/api/tuitions/ad-search-results?PageNo=1&RecordsPerPage=2000&GradeCategoryId=-1&GradeId=-1&SubjectId=-1&MediumId=-1&ClassTypeId=-1&DistrictId=-1&TownId=-1&IncludeOnline=true&LanguageCode=ENG"

    print("Fetching Tuteclass ad list...")
    try:
        r = requests.get(search_url)
        search_results = r.json()
    except Exception as e:
        print(f"Error fetching search results: {e}")
        return

    ad_ids = [item.get("tuitionAdId") for item in search_results if item.get("tuitionAdId")]
    print(f"Found {len(ad_ids)} ads on Tuteclass.")

    phone_to_name = {}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                p, n = row.get('Phone Number'), row.get('Name')
                if p and n: phone_to_name[p] = n

    print(f"Initial records: {len(phone_to_name)}")

    new_found = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_ad_details, ad_id): ad_id for ad_id in ad_ids}

        for future in as_completed(futures):
            name, wa = future.result()
            if name and wa:
                phones = normalize_phone(wa)
                for ph in phones:
                    c_name = clean_name(name)
                    if ph in phone_to_name:
                        if len(c_name) > len(phone_to_name[ph]):
                            phone_to_name[ph] = c_name
                    else:
                        phone_to_name[ph] = c_name
                        new_found += 1

    print(f"Tuteclass scraping complete. New unique phones added: {new_found}")

    final_list = [{'Name': n, 'Phone Number': p} for p, n in phone_to_name.items()]
    final_list.sort(key=lambda x: x['Name'])

    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Phone Number'])
        writer.writeheader()
        writer.writerows(final_list)
    print(f"Total unique records now: {len(phone_to_name)}")

if __name__ == "__main__":
    main()
