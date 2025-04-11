import cv2
import pytesseract
import numpy as np
import spacy
import pandas as pd
import pdfplumber
from PIL import Image
from IPython.display import display, Markdown
import ipywidgets as widgets
import io
from ipyfilechooser import FileChooser
import re
import mysql.connector
from datetime import datetime
import pytesseract
import cv2
import pdfplumber
import re
import numpy as np
from pymongo import MongoClient
from IPython.display import display
from ipywidgets import FileUpload
nlp = spacy.load("en_core_web_sm")

# Output widget for displaying extracted text and information
output_widget = widgets.Output()

# MySQL database connection details
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "ankit2061",
    "database": "ClaimDetails",
}

def preprocess_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        with output_widget:
            print("Error: Could not read the image. Please check the file format and path.")
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    kernel = np.ones((1, 1), np.uint8)
    processed_image = cv2.dilate(binary, kernel, iterations=1)
    processed_image = cv2.erode(processed_image, kernel, iterations=1)

    return processed_image

def extract_text_from_image(image_path):
    preprocessed_image = preprocess_image(image_path)
    if preprocessed_image is None:
        return ""

    pil_image = Image.fromarray(preprocessed_image)
    try:
        text = pytesseract.image_to_string(pil_image)
    except pytesseract.TesseractError as e:
        with output_widget:
            output_widget.clear_output()
            print(f"Tesseract Error: {e}")
        return ""
    return text.strip()

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        with output_widget:
            output_widget.clear_output()
            print(f"Error reading PDF: {e}")
        return ""
    return text.strip()

def extract_aadhaar_number(text):
    """
    Specialized function to extract Aadhaar numbers using multiple approaches
    """
    # Clean the text first - this can help with OCR errors
    cleaned_text = re.sub(r'\s+', ' ', text)
    
    # Method 1: Look for common Aadhaar number patterns (12 digits with or without separators)
    # This catches raw numbers that look like Aadhaar numbers
    aadhaar_patterns = [
        # Pattern with no separators - 12 consecutive digits
        r'(?<!\d)(\d{12})(?!\d)',
        # Pattern with space separators
        r'(\d{4}\s+\d{4}\s+\d{4})',
        # Pattern with dash separators
        r'(\d{4}-\d{4}-\d{4})',
        # Pattern with dot separators
        r'(\d{4}\.\d{4}\.\d{4})'
    ]
    
    for pattern in aadhaar_patterns:
        matches = re.findall(pattern, cleaned_text)
        if matches:
            # Clean up the found number (remove spaces, dashes)
            aadhaar = re.sub(r'[^\d]', '', matches[0])
            if len(aadhaar) == 12:
                return aadhaar
    
    # Method 2: Look for Aadhaar numbers with keywords
    # This catches Aadhaar numbers that are labeled
    keyword_patterns = [
        # Various ways "Aadhaar" might be written followed by a number
        r'(?:aadhar|aadhaar|adhar|aadha+r|आधार)(?:\s*(?:card|number|no|id|#|:|नंबर|संख्या))?\s*[:\.\-]?\s*((?:\d[\d\s\.\-]*){12})',
        r'(?:uid|unique\s+id)(?:\s*(?:number|no|#))?\s*[:\.\-]?\s*((?:\d[\d\s\.\-]*){12})',
        # Looking for "No:" or "Number:" followed by what could be an Aadhaar
        r'(?:no|number|id)?\s*[:\.\-]\s*((?:\d[\d\s\.\-]*){12})'
    ]
    
    for pattern in keyword_patterns:
        matches = re.findall(pattern, cleaned_text.lower())
        if matches:
            # Clean up the found number
            aadhaar = re.sub(r'[^\d]', '', matches[0])
            if len(aadhaar) == 12:
                return aadhaar
    
    # Method 3: More aggressive - find any 12-digit sequence that could be an Aadhaar number
    # Use with caution as it might pick up other 12-digit numbers
    digit_sequences = re.findall(r'(?<!\d)(\d[\d\s\.\-]*\d)(?!\d)', cleaned_text)
    for seq in digit_sequences:
        digits_only = re.sub(r'[^\d]', '', seq)
        if len(digits_only) == 12:
            return digits_only
            
    return None

