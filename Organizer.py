import google.generativeai as genai
import os
from dotenv import load_dotenv
import pdfplumber
import json
import time
import re
import pickle

load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=google_api_key)
model = genai.GenerativeModel(model_name="gemini-2.0-flash-thinking-exp-01-21")
PDF_DIR = "/Downloads/every-vc-bill/pdfs"
PROGRESS_FILE = "bill_processing_progress.pkl"
JSON_DIR = "/Downloads/every-vc-bill/json_outputs"
os.makedirs(JSON_DIR, exist_ok=True)

def save_progress(processed_files):
    with open(PROGRESS_FILE, 'wb') as f:
        pickle.dump(processed_files, f)

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'rb') as f:
            return pickle.load(f)
    return set()

def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*]', ' ', filename)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    if not sanitized.strip():
        return "Untitled_Bill"
    return sanitized.strip()[:200]

def convert_filetext_to_dict(directory, path, processed_files):
    os.chdir(path)
    file_dict = {}
    processed = 0
    failed = 0
    for filename in directory:
        if filename in processed_files:
            continue
        try:
            text = ""
            with pdfplumber.open(filename) as pdf:
                for page in pdf.pages:
                    extracted_text = page.extract_text()
                    if extracted_text:
                        text += extracted_text + "\n"
            if text.strip():
                file_dict[filename] = text
                processed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Failed to process {filename}: {e}")
            failed += 1
    print(f"Processed {processed}. {failed} failed to process.")
    return file_dict
def get_llm_retitle(text, attempts):
    if attempts == 0:
        print("Failed to process file.")
        return None
    try:
        prompt = f"""You are a generative language model that is part of an agentic pipeline designed to analyze bills and amend the U.S. Code.
            Your job is to modify files into the appropriate type. You will be passed a file. You must output valid JSON, naming the file and providing a list of all sections of U.S. Code amended within the bill. Output only valid JSON. 
            You are to output JSON in this format:
            {{
                "title":"The title of the bill, as provided within the bill itself. Should include year. If there is a 'Short Title' section in the Act, use the citation provided by the Short Title. CRITICAL: **All titles should be formatted like "_____ Act of [year]**.",
                "author":"The author(s) of the bill.",
                "cosponsors":"the cosponsors of the bill.",
                "amendments":"A list of exactly which sections and titles of USC are amended. Format as follows: [[Section, Title], [Section, Title],...]. Include only the numbered sections amended. Use arrays with square brackets. If the bill also contains sections that change or make law but do NOT amend any U.S. code, also include a [None, section of the bill] in this field for each section of the bill that makes but does not amend law"
                "category":"COMM, DEFN, TRIBE, GOVT, ECON, ENRGY, EDU, SEC, FEMA, TRAN, HLTH, CRTS, ENVRN, AGRI, JUST, HOUS, TAX, MARIT, SCI for: commerce-trade-and-industry,defense-and-veterans-affairs,cultural-recreational-and-tribal-affairs,government-administration-and-oversight,economic-budgetary-and-financial-policy,energy-resources-and-policy,education-labor-and-workforce-development,international-affairs-and-national-security,emergency-prepardness-and-disaster-relief,transportation-and-infrastructure,healthcare-and-social-services,civil-rights-and-liberties,environmental-conservation-climate-and-natural-resources,agriculture-food-and-rural-development,public-safety-immigration-and-justice,housing-and-urban-development,taxation-and-revenue,maritime-and-oceanic-policy,science-technology-and-innovation, respectively."
            }}
            Do NOT include ```json or ``` markers in your response. Output only the raw JSON. I will be running whatever you output through json.loads(). Ensure your output does not trigger a JSON parsing error.
            IMPORTANT. Do NOT write your JSON in a markdown block. Output ONLY JSON that can be passed directly to 
            The text of the bill will be provided for you now: {text[:2000000]}.
            Remember that you are only to output valid JSON in the provided format."""
        response = model.generate_content([prompt])
        response_text = response.text.replace("```json", "").replace("```", "").lstrip()
        response_json = json.loads(response_text)

        return response_json
    except json.JSONDecodeError as e:
            print(f"JSON parsing error!")
            print(f"Response was: {response_text if 'response_text' in locals() else 'No response'}")
            print(f"Attempting again: {attempts-1} attempts remaining.")
            time.sleep(15)
            return get_llm_retitle(text + "On your last attempt, you returned invalid JSON. Make sure you ONLY return valid JSON - your JSON will be passed directly into json.loads().", attempts-1)
    except Exception as e:
            print(f"Failed to process: {e}")
            print(f"Attempting again: {attempts-1} attempts remaining.")
            time.sleep(15)
            return get_llm_retitle(text, attempts-1)
def clean_up_bill_dict(dictionary):
        processed_files = load_progress()
        for path, text in dictionary.items():
            respdict = get_llm_retitle(text, attempts = 5)
            if respdict:
                newtitle = sanitize_filename(respdict["title"])
                json_filename = os.path.join(JSON_DIR, f"{newtitle}.json")
                with open(json_filename, 'w') as f:
                    json.dump(respdict, f, indent=4)
                print(f"JSON data saved to {json_filename}")
                if path != newtitle:
                    os.chdir(PDF_DIR)
                    if os.path.exists(newtitle):
                        newtitle = f"{newtitle}_{int(time.time())}"
                    os.rename(path, newtitle + ".pdf")
                    print(f"File '{path}' renamed to '{newtitle}' successfully.")
                else:
                    print(f"File '{path}' already has correct name.")
                processed_files.add(path)
                save_progress(processed_files)
                time.sleep(15)
            else:
                print("Failed after maximum attempts.")

if __name__ == "__main__":
    processed_files = load_progress()
    directory = [f for f in os.listdir(PDF_DIR) if f not in processed_files]
    file_dict = convert_filetext_to_dict(directory, PDF_DIR, processed_files)
    clean_up_bill_dict(file_dict)
