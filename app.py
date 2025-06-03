import streamlit as st
import google.generativeai as genai
import PyPDF2
from PIL import Image
import io
import sqlite3
import json
import datetime
import os
import re # For regex-based Bengali character detection

# --- Configuration ---
MODEL_NAME = "models/gemini-2.0-flash" # User-specified model name
API_KEY = "AIzaSyCH6v9snOFfIil6pplbVB0mPQnTckxJWj0" # Replace with your actual key
DB_FILE = "prescription_sessions.db"

# --- Initialize Gemini AI ---
try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    st.error(f"Failed to configure Gemini AI. Please check your API key: {e}")
    st.stop()

try:
    model = genai.GenerativeModel(MODEL_NAME)
except Exception as e:
    st.error(f"Failed to create Gemini Model '{MODEL_NAME}'. Is the model name correct and supported? Error: {e}")
    st.stop()


# --- Database Functions ---
def init_db():
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                file_name TEXT,
                input_content_preview TEXT,
                extracted_medicines_json TEXT,
                generated_details_json TEXT -- This will now store a more complex structure
            )
        ''')
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()

def save_session_to_db(file_name, input_content_preview, extracted_medicines, generated_details_list):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # `extracted_medicines` here should be the list of *original* names before translation for record keeping
        extracted_meds_json = json.dumps(extracted_medicines) # Storing original names
        generated_details_json = json.dumps(generated_details_list) # Storing list of dicts (each dict has 16 points + highlights/queries)

        cursor.execute('''
            INSERT INTO sessions (timestamp, file_name, input_content_preview, extracted_medicines_json, generated_details_json)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, file_name, input_content_preview, extracted_meds_json, generated_details_json))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Error saving session to database: {e}")
    finally:
        if conn:
            conn.close()

def load_sessions_from_db():
    conn = None
    sessions = []
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row # To access columns by name
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions ORDER BY timestamp DESC")
        sessions = cursor.fetchall()
    except sqlite3.Error as e:
        st.error(f"Error loading sessions from database: {e}")
    finally:
        if conn:
            conn.close()
    return sessions

# --- Text Extraction from Documents ---
def extract_text_from_pdf(uploaded_file_bytes):
    text = ""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file_bytes))
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            if page.extract_text():
                text += page.extract_text() + "\n" # Add newline between pages
        return text.strip() if text else None
    except Exception as e:
        st.warning(f"Could not extract text directly from PDF: {e}. Will attempt OCR if it's image-based.")
        return None

def extract_text_from_image_or_pdf_ocr(file_bytes, model_instance):
    try:
        image = Image.open(io.BytesIO(file_bytes))
        # For PDF OCR, we are essentially treating the PDF as an image (or its pages).
        # This might need a more sophisticated PDF-to-image conversion for multi-page PDFs
        # if Gemini doesn't handle multi-frame images well from PDF bytes.
        # For now, assume it processes the first page or a general representation.
        st.write("_Performing OCR on the document..._")
        prompt_parts = [
            "This document is a medical prescription. Extract all readable text, paying close attention to medicine names, dosages, and doctor's notes. Preserve the layout or indicate line breaks if possible. If the text is in Bengali, provide the Bengali text.",
            image
        ]
        response = model_instance.generate_content(prompt_parts)
        if response.text and response.text.strip():
            st.success("OCR successful.")
            return response.text.strip()
        else:
            st.error("OCR did not yield any text.")
            return None
    except UnidentifiedImageError:
        st.error("The uploaded PDF could not be processed as an image for OCR. It might not be an image-based PDF or is corrupted.")
        return None
    except Exception as e:
        st.error(f"Error during OCR processing: {e}")
        return None


# --- Language Processing ---
def contains_bengali_chars(text):
    return bool(re.search(r'[\u0980-\u09FF]', text))

