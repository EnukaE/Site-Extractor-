import pandas as pd
import os
import re

CSV_FILE = 'teachers.csv'

def normalize_phone(phone_str):
    if not phone_str or pd.isna(phone_str): return None
    digits = re.sub(r'\D', '', str(phone_str))
    if not digits: return None
    if digits.startswith('94') and len(digits) == 11:
        return digits
    elif digits.startswith('0') and len(digits) == 10:
        return '94' + digits[1:]
    elif len(digits) == 9:
        return '94' + digits
    return None

def clean_name(name):
    if not name or pd.isna(name): return ""
    name = str(name)

    # Remove emojis and non-BMP characters
    name = re.sub(r'[^\u0000-\uFFFF]', '', name)

    # Split by common delimiters and take the first part if it looks like a name
    # Teachers often put qualifications after a comma or dash
    parts = re.split(r'[,|\-\(]', name)
    if len(parts) > 1:
        # If the first part is very short (like "Dr."), keep more
        if len(parts[0].strip()) < 5:
            name = parts[0] + " " + parts[1]
        else:
            name = parts[0]

    # Remove anything in brackets
    name = re.sub(r'\[.*?\]', '', name)

    # Remove specific academic and professional titles/qualifications
    titles = [
        r'Mr\.', r'Mrs\.', r'Ms\.', r'Miss\.', r'Dr\.', r'Prof\.', r'Rev\.', r'Eng\.', r'Lecturer',
        r'BSc', r'MSc', r'PhD', r'MBBS', r'B\.Sc', r'M\.Sc', r'BA', r'MA', r'BEd', r'MEd',
        r'Undergraduate', r'Graduate', r'Teacher', r'Tutor', r'Smt\.', r'Vishwa', r'Vibhashana',
        r'Keerthi', r'Shree', r'Bachelor\'s degree', r'Master\'s degree', r'Diploma', r'Qualified',
        r'CIMA', r'ACCA', r'AAT', r'Visiting', r'Instructor', r'Sir', r'Madam', r'Lady', r'Female', r'Male',
        r'HNDE', r'NDTT', r'PGDE', r'BEng', r'NDT-IT', r'LVCM', r'PGEDM', r'M\.Phil',
        r'Kala', r'Vibhushana', r'Vithya', r'Shoori', r'Kalasuri'
    ]

    for title in titles:
        name = re.sub(r'\b' + title + r'\b', '', name, flags=re.IGNORECASE)

    # Keywords that suggest it's NOT a person's name
    non_person_keywords = [
        'institute', 'academy', 'school', 'college', 'center', 'centre',
        'education', 'group', 'classes', 'learning', 'tuition', 'university',
        'years of experienced', 'years well experienced', 'experienced',
        'specialist', 'specialised', 'expert', 'medium', 'syllabus', 'grade',
        'subject', 'test', 'email', 'lesson', 'paper', 'service', 'training', 'professional',
        'at paypal', 'university of', 'senior engineer', 'medical student', 'final year student',
        'author', 'government', 'national player', 'instructure', 'proffesional', 'engineer',
        'friendly young', 'former', 'student', 'masters student', 'reputed', 'registered',
        'retired', 'science faculty', 'secretary', 'well educated', 'well known', 'doctor',
        'trained', 'faculty', 'qualified', 'campus', 'educational', 'foundation'
    ]

    lower_name = name.lower()
    if any(word in lower_name for word in non_person_keywords):
        return ""

    # Suspicious symbols
    if re.search(r'[<>@/:#?!=*|•📅📍📌]', name):
        return ""

    # Clean up whitespace and punctuation
    name = re.sub(r'\s+', ' ', name).strip()
    # Strip non-word characters from start/end (except for foreign characters handled by regex)
    name = re.sub(r'^[^a-zA-Z\u0D80-\u0DFF\u0B80-\u0BFF]+', '', name)
    name = re.sub(r'[^a-zA-Z\u0D80-\u0DFF\u0B80-\u0BFF]+$', '', name)

    # Remove names that have too many digits
    if len(re.sub(r'\D', '', name)) > 2:
        return ""

    # If name starts with "A " and is very short, it's likely a descriptor like "A Lady"
    if name.startswith("A ") and len(name) < 10:
        # Check if the second part is a common name or a descriptor
        second_word = name.split(" ")[1].lower()
        if second_word in ['well', 'young', 'primary', 'miss', 'lady', 'female', 'male', 'former', 'reputed']:
            return ""

    # If name is too short or too long, it might be garbage
    if len(name) < 3 or len(name) > 40:
        return ""

    # Check if name contains at least one alphabetic character (either English or Sinhala/Tamil)
    if not re.search(r'[a-zA-Z\u0D80-\u0DFF\u0B80-\u0BFF]', name):
        return ""

    return name

def main():
    if not os.path.exists(CSV_FILE):
        print("CSV not found.")
        return

    df = pd.read_csv(CSV_FILE)

    # Ensure columns
    if 'Name' not in df.columns:
        if 'name' in df.columns: df['Name'] = df['name']
    if 'Phone Number' not in df.columns:
        if 'phone' in df.columns: df['Phone Number'] = df['phone']

    df = df[['Name', 'Phone Number']].copy()

    print(f"Initial count: {len(df)}")

    # 1. Normalize and clean phones
    df['Phone Number'] = df['Phone Number'].apply(normalize_phone)
    df = df.dropna(subset=['Phone Number'])

    # 2. Clean names
    df['Name'] = df['Name'].apply(clean_name)
    df = df[df['Name'] != ""]

    # 3. Deduplicate: keep longest name for each phone
    df['name_len'] = df['Name'].str.len()
    df = df.sort_values(['Phone Number', 'name_len'], ascending=[True, False])
    df = df.drop_duplicates(subset=['Phone Number'], keep='first')
    df = df.drop(columns=['name_len'])

    # Final sort
    df = df.sort_values('Name')

    df.to_csv(CSV_FILE, index=False)
    print(f"Final count: {len(df)}")

if __name__ == "__main__":
    main()
