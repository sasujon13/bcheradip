import os
import pandas as pd

# Function to extract data from merged cells based on new lines
def split_merged_cell_data(data):
    if isinstance(data, float) or pd.isnull(data):
        return {
            "MPO_CODE": None,
            "EIIN": None,
            "Level_of_MPO": None,
            "Institution_Name": None,
            "Institution_District": None,
            "Institution_Thana": None
        }
    
    # Split the text data based on new lines
    lines = data.split("\n")
    
    # Initialize a dictionary to store the extracted fields
    extracted_data = {
        "MPO_CODE": None,
        "EIIN": None,
        "Level_of_MPO": None,
        "Institution_Name": None,
        "Institution_District": None,
        "Institution_Thana": None
    }
    
    # Process each line and extract relevant parts
    for line in lines:
        line = line.strip()  # Remove extra spaces around the line
        
        # Check for each specific field and assign values accordingly
        if "MPO CODE" in line:
            extracted_data["MPO_CODE"] = line.split(":")[1].strip()
        elif "EIIN" in line:
            extracted_data["EIIN"] = line.split(":")[1].strip()
        elif "Level of MPO" in line:
            extracted_data["Level_of_MPO"] = line.split(":")[1].strip()
        elif "INSTITUTION'S NAME" in line:
            extracted_data["Institution_Name"] = line.split(":")[1].strip()
        elif "INSTITUTION'S DISTRICT" in line:
            extracted_data["Institution_District"] = line.split(":")[1].strip()
        elif "INSTITUTION'S THANA" in line:
            extracted_data["Institution_Thana"] = line.split(":")[1].strip()
    
    return extracted_data

# Function to find the merged data in the first 4 rows
def find_merged_data(df):
    # Loop through the first 4 rows and check for "MPO CODE"
    for i in range(4):
        if i < len(df) and isinstance(df.iloc[i, 0], str) and "MPO CODE" in df.iloc[i, 0]:
            return df.iloc[i, 0]
    
    # If no valid row is found, return None
    return None

# Function to process each Excel file and extract the first row from all sheets
def process_excel_file(file_path):
    first_rows = []
    
    # Load the Excel file
    xls = pd.ExcelFile(file_path)
    
    # Loop through each sheet
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        
        # Find the merged data in the first 4 rows
        merged_data = find_merged_data(df)
        
        if merged_data:
            # Extract the data from the merged cell
            extracted_data = split_merged_cell_data(merged_data)
            # Add the extracted data to the list of first rows
            first_rows.append(extracted_data)
        else:
            print(f"No 'MPO CODE': {sheet_name} in {file_path}")
    
    return first_rows

# Function to process all Excel files in a folder
def process_all_files_in_folder(folder_path, output_file):
    all_extracted_data = []
    
    # Loop through all files in the folder
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".xlsx"):
            file_path = os.path.join(folder_path, file_name)
            print(f"Processing file: {file_path}")
            
            # Process each Excel file and extract the data
            extracted_data = process_excel_file(file_path)
            all_extracted_data.extend(extracted_data)
    
    # If there is any data extracted, write to an Excel file
    if all_extracted_data:
        # Create a DataFrame with all the extracted data
        output_df = pd.DataFrame(all_extracted_data)
        
        # Write the DataFrame to a new Excel file
        output_df.to_excel(output_file, index=False)
        print(f"Data written to: {output_file}")
    else:
        print("No data extracted from any file.")

# Specify the folder path and output file name
folder_path = r"G:\My Drive\Cheradip Database\Janata"
output_file = "Institute.xlsx"

# Run the processing function
process_all_files_in_folder(folder_path, output_file)