def translate_to_english_if_needed(name, model_instance):
    if not contains_bengali_chars(name): # If no Bengali characters, assume English or other Latin script
        # Simple check: if it contains any letter a-z, assume it's fine.
        if re.search(r'[a-zA-Z]', name):
            return name # Already likely English or scientific name
        # If no Bengali and no English, it's ambiguous, but we'll try to process as is
        # or let Gemini handle it in the details fetching if it's a very unusual script.

    st.write(f"_Translating '{name}' to English (if applicable)..._")
    prompt = f"""The following is a medicine name, possibly in Bengali: '{name}'.
If this name is primarily in Bengali script, translate it to its common English pharmaceutical equivalent.
If the name is already in English or a widely recognized Latin-script brand/scientific name (even if used in Bangladesh), return the original name.
Output ONLY the final name. For example:
Input: 'নাপা', Output: 'Napa'
Input: 'প্যারাসিটামল', Output: 'Paracetamol'
Input: 'Amoxicillin', Output: 'Amoxicillin'
Input: 'সেকলো', Output: 'Seclo'

Processed Name:""" # Added a clear marker for easier parsing

    try:
        response = model_instance.generate_content(prompt)
        if response.text:
            # Try to parse after "Processed Name:"
            processed_text = response.text.strip()
            if "processed name:" in processed_text.lower():
                translated_name = processed_text.split(":", 1)[-1].strip()
            else: # Fallback if marker not found (Gemini might just return the name)
                translated_name = processed_text

            if translated_name and translated_name.lower() != name.lower():
                st.write(f"    Translated '{name}' to '{translated_name}'")
                return translated_name
            return name # Return original if no effective translation or already English/processed
        return name
    except Exception as e:
        st.warning(f"Translation attempt failed for '{name}': {e}")
        return name


# --- Gemini AI Interactions ---
def get_medicine_names_from_text(document_text, model_instance):
    prompt = f"""From the following doctor's prescription text, extract only the names of medicines.
List each medicine name on a new line. Do not include dosages, frequencies, or other text.
If a medicine name appears to be in Bengali, provide it in Bengali.
If no medicines are found, output the single word 'NONE'.

Prescription Text:
{document_text}

Medicine Names:
"""
    try:
        response = model_instance.generate_content(prompt)
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            st.warning(f"Medicine name extraction blocked: {response.prompt_feedback.block_reason}")
            return []
        if response.text.strip().upper() == "NONE":
            return []
        
        # Robust parsing for medicine names
        lines = response.text.splitlines()
        medicines_started = False
        medicine_names_list = []
        for line in lines:
            if "medicine names:" in line.lower():
                medicines_started = True
                line_content = line.lower().split("medicine names:",1)[1].strip()
                if line_content and line_content.upper() != "NONE":
                    medicine_names_list.append(line_content.strip())
                continue
            if medicines_started and line.strip() and line.strip().upper() != "NONE":
                medicine_names_list.append(line.strip())
        
        # Fallback if the above parsing fails but there's text
        if not medicine_names_list and response.text.strip() and response.text.strip().upper() != "NONE":
             potential_names = [name.strip() for name in response.text.split('\n') if name.strip() and name.strip().upper() != "NONE"]
             # Filter out common non-medicine phrases if any (this is heuristic)
             medicine_names_list = [name for name in potential_names if len(name) > 2 and not name.lower().startswith(("dosage:", "frequency:", "dr."))]


        return list(filter(None, medicine_names_list)) # Remove any empty strings
    except Exception as e:
        st.error(f"Error extracting medicine names: {e}")
        return []


