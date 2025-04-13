import streamlit as st
import google.generativeai as genai
import re
import os

# Google Gemini API Configuration
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Error Handling Decorator
def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            st.error(f"Error: {e}")
            return None
    return wrapper

# Input Validation Functions
def validate_insurance_id(insurance_id):
    return re.match(r'^[A-Za-z0-9-]+$', insurance_id) is not None  # More permissive

def validate_field_name(field):
    valid_fields = ["name", "father", "aadhar", "gender", "blood",
                   "address", "hospital", "phone", "disease",
                   "medicines", "bed", "amount", "charges"]
    return field.lower() in valid_fields

@handle_errors
def get_gemini_explanation(prompt):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini API Error: {e}"

# Mock data for testing
MOCK_PATIENT_DATA = {
    "12345": {
        "name": "John Doe",
        "father": "Robert Doe",
        "aadhar": "1234-5678-9012",
        "gender": "Male",
        "blood": "O+",
        "address": "123 Main St, Anytown, USA",
        "hospital": "General Hospital",
        "phone": "555-123-4567",
        "disease": "Hypertension",
        "medicines": "Lisinopril, Amlodipine",
        "bed": "Room 302, Bed 1",
        "amount": "5000",
        "charges": "500"
    },
    "67890": {
        "name": "Jane Smith",
        "father": "David Smith",
        "aadhar": "9876-5432-1098",
        "gender": "Female",
        "blood": "A-",
        "address": "456 Oak St, Othertown, USA",
        "hospital": "Community Medical Center",
        "phone": "555-987-6543",
        "disease": "Diabetes",
        "medicines": "Metformin, Insulin",
        "bed": "Room 205, Bed 2",
        "amount": "6500",
        "charges": "650"
    }
}

@handle_errors
def get_patient_data(insurance_id, field):
    if insurance_id in MOCK_PATIENT_DATA and field in MOCK_PATIENT_DATA[insurance_id]:
        return MOCK_PATIENT_DATA[insurance_id][field]
    else:
        return "Data not found in database."

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "username" not in st.session_state:
    st.session_state.username = None

if "users" not in st.session_state:
    st.session_state.users = {}

# Username input for first-time users
if st.session_state.username is None:
    st.title("Welcome to the Insurance and Medical Term Explainer")
    st.write("Please enter your username to get started.")
    
    username = st.text_input("Username", key="username_input")
    
    if st.button("Submit"):
        if username:
            # Save username in session state
            st.session_state.username = username
            # Initialize user if first time
            if username not in st.session_state.users:
                st.session_state.users[username] = {"joined_at": "now"}
            
            st.success(f"Welcome, {username}!")
            st.rerun()
        else:
            st.error("Please enter a valid username.")

# Main application once username is set
else:
    st.title(f"Hello, {st.session_state.username}! Insurance and Medical Term Explainer")
    st.write("Ask about insurance terms, medical conditions, or retrieve patient data")

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Sidebar for navigation (simulating routes)
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Chat", "Explainer"])

    # Explainer Page (simulated route)
    if page == "Explainer":
        st.subheader("Common Terms")
        st.write("- **Deductible:** The amount you pay before your insurance starts to pay.")
        st.write("- **Premium:** The monthly payment you make to have insurance.")
        st.write("- **Co-pay:** A fixed amount you pay for a covered healthcare service.")
        st.write("- **Out-of-pocket maximum:** The most you'll pay for covered services in a year.")
        st.write("- **EOB (Explanation of Benefits):** A statement from your insurance company explaining what was covered.")

    # Chat Page
    elif page == "Chat":
        if prompt := st.chat_input("What would you like to know?"):
            # Add user message to session state
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)

            query = prompt.strip().lower()
            response = None  # Initialize response

            if any(keyword in query for keyword in ["insurance", "policy", "claim", "deductible", "premium"]):
                prompt_text = f"Explain the insurance term '{query}'. Provide a clear and concise explanation."
                response = get_gemini_explanation(prompt_text)

            elif any(keyword in query for keyword in ["medical", "disease", "medicine", "hypertension", "diabetes", "appendicitis"]):
                prompt_text = f"Explain the medical term '{query}'. Provide a clear and concise explanation."
                response = get_gemini_explanation(prompt_text)

            elif any(keyword in query for keyword in ["data", "information", "details", "name", "father", "aadhar", "gender", "blood", "address", "hospital", "phone", "disease", "medicines", "bed", "amount", "charges"]):
                insurance_id_match = re.search(r'\b[A-Za-z0-9-]+\b', query)

                if insurance_id_match:
                    insurance_id = insurance_id_match.group(0)

                    if not validate_insurance_id(insurance_id):
                        response = "Invalid Insurance ID format. Please use a valid ID."
                    else:
                        field_match = re.search(r'(name|father|aadhar|gender|blood|address|hospital|phone|disease|medicines|bed|amount|charges)', query, re.IGNORECASE)

                        if field_match:
                            field = field_match.group(0).lower()
                            if not validate_field_name(field):
                                response = f"Invalid field name. Choose from: name, father, aadhar, gender, blood, address, hospital, phone, disease, medicines, bed, amount, charges."
                            else:
                                response = get_patient_data(insurance_id, field)
                        else:
                            response = "Please specify a field (name, address, etc.)."
                else:
                    response = "Please provide an Insurance ID."

            else:
                response = "I can help explain medical and insurance terms, and retrieve data. Please specify what you are looking for."

            if response:
                with st.chat_message("assistant"):
                    st.markdown(response)
                # Add assistant response to session state
                st.session_state.messages.append({"role": "assistant", "content": response})
