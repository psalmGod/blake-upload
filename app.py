from flask import Flask, request, render_template
import pandas as pd
import requests
import os
import math

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Replace with your actual API key
TWENTY_CRM_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NmMzOTUyNC02YjE0LTQ4NWMtODdmNi0wYmM2YjU2MzlkODgiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiNjZjMzk1MjQtNmIxNC00ODVjLTg3ZjYtMGJjNmI1NjM5ZDg4IiwiaWF0IjoxNzM3MzMzOTYzLCJleHAiOjQ4OTA5MzM5NjIsImp0aSI6IjZjNTRmNGEyLWEyYjctNDNlNy1hOTI5LTNmZWVmMTY0ZGM0MCJ9.uLImnRd00mPmdlKPoAGLmQNFwuyHiNdykRYetdRV580"

TWENTY_CRM_ENDPOINT = "https://api.twenty.com/rest/people"
HEADERS = {
    "Authorization": f"Bearer {TWENTY_CRM_API_KEY}",
    "Content-Type": "application/json",
}

@app.route('/')
def home():
    return '''
    <h1>Twenty CRM Spreadsheet Loader</h1>
    <form action="/upload" method="POST" enctype="multipart/form-data">
        <label for="file">Upload Spreadsheet:</label>
        <input type="file" name="file" accept=".xls,.xlsx" required>
        <button type="submit">Upload</button>
    </form>
    '''

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return "No file uploaded.", 400

    file = request.files['file']
    if not (file.filename.endswith('.xls') or file.filename.endswith('.xlsx')):
        return "Invalid file type. Please upload an Excel file.", 400

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    try:
        sheets = pd.ExcelFile(filepath).sheet_names
    except Exception as e:
        return f"Error reading file: {str(e)}", 500

    return render_template('select_sheet.html', sheets=sheets, filename=file.filename)

@app.route('/select-sheet', methods=['POST'])
def select_sheet():
    filename = request.form['filename']
    selected_sheet = request.form['sheet']

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        df = pd.read_excel(filepath, sheet_name=selected_sheet)
    except Exception as e:
        return f"Error loading sheet: {str(e)}", 500

    columns = list(df.columns)
    return render_template('map_columns.html', columns=columns, filename=filename, sheet=selected_sheet)

@app.route('/map-columns', methods=['POST'])
def map_columns():
    filename = request.form['filename']
    sheet = request.form['sheet']

    # Column mappings from the user
    column_mappings = {
        "First Name": request.form.get('first_name_column'),
        "Last Name": request.form.get('last_name_column'),
        "Email": request.form.get('email_column'),
        "City": request.form.get('city_column'),
        "Location": request.form.get('location_column'),
        "Company": request.form.get('company_column'),
        "Job Title": request.form.get('job_title_column'),
        "Phone Number": request.form.get('phone_number_column'),
    }

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        # Load the selected sheet into a DataFrame
        df = pd.read_excel(filepath, sheet_name=sheet)

        # Replace NaN values with empty strings
        df = df.fillna("")

    except Exception as e:
        return f"Error loading sheet: {str(e)}", 500

    # Prepare the data for Twenty CRM
    people_data = []
    for _, row in df.iterrows():
        # Extract first name and last name from the "Name" column
        full_name = row.get(column_mappings["First Name"], "")
        first_name = full_name.split()[0] if isinstance(full_name, str) and full_name else ""
        last_name = " ".join(full_name.split()[1:]) if isinstance(full_name, str) and len(full_name.split()) > 1 else ""

        person = {
            "name": {"firstName": first_name, "lastName": last_name},
            "emails": {"primaryEmail": row.get(column_mappings["Email"], "")},
            "jobTitle": row.get(column_mappings["Job Title"], ""),
            "city": row.get(column_mappings["City"], ""),
            "addresses": row.get(column_mappings["Location"]),
            "workplaces": row.get(column_mappings["Company"]),
            "firstName": {"firstName": first_name, "lastName": ""},
            "lastName": {"firstName": "", "lastName": last_name},
            "phones": {"primaryPhoneNumber": row.get(column_mappings["Phone Number"], "")},
            #"customFields": {"address": row.get(column_mappings["Location"], ""),"workplace": row.get(column_mappings["Company"], ""),},
        }

        # Remove empty or null fields
        person = {k: v for k, v in person.items() if v}
        person["emails"] = {k: v for k, v in person["emails"].items() if v}

        people_data.append(person)

    # Send data to Twenty CRM in batches of 2000
    batch_size = 2000
    num_batches = math.ceil(len(people_data) / batch_size)
    successful_uploads = 0
    duplicate_emails = []

    for i in range(num_batches):
        batch = people_data[i * batch_size:(i + 1) * batch_size]
        for person in batch:
            try:
                response = requests.post(TWENTY_CRM_ENDPOINT, headers=HEADERS, json=person)
                if response.status_code == 400 and "Duplicate Emails" in response.text:
                    duplicate_emails.append(person["emails"]["primaryEmail"])
                    print(f"Duplicate email skipped: {person['emails']['primaryEmail']}")
                    continue  # Skip duplicate emails
                response.raise_for_status()  # Raise an exception for HTTP errors
                successful_uploads += 1
            except requests.exceptions.RequestException as e:
                print(f"Failed to upload person: {person}. Error: {response.text}")

    return f"Successfully uploaded {successful_uploads} records to Twenty CRM. Skipped {len(duplicate_emails)} duplicate emails."

if __name__ == '__main__':
    app.run(debug=False)