def get_medicine_details_from_gemini(medicine_name_english, model_instance):
    prompt = f"""
    You are an AI assistant for a pharmacist in Bangladesh.
    For the medicine '{medicine_name_english}', provide the following information.

    Instructions:
    1.  **Primary Source (Medex.com.bd):** First, prioritize finding information from `https://medex.com.bd`. You can simulate searching it using a query like `https://medex.com.bd/search?search={medicine_name_english}`.
    2.  **Secondary Sources (General Web Search):** If Medex.com.bd does not yield complete information, use your general web search capabilities (like Google) and knowledge from other reliable medical sources.
    3.  **Bangladesh Context:** Where possible, provide information relevant to Bangladesh (e.g., manufacturers available locally). However, for general medical facts (pharmacology, side effects), standard information is acceptable if Bangladesh-specific nuances aren't readily found. Do not mark fields as 'Not Found' solely for lacking a BD-specific version if general info exists.
    4.  **Output Structure:** Use the exact numbered fields below. If information for a field is genuinely unavailable after all search attempts, state 'Not Found'.

    **Structured Information (1-16):**
    1. Medicine Name: {medicine_name_english} (Confirm or provide the most common name)
    2. Medicine Manufacturer Name: (List known in Bangladesh if possible, otherwise general)
    3. Indications:
    4. Pharmacology:
    5. Dosage & Administration:
    6. Interaction:
    7. Contraindications:
    8. Side Effects:
    9. Pregnancy & Lactation:
    10. Precautions & Warnings:
    11. Use in Special Populations:
    12. Overdose Effects:
    13. Therapeutic Class:
    14. Storage Conditions:
    15. Chemical Structure (Molecular Formula):
    16. Primary Website URL: (The most relevant medex.com.bd page URL if found. Otherwise, the URL of another primary source used for the above details. If multiple general sources, state 'Multiple general sources used' or 'Not Found').

    **Web Search Highlights (17):**
    17. Web Search Highlights:
        *   Provide up to 3 key web search results (e.g., from Google) that appear most relevant for a pharmacist researching '{medicine_name_english}'.
        *   For each result, use this exact format:
            Title: [Page Title]
            URL: [Full URL]
            Snippet: [A brief 1-2 sentence summary or snippet]
        *   If no relevant web search results can be summarized in this way, state 'No specific web search highlights found under this section.'

    **Final Fallback (Only if EVERYTHING above fails):**
    If, after all attempts, you can find *absolutely no information for points 1-16 AND no web search highlights for point 17*, then output ONLY the following line and nothing else:
    COMPLETE_INFO_FAILURE_SUGGEST_QUERIES: {medicine_name_english} generic name, {medicine_name_english} uses Bangladesh, {medicine_name_english} side effects

    --- End of Instructions ---
    Begin Response:
    """
    
    details = {"original_query_name": medicine_name_english} # Store the name used for this query
    keys_order_structured = [
        "Medicine Name", "Medicine Manufacturer Name", "Indications", "Pharmacology",
        "Dosage & Administration", "Interaction", "Contraindications", "Side Effects",
        "Pregnancy & Lactation", "Precautions & Warnings", "Use in Special Populations",
        "Overdose Effects", "Therapeutic Class", "Storage Conditions",
        "Chemical Structure (Molecular Formula)", "Primary Website URL"
    ]
    details['web_search_highlights'] = []
    details['suggested_queries'] = []

    try:
        response = model_instance.generate_content(prompt)
        
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            st.warning(f"Content generation for '{medicine_name_english}' blocked: {response.prompt_feedback.block_reason}")
            details["error_message"] = f"Blocked ({response.prompt_feedback.block_reason})"
            for key in keys_order_structured: details[key] = "Blocked"
            return details

        raw_text = response.text
        # st.text_area(f"Raw Gemini Response for {medicine_name_english}", raw_text, height=300) # DEBUG

        if "COMPLETE_INFO_FAILURE_SUGGEST_QUERIES:" in raw_text:
            query_line = raw_text.split("COMPLETE_INFO_FAILURE_SUGGEST_QUERIES:",1)[1].strip()
            details['suggested_queries'] = [q.strip() for q in query_line.split(',')]
            for key in keys_order_structured: details[key] = "Not Found (Complete Failure)"
            return details

        current_structured_field = None
        current_value_lines = []
        parsing_highlights = False
        current_highlight = {}

        lines = raw_text.splitlines()
        for line_idx, line_content in enumerate(lines):
            line = line_content.strip()
            if not line: continue

            # Check for start of Web Search Highlights
            if line.startswith("17. Web Search Highlights:"):
                if current_structured_field and current_value_lines: # Save last structured field
                    details[current_structured_field] = "\n".join(current_value_lines).strip()
                    current_value_lines = []
                current_structured_field = None # Done with structured part
                parsing_highlights = True
                if "No specific web search highlights found" in line:
                    details['web_search_highlights'].append({"title": "Info", "snippet": "No specific web search highlights found by AI."})
                continue

            if parsing_highlights:
                if line.startswith("Title:"):
                    if current_highlight.get("snippet"): # Save previous highlight
                        details['web_search_highlights'].append(current_highlight)
                        current_highlight = {}
                    current_highlight["title"] = line.split(":",1)[1].strip()
                elif line.startswith("URL:"):
                    current_highlight["url"] = line.split(":",1)[1].strip()
                elif line.startswith("Snippet:"):
                    current_highlight["snippet"] = line.split(":",1)[1].strip()
                elif current_highlight.get("snippet"): # if snippet exists, and this line is not a new key, append to snippet
                     current_highlight["snippet"] += " " + line
                continue # Move to next line after processing highlight line

            # Parsing structured fields (1-16)
            # Check if line starts with "N. Field Name:"
            matched_field = False
            for i, key_name in enumerate(keys_order_structured):
                if line.startswith(f"{i+1}. {key_name}:"):
                    if current_structured_field and current_value_lines: # Save previous field's value
                        details[current_structured_field] = "\n".join(current_value_lines).strip()
                    
                    current_structured_field = key_name
                    current_value_lines = [line.split(":",1)[1].strip()]
                    matched_field = True
                    break
            
            if not matched_field and current_structured_field:
                current_value_lines.append(line) # Append to current field's value

        # Save the last field (either structured or highlight)
        if current_structured_field and current_value_lines:
            details[current_structured_field] = "\n".join(current_value_lines).strip()
        if current_highlight.get("snippet"): # Save last highlight item
            details['web_search_highlights'].append(current_highlight)

        # Ensure all structured keys are present
        for key in keys_order_structured:
            if key not in details:
                details[key] = "Not Found"
            elif isinstance(details[key], list) and not details[key]: # if it was init as [] and never filled
                 details[key] = "Not Found"


    except Exception as e:
        st.error(f"Error parsing details for '{medicine_name_english}': {e}")
        details["error_message"] = f"Error during processing: {e}"
        for key in keys_order_structured: details[key] = "Error"

    return details