def clean_extracted_field(text, field_type):
    """
    Cleans extracted text based on field type to remove common OCR artifacts
    and mislabeled content
    """
    # Convert to string in case we received another type
    text = str(text).strip()
    
    # Remove common label text that might be captured within the value
    unwanted_labels = [
        "Phone Number", "Contact", "Mobile", "Call",
        "Hospital Name", "Doctor", "Clinic", "MD", "Dr\\.",
        "Address", "Location", "Place", "Residence",
        "Insurance ID", "Policy Number", "Insurance",
        "Amount", "Total", "Fee", "Payment",
        "Disease", "Diagnosis", "Condition",
        "Medicines", "Medication", "Drugs", "Prescription"
    ]
    
    # For each unwanted label, try to remove it if it appears at the end
    for label in unwanted_labels:
        # Create pattern to match label at the end of the text (allowing for spaces)
        pattern = rf'\s*{re.escape(label)}$'
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Remove common field separators
    text = re.sub(r'[:;|]$', '', text)
    
    # Clean up newlines and extra spaces
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    
    # Additional field-specific cleaning
    if field_type in ["Address"]:
        # Keep only relevant address information
        text = re.sub(r'\s*(?:Phone|Mobile|Contact|Email).*$', '', text, flags=re.IGNORECASE)
    
    elif field_type in ["Hospital Name"]:
        # Remove doctor references
        text = re.sub(r'\s*(?:Doctor|Dr\.|MD|Physician).*$', '', text, flags=re.IGNORECASE)
    
    elif field_type in ["Phone Number"]:
        # Keep only digits and basic formatting characters
        text = re.sub(r'[^\d+\-\s()]', '', text)
    
    return text.strip()

def extract_fields_with_boundaries(text):
    """
    Extract fields with improved boundary detection to prevent label bleed
    """
    extracted_info = []
    found_labels = set()
    
    # Dictionary of field patterns with better boundary detection
    field_patterns = {
        "Name": r'(?:Patient(?:\s*Name)?|Name|Patient)[:;]?\s*([\w\s\.]+?)(?=\n|$|(?:Father|Gender|Blood|Aadhaar))',
        "Father's Name": r'(?:Father(?:[\'s]*\s*Name)?|Father)[:;]?\s*([\w\s\.]+?)(?=\n|$|(?:Gender|Blood|Aadhaar))',
        "Gender": r'(?:Gender|Sex)[:;]?\s*(Male|Female|Other|M|F)(?=\n|$)',
        "Blood Group": r'(?:Blood(?:\s*Group)?)[:;]?\s*([ABO][+-]|AB[+-])(?=\n|$)',
        "Address": r'(?:Address|Location|Place|Residence)[:;]?\s*([\w\s,\.\-\/]+?)(?=\n|$|(?:Phone|Mobile|Contact|Email))',
        "Hospital Name": r'(?:Hospital(?:\s*Name)?|Clinic|Medical Center)[:;]?\s*([\w\s\.]+?)(?=\n|$|(?:Doctor|Dr|MD|Address))',
        "Insurance ID": r'(?:Insurance(?:\s*(?:ID|Number|No))?|Policy(?:\s*Number)?)[:;]?\s*([\w\d\-]+?)(?=\n|$)',
        "Phone Number": r'(?:Phone(?:\s*Number)?|Mobile|Contact|Cell)[:;]?\s*([\d\s\+\-\(\)]+?)(?=\n|$)',
        "Amount": r'(?:Amount|Total|Cost|Fee|Charges)[:;]?\s*([\d\.]+?)(?=\n|$|Rs|\$|₹)',
        "Disease Name": r'(?:Disease(?:\s*Name)?|Diagnosis|Condition|Ailment)[:;]?\s*([\w\s]+?)(?=\n|$|(?:Disease Details|Symptoms|Treatment))',
        "Disease Details": r'(?:Disease(?:\s*Details)?|Details|Diagnosis Details|Clinical Details|Symptoms)[:;]?\s*([\w\s,\.;\(\)\-\/]+?)(?=\n\n|\n(?:Medicines|Medications|Drugs)|$)',
        "Medicines": r'(?:Medicines|Medications|Drugs|Prescriptions|Medicine List)[:;]?\s*([\w\s,\.;\(\)\-\/]+?)(?=\n\n|\n(?:Bed|Ventilation|Amount|Charges)|$)',
        "Bed Type": r'(?:Bed(?:\s*Type)?)[:;]?\s*([\w\s]+?)(?=\n|$)',
        "Ventilation": r'(?:Ventilation|Ventilator|Oxygen)[:;]?\s*(Yes|No|Required|Not Required)(?=\n|$)',
        "Other Charges": r'(?:Other(?:\s*Charges)?|Additional(?:\s*Charges)?|Extra)[:;]?\s*([\d\.]+?)(?=\n|$|Rs|\$|₹)'
    }
    
    # 1. First pass: Extract Aadhaar number with dedicated function
    aadhaar = extract_aadhaar_number(text)
    if aadhaar:
        formatted_aadhaar = f"{aadhaar[:4]}-{aadhaar[4:8]}-{aadhaar[8:]}"
        extracted_info.append({"Text": formatted_aadhaar, "Label": "Aadhar Card"})
        found_labels.add("Aadhar Card")
    
    # 2. Second pass: Extract other fields with improved boundary detection
    for label, pattern in field_patterns.items():
        if label in found_labels:
            continue
            
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            extracted_text = matches.group(1).strip()
            # Clean the extracted text to remove potential label contamination
            cleaned_text = clean_extracted_field(extracted_text, label)
            
            # Only add if we have meaningful content
            if cleaned_text and len(cleaned_text) > 0:
                extracted_info.append({"Text": cleaned_text, "Label": label})
                found_labels.add(label)
    
    # 3. Third pass: Look for unlabeled numbers that might be specific fields
    if "Phone Number" not in found_labels:
        # Look for potential phone numbers (10-digit sequences)
        phone_matches = re.search(r'(?<!\d)(\d{10})(?!\d)', text)
        if phone_matches:
            extracted_info.append({"Text": phone_matches.group(1), "Label": "Phone Number"})
            found_labels.add("Phone Number")
    
    # Look for Appendicitis or other common conditions if disease name not found
    if "Disease Name" not in found_labels:
        common_diseases = ["appendicitis", "diabetes", "hypertension", "cancer", "fracture", "pneumonia"]
        for disease in common_diseases:
            if re.search(rf'\b{disease}\b', text, re.IGNORECASE):
                extracted_info.append({"Text": disease.capitalize(), "Label": "Disease Name"})
                found_labels.add("Disease Name")
                break
    
    return extracted_info

