**`README.md`**

```markdown
# Pharmacist Prescription Assistant with Gemini AI

This Streamlit application allows pharmacists to upload doctor's prescriptions (PDF or Image) to extract medicine names. It then uses Google's Gemini AI to:
1.  Translate any Bengali medicine names to English.
2.  Retrieve detailed information for each medicine, prioritizing the `medex.com.bd` website and then using general web search capabilities.
3.  Provide relevant web search highlights (titles, URLs, snippets) for further research.
4.  Offer fallback Google search queries if detailed information cannot be found.

All session data, including uploaded file information, extracted medicines, and AI-generated details, are saved in a local SQLite database (`prescription_sessions.db`). Generated content can also be downloaded as a `.txt` file.

## Features

*   **File Upload:** Supports PDF and common image formats (PNG, JPG, JPEG).
*   **Text Extraction:** Extracts text from PDFs (text-based and image-based via OCR) and images using Gemini AI.
*   **Medicine Name Extraction:** Identifies medicine names from the extracted text.
*   **Bengali to English Translation:** Translates medicine names detected in Bengali script to English for broader search compatibility.
*   **Comprehensive Medicine Details:** Retrieves 16 key details for each medicine:
    1.  Medicine Name
    2.  Medicine Manufacturer Name
    3.  Indications
    4.  Pharmacology
    5.  Dosage & Administration
    6.  Interaction
    7.  Contraindications
    8.  Side Effects
    9.  Pregnancy & Lactation
    10. Precautions & Warnings
    11. Use in Special Populations
    12. Overdose Effects
    13. Therapeutic Class
    14. Storage Conditions
    15. Chemical Structure (Molecular Formula)
    16. Primary Website URL (prioritizing medex.com.bd)
*   **Web Search Highlights:** Provides 2-3 relevant web search snippets for each medicine.
*   **Fallback Search Queries:** Suggests Google search queries if Gemini cannot find detailed information.
*   **Data Persistence:** Saves all session information (input, extracted medicines, generated details) in an SQLite database.
*   **Downloadable Reports:** Allows downloading of all generated content for a session in a `.txt` file.
*   **Session History:** View past sessions from the sidebar.

## Prerequisites

*   Python 3.8 or higher
*   pip (Python package installer)
*   A Google Gemini API Key

## Setup

1.  **Clone the repository (or save the code):**
    If you have this as a project, clone it. Otherwise, save the Python script (e.g., `app.py`).

2.  **Create a Virtual Environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    Navigate to the project directory and install the required packages:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure API Key:**
    Open the Python script (e.g., `app.py`) and replace the placeholder API key with your actual Google Gemini API Key:
    ```python
    API_KEY = "YOUR_GEMINI_API_KEY_HERE"
    ```
    **Note:** For production or shared environments, it's highly recommended to use environment variables or Streamlit secrets to manage your API key instead of hardcoding it.

## Running the Application

1.  Ensure your virtual environment is activated.
2.  Navigate to the directory containing `app.py` (or your script name).
3.  Run the Streamlit app from your terminal:
    ```bash
    streamlit run app.py
    ```
    (Replace `app.py` with the actual name of your Python file if different).
4.  The application will open in your default web browser.

## Database

*   The application will automatically create an SQLite database file named `prescription_sessions.db` in the same directory as the script if it doesn't already exist. This file stores all session data.

## Disclaimer

*   This application is intended for use by **professional pharmacists** as an aid and should not be used by individuals without medical training for self-diagnosis or treatment.
*   The information provided by Gemini AI is for informational purposes only. While efforts are made to prioritize `medex.com.bd` and provide accurate data, **all medical information should be critically verified from trusted, authoritative sources before making any clinical decisions.**
*   The AI's ability to interpret complex prescriptions, handwriting, or low-quality images may be limited.
*   The accuracy of translation and information retrieval depends on the AI model's capabilities and the clarity of the input.

## File Structure (Example)

```
.
├── app.py                      # Main Streamlit application script
├── requirements.txt            # Python dependencies
├── README.md                   # This file
└── prescription_sessions.db    # SQLite database (created on first run)
```
```

---

**`requirements.txt`**

```text
streamlit
google-generativeai
PyPDF2
Pillow
```

---

**Important Considerations for the `requirements.txt`:**

*   The versions are not pinned. This means `pip install -r requirements.txt` will install the latest compatible versions of these packages. For more reproducible builds, you would pin versions (e.g., `streamlit==1.28.0`). You can generate a pinned list from your working environment using `pip freeze > requirements.txt`.
*   The `re`, `sqlite3`, `json`, `datetime`, and `os` modules are part of Python's standard library and do not need to be listed in `requirements.txt`.

These files should provide a good starting point for anyone looking to understand, set up, and run your application.