# --- Streamlit App ---
def main():
    st.set_page_config(
        page_title="Pharmacist Prescription Assistant",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("💊 Pharmacist Prescription Assistant")
    st.markdown("""
    Upload a doctor's prescription (PDF or Image) to extract medicine names, translate if necessary,
    and get detailed information including web search highlights.
    This tool is intended for **professional pharmacists**.
    """)
    st.info("""
    **Process:**
    1.  Extract text from document (using OCR if needed).
    2.  Identify medicine names (Bengali names will be translated to English).
    3.  For each medicine, fetch details prioritizing `medex.com.bd`, then general web search.
    4.  Display structured info and web search highlights.
    Please always verify critical medical information.
    """)

    init_db()

    uploaded_file = st.file_uploader(
        "Upload Prescription (PDF or Image)",
        type=["pdf", "png", "jpg", "jpeg"],
        help="Upload your prescription file here."
    )

    if uploaded_file is not None:
        file_name = uploaded_file.name
        file_type = uploaded_file.type
        file_bytes = uploaded_file.getvalue()

        st.subheader(f"Processing: {file_name}")
        all_extracted_text = ""
        input_content_preview = f"{file_type} - {file_name}"

        with st.spinner("Extracting content from document..."):
            if file_type == "application/pdf":
                direct_text = extract_text_from_pdf(file_bytes)
                if direct_text:
                    all_extracted_text = direct_text
                    st.success("Text extracted directly from PDF.")
                else: # Try OCR for image-based PDF
                    all_extracted_text = extract_text_from_image_or_pdf_ocr(file_bytes, model)
                    input_content_preview += " (OCR Attempted)"
            elif file_type.startswith("image/"):
                all_extracted_text = extract_text_from_image_or_pdf_ocr(file_bytes, model)
                input_content_preview += " (Image OCR)"
            else:
                st.error("Unsupported file type.")
                all_extracted_text = None
        
        if all_extracted_text:
            st.expander("View Extracted Text from Document").text_area("", all_extracted_text, height=150)
            input_content_preview = all_extracted_text[:200] + ("..." if len(all_extracted_text) > 200 else "")
            
            with st.spinner("Identifying medicine names..."):
                original_medicine_names = get_medicine_names_from_text(all_extracted_text, model)

            if original_medicine_names:
                st.subheader(f"Identified Potential Medicines ({len(original_medicine_names)}):")
                st.write(", ".join(original_medicine_names))

                processed_medicine_details_list = [] # This will store dicts for DB
                
                progress_bar = st.progress(0)
                status_text = st.empty()

                for i, original_med_name in enumerate(original_medicine_names):
                    status_text.text(f"Processing {i+1}/{len(original_medicine_names)}: {original_med_name}")
                    
                    st.markdown(f"---")
                    st.markdown(f"#### Details for: **{original_med_name}**")

                    english_med_name = translate_to_english_if_needed(original_med_name, model)
                    if english_med_name.lower() != original_med_name.lower():
                        st.markdown(f"_(Queried as: **{english_med_name}**)_")
                    
                    with st.spinner(f"Fetching details for '{english_med_name}'..."):
                        med_details_dict = get_medicine_details_from_gemini(english_med_name, model)
                        # Store the original name with details for context if needed, but details are for english_med_name
                        med_details_dict['original_extracted_name'] = original_med_name
                        processed_medicine_details_list.append(med_details_dict)

                    # Display structured information
                    keys_order_display = [
                        "Medicine Name", "Medicine Manufacturer Name", "Indications", "Pharmacology",
                        "Dosage & Administration", "Interaction", "Contraindications", "Side Effects",
                        "Pregnancy & Lactation", "Precautions & Warnings", "Use in Special Populations",
                        "Overdose Effects", "Therapeutic Class", "Storage Conditions",
                        "Chemical Structure (Molecular Formula)", "Primary Website URL"
                    ]
                    has_structured_info = False
                    for key_display in keys_order_display:
                        value = med_details_dict.get(key_display, "Not Found")
                        if value and value not in ["Not Found", "Error", "Blocked", "Not Found (Complete Failure)"]:
                            has_structured_info = True
                        st.markdown(f"**{key_display}:** {value}")
                    
                    # Display Web Search Highlights
                    if med_details_dict.get('web_search_highlights'):
                        st.markdown("**Web Search Highlights:**")
                        for item_idx, item in enumerate(med_details_dict['web_search_highlights']):
                            if item.get("title") == "Info" and "No specific web search highlights found" in item.get("snippet",""):
                                st.markdown(f"- __{item.get('snippet')}__")
                            else:
                                st.markdown(f"- **{item.get('title', 'N/A')}**")
                                if item.get('url'): st.markdown(f"  URL: <{item.get('url')}>") # Make it a clickable link
                                if item.get('snippet'): st.markdown(f"  Snippet: _{item.get('snippet')}_")
                        has_structured_info = True # Even if only highlights, consider it info found

                    # Display Suggested Queries (if COMPLETE_INFO_FAILURE)
                    if med_details_dict.get('suggested_queries'):
                        st.markdown("**Could not find detailed information. Suggested Search Queries:**")
                        for q_idx, query in enumerate(med_details_dict['suggested_queries']):
                            st.markdown(f"- `{query}`")
                        if not has_structured_info: # If absolutely nothing else was shown
                             st.warning("No structured details or web highlights were found for this item.")
                    
                    if med_details_dict.get("error_message"):
                        st.error(f"An error occurred: {med_details_dict['error_message']}")

                    progress_bar.progress((i + 1) / len(original_medicine_names))
                status_text.text("All medicines processed.")

                if processed_medicine_details_list:
                    save_session_to_db(file_name, input_content_preview, original_medicine_names, processed_medicine_details_list)
                    st.success("Session and all processed details saved to database!")

                    # Prepare text for download (includes structured, highlights, and queries)
                    full_generated_text_for_download_str = ""
                    for details_dict in processed_medicine_details_list:
                        full_generated_text_for_download_str += f"--- Details for {details_dict.get('original_extracted_name')} (Queried as: {details_dict.get('original_query_name')}) ---\n"
                        for key in keys_order_display: # Structured info
                            full_generated_text_for_download_str += f"{key}: {details_dict.get(key, 'N/A')}\n"
                        
                        if details_dict.get('web_search_highlights'):
                            full_generated_text_for_download_str += "\nWeb Search Highlights:\n"
                            for item in details_dict['web_search_highlights']:
                                full_generated_text_for_download_str += f"  Title: {item.get('title', 'N/A')}\n"
                                full_generated_text_for_download_str += f"  URL: {item.get('url', 'N/A')}\n"
                                full_generated_text_for_download_str += f"  Snippet: {item.get('snippet', 'N/A')}\n\n"
                        
                        if details_dict.get('suggested_queries'):
                            full_generated_text_for_download_str += "\nSuggested Search Queries (if info was scarce):\n"
                            for q in details_dict['suggested_queries']:
                                full_generated_text_for_download_str += f"- {q}\n"
                        full_generated_text_for_download_str += "\n\n"

                    download_filename = f"prescription_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    st.download_button(
                        label="Download All Generated Content as .txt",
                        data=full_generated_text_for_download_str.encode("utf-8"),
                        file_name=download_filename,
                        mime="text/plain"
                    )

            elif all_extracted_text:
                st.warning("No medicine names could be extracted from the document text.")
            else: # No text extracted at all
                st.error("Could not extract any text from the uploaded document.")
        
    # Session History in Sidebar
    st.sidebar.header("Session History")
    sessions = load_sessions_from_db()
    if sessions:
        st.sidebar.info(f"Loaded {len(sessions)} previous sessions.")
        for session_row in sessions:
            with st.sidebar.expander(f"Session {session_row['id']} - {session_row['timestamp']} - {session_row['file_name']}"):
                st.write(f"**File Name:** {session_row['file_name']}")
                st.write(f"**Input Preview:**")
                st.text_area("Input Preview", session_row['input_content_preview'], height=100, disabled=True, key=f"input_{session_row['id']}")
                
                try:
                    original_meds = json.loads(session_row['extracted_medicines_json'])
                    st.write(f"**Original Extracted Medicines:** {', '.join(original_meds) if original_meds else 'None'}")
                except (json.JSONDecodeError, TypeError):
                    st.write(f"**Original Extracted Medicines:** [Error loading or not found]")
                
                try:
                    generated_data_list = json.loads(session_row['generated_details_json'])
                    st.write(f"**Processed Details ({len(generated_data_list)} items):**")
                    for med_data_dict in generated_data_list:
                        orig_name = med_data_dict.get('original_extracted_name', 'N/A')
                        queried_as = med_data_dict.get('original_query_name', orig_name)
                        display_name = f"{orig_name}"
                        if orig_name.lower() != queried_as.lower():
                            display_name += f" (as {queried_as})"
                        
                        st.markdown(f"- **{display_name}**: {med_data_dict.get('Medicine Name', 'Details N/A')}")
                        # Could add a button here to show full details for this past item
                except (json.JSONDecodeError, TypeError):
                    st.write(f"**Generated Details:** [Error loading or not found]")
    else:
        st.sidebar.info("No previous sessions found.")

if __name__ == "__main__":
    main()