def process_text(text, keywords=[]):
    """
    Main processing function that combines extraction methods
    """
    # Get fields using improved boundary detection
    extracted_info = extract_fields_with_boundaries(text)
    
    # For backward compatibility, still use keyword-based extraction for any missing fields
    found_labels = {item["Label"] for item in extracted_info}
    
    for keyword in keywords:
        # Skip keywords for fields we already found
        label = keyword.replace(":", "").strip()
        if any(label in existing for existing in found_labels):
            continue
            
        # Simple keyword-based extraction as fallback
        pattern = re.compile(rf"{re.escape(keyword)}\s*([\w\s\d\.\-]+?)(?=\n|$)", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            extracted_text = match.group(1).strip()
            cleaned_text = clean_extracted_field(extracted_text, label)
            
            if cleaned_text and len(cleaned_text) > 0:
                extracted_info.append({"Text": cleaned_text, "Label": label})
                found_labels.add(label)
    
    return extracted_info

# The extract_aadhaar_number function from previous solution should be included here
def extract_aadhaar_number(text):
    """
    Specialized function to extract Aadhaar numbers using multiple approaches
    """
    # Clean the text first - this can help with OCR errors
    cleaned_text = re.sub(r'\s+', ' ', text)
    
    # Method 1: Look for common Aadhaar number patterns (12 digits with or without separators)
    aadhaar_patterns = [
        # Pattern with no separators - 12 consecutive digits
        r'(?<!\d)(\d{12})(?!\d)',
        # Pattern with space separators
        r'(\d{4}\s+\d{4}\s+\d{4})',
        # Pattern with dash separators
        r'(\d{4}-\d{4}-\d{4})',
        # Pattern with dot separators
        r'(\d{4}\.\d{4}\.\d{4})'
    ]
    
    for pattern in aadhaar_patterns:
        matches = re.findall(pattern, cleaned_text)
        if matches:
            # Clean up the found number (remove spaces, dashes)
            aadhaar = re.sub(r'[^\d]', '', matches[0])
            if len(aadhaar) == 12:
                return aadhaar
    
    # Method 2: Look for Aadhaar numbers with keywords
    keyword_patterns = [
        # Various ways "Aadhaar" might be written followed by a number
        r'(?:aadhar|aadhaar|adhar|aadha+r|आधार)(?:\s*(?:card|number|no|id|#|:|नंबर|संख्या))?\s*[:\.\-]?\s*((?:\d[\d\s\.\-]*){12})',
        r'(?:uid|unique\s+id)(?:\s*(?:number|no|#))?\s*[:\.\-]?\s*((?:\d[\d\s\.\-]*){12})',
        # Looking for "No:" or "Number:" followed by what could be an Aadhaar
        r'(?:no|number|id)?\s*[:\.\-]\s*((?:\d[\d\s\.\-]*){12})'
    ]
    
    for pattern in keyword_patterns:
        matches = re.findall(pattern, cleaned_text.lower())
        if matches:
            # Clean up the found number
            aadhaar = re.sub(r'[^\d]', '', matches[0])
            if len(aadhaar) == 12:
                return aadhaar
    
    # Method 3: More aggressive - find any 12-digit sequence that could be an Aadhaar number
    digit_sequences = re.findall(r'(?<!\d)(\d[\d\s\.\-]*\d)(?!\d)', cleaned_text)
    for seq in digit_sequences:
        digits_only = re.sub(r'[^\d]', '', seq)
        if len(digits_only) == 12:
            return digits_only
            
    return None
def save_to_database(data, insurance_id, file_path):
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cursor = cnx.cursor()

        # Insert document information into the 'patient_documents' table
        insert_doc_query = "INSERT INTO patient_documents (insurance_id, file_path) VALUES (%s, %s)"
        doc_values = (insurance_id, file_path)
        cursor.execute(insert_doc_query, doc_values)

        # Modified query to exclude the ventilation and appointment_time columns
        insert_patient_query = """
        INSERT INTO patient_details 
        (insurance_id, name, father_name, aadhar_card, gender, blood_group, 
        address, hospital_name, phone_number, amount, 
        disease_name, disease_details, medicines, bed_type, other_charges) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        name = next((item["Text"] for item in data if item["Label"] == "Name"), None)
        father_name = next((item["Text"] for item in data if item["Label"] == "Father's Name"), None)
        aadhar_card = next((item["Text"] for item in data if item["Label"] == "Aadhar Card"), None)
        gender = next((item["Text"] for item in data if item["Label"] == "Gender"), None)
        blood_group = next((item["Text"] for item in data if item["Label"] == "Blood Group"), None)
        address = next((item["Text"] for item in data if item["Label"] == "Address"), None)
        hospital_name = next((item["Text"] for item in data if item["Label"] == "Hospital Name"), None)
        phone_number = next((item["Text"] for item in data if item["Label"] == "Phone Number"), None)
        
        # Clean the amount value
        amount = next((item["Text"] for item in data if item["Label"] == "Amount"), None)
        if amount:
            amount = re.sub(r'[^\d.]', '', amount)
            if amount:
                try:
                    amount = float(amount)
                except ValueError:
                    amount = None
        
        disease_name = next((item["Text"] for item in data if item["Label"] == "Disease Name"), None)
        disease_details = next((item["Text"] for item in data if item["Label"] == "Disease Details"), None)
        medicines = next((item["Text"] for item in data if item["Label"] == "Medicines"), None)
        bed_type = next((item["Text"] for item in data if item["Label"] == "Bed Type"), None)
        
        # Clean other_charges
        other_charges = next((item["Text"] for item in data if item["Label"] == "Other Charges"), None)
        if other_charges:
            other_charges = re.sub(r'[^\d.]', '', other_charges)
            if other_charges:
                try:
                    other_charges = float(other_charges)
                except ValueError:
                    other_charges = None

        # Note: ventilation and appointment_time are removed from the values tuple
        patient_values = (insurance_id, name, father_name, aadhar_card, gender, blood_group, 
                          address, hospital_name, phone_number, amount, 
                          disease_name, disease_details, medicines, bed_type, other_charges)
        
        cursor.execute(insert_patient_query, patient_values)

        cnx.commit()
        cursor.close()
        cnx.close()
        with output_widget:
            print("Data saved to database successfully.")
    except mysql.connector.Error as err:
        with output_widget:
            print(f"Error saving to database: {err}")
def process_file(file_path):
    try:
        text = ""
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            text = extract_text_from_image(file_path)
        elif file_path.lower().endswith('.pdf'):
            text = extract_text_from_pdf(file_path)

        with output_widget:
            output_widget.clear_output()
            if not text.strip():
                print("Error: No text detected in the file.")
                return

            print("Full Extracted Text:", text)

            important_info = process_text(text, ["Name:", "Father's Name:", "Aadhar Card:", "Gender:", "Blood Group:", "Address:", "Hospital Name:", "Insurance ID:", "Phone Number:", "Amount:", "Disease Name:", "Disease Details:", "Medicines:", "Bed Type:", "Ventilation:", "Other Charges:"])
            if important_info:
                display(Markdown("### Important Extracted Information:"))
                df = pd.DataFrame(important_info)
                display(df)

                insurance_id_data = next((item["Text"] for item in important_info if item["Label"] == "Insurance ID"), None)

                if insurance_id_data is None:
                    print("Error: Insurance ID not found. Data not saved.")
                    return

                save_to_database(important_info, insurance_id_data, file_path)
            else:
                display(Markdown("**No important information found.**"))
    except Exception as e:
        with output_widget:
            output_widget.clear_output()
            print(f"An error occurred: {e}")

file_chooser = FileChooser()

def on_file_chosen(chooser):
    if chooser.selected:
        process_file(chooser.selected)

file_chooser.register_callback(on_file_chosen)

display(file_chooser, output_widget)

pytesseract.pytesseract.tesseract_cmd = r'/opt/homebrew/Caskroom/miniconda/base/bin/tesseract'