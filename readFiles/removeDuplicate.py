import pandas as pd

# Load the data from the Excel file
institute_df = pd.read_excel("Institute3.xlsx")

# Remove duplicates based on conditions
# Step 1: Create a boolean mask to identify duplicates in column 'A' (assuming 'MPO Number' is in column A)
duplicates = institute_df[institute_df.duplicated(subset=['EIIN'], keep=False)]

# Step 2: Iterate over each duplicate group and remove based on the condition in column 'G'
for mpo_number, group in duplicates.groupby('EIIN'):
    # Step 3: If column 'G' is blank, mark it for removal
    blank_rows = group[group['Name Of Institute'].isna() | (group['Name Of Institute'] == '')]
    
    if not blank_rows.empty:
        # Remove rows with blank 'Level' (column G)
        institute_df = institute_df.drop(blank_rows.index)
        group = group.drop(blank_rows.index)  # Update group after removal

    if len(group) > 1:
        # Step 4: Check if 'Level' in column G ends with 'School', 'College', 'Coll.', or 'Col.'
        school_rows = group[group['Name Of Institute'].str.endswith(('School','Bidyalaya'), na=False)]
        college_rows = group[group['Name Of Institute'].str.endswith(('College', 'Coll.', 'Col.','(Coll)','(Col.)', 'Col', 'Coll'), na=False)]
        
        # If both school and college exist, remove the school row
        if not school_rows.empty and not college_rows.empty:
            institute_df = institute_df.drop(school_rows.index)

# Save the modified data back to a new Excel file
institute_df.to_excel("Updated_Institute3.xlsx", index=False)

print("Duplicates removal process completed!")
