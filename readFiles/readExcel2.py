import pandas as pd

# Load the data from both Excel files
institute_df = pd.read_excel("Institute.xlsx")
institute2_df = pd.read_excel("Institute2.xlsx")

# Iterate over each value in column H of Institute.xlsx
for index, value in institute_df['MPO Number'].items():
    # Search for the value in column A of Institute2.xlsx
    matched_row = institute2_df[institute2_df['MPO Number'] == value]
    
    if not matched_row.empty:
        # If a match is found, get the corresponding value from column B
        related_field = matched_row['EIIN'].values[0]
        related_field2 = matched_row['Level'].values[0]
        # Place the related value in column G of Institute.xlsx
        institute_df.at[index, 'EIIN'] = related_field
        institute_df.at[index, 'Level'] = related_field2

# Save the modified Institute.xlsx to a new file
institute_df.to_excel("Updated_Institute.xlsx", index=False)

print("Matching process completed. Data saved to Updated_Institute.xlsx.")
