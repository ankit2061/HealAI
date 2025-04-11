import streamlit as st
from pymongo import MongoClient
import google.generativeai as genai
import re
# import requests
# from dotenv import load_dotenv
# import os

import creds


# MongoDB Configuration
MONGO_CONFIG = {
    "host": "127.0.0.1",
    "port": 27017,
    "db_name": "ClaimDetails",
}



# Gemini API Configuration
genai.configure(api_key=creds.api_key)

def get_gemini_explanation(prompt):
    model = genai.GenerativeModel('gemini-2.0-flash')
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini API Error: {e}"

def get_data_from_mongodb(insurance_id, field):
    try:
        client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])
        db = client[MONGO_CONFIG["db_name"]]
        patient_details = db.patient_details
        patient_data = patient_details.find_one({"insurance_id": insurance_id})
        
        if patient_data and patient_data.get(field):
            return patient_data[field]
        else:
            return "Data not found in database."
    except Exception as e:
        return f"MongoDB Error: {e}"

st.title("Insurance and Medical Term Explainer:")
st.write("Ask about insurance terms, medical conditions (or retrieve patient data)")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("What would you like to know?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Process the query
    query = prompt.strip().lower()
    
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
            field_match = re.search(r'(name|father|aadhar|gender|blood|address|hospital|phone|disease|medicines|bed|amount|charges)', query, re.IGNORECASE)
            
            if field_match:
                field = field_match.group(0).lower().replace("'", "")
                response = get_data_from_mongodb(insurance_id, field)
            else:
                response = "Please specify a field (name, address, etc.)."
        else:
            response = "Please provide an Insurance ID."
    
    else:
        response = "I can help explain medical and insurance terms, and retrieve data from the extracted claims. Please specify what you are looking for."
    
    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        st.markdown(response)
    
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})