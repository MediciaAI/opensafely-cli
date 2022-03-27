import pandas
import hashlib
from numpy.random import uniform
from numpy import array

def inspect_pat_ID(data_file_path):
    data = pandas.read_csv(data_file_path, index_col=False)

    # Select some rows randomly for patient ID inspection.    
    random_rows = array(uniform(0, data.shape[0], 5), dtype=int)

    # This list has length equal to the number of random rows. Its value is True when the corresponding row has a patient ID.
    result = []
    
    # This list holds the names of all columns detected with patient ID.
    detected_columns_names = []
    for row_idx in random_rows:
        pat_id_found = False
        # A temporary list to hold the columns names in the current row where the patient ID exists.
        curr_columns_names = []
        for col_name in data.columns:
            curr_col_val = data.loc[row_idx, col_name]
            if type(curr_col_val) is str:
                # The patient ID data type in the databse is CHAR(50). When the ID length is less than 50 characters, it is filled by spaces at the end.
                # The strip() method is called to remove ant spaces at the beginning and end of the ID.
                curr_col_val = curr_col_val.strip()
                if curr_col_val.isalnum():
                    if len(curr_col_val) > 2:
                        pat_id_length = curr_col_val[:2]
                        if pat_id_length.isdecimal(): # 03123
                            pat_id_length = int(curr_col_val[:2])
                            if len(curr_col_val) > (2 + pat_id_length):
                                pat_id = curr_col_val[2:2+pat_id_length]
                                hash_code = hashlib.md5(pat_id.encode()).hexdigest()
                                hash_summary = hash_code[0] + hash_code[16] + hash_code[-1]
                                if hash_summary == curr_col_val[2+pat_id_length:]:
                                    # print("The value {curr_col_val} at the column named {col_name} of the row with index {row_idx} represents a patient ID.".format(curr_col_val=curr_col_val, col_name=col_name, row_idx=row_idx))
                                    pat_id_found = True
                                    curr_columns_names.append(col_name)

        result.append(pat_id_found)

        # It is expected to have dubplicate columns names stored in this list.
        detected_columns_names.append(curr_columns_names)

    # This is the list of unique columns names.
    unique_columns_names = list(set([column_name for curr_columns_names in detected_columns_names for column_name in curr_columns_names]))

    return any(result), detected_columns_names, unique_columns_names

def hash_columns(data_file_path, columns_names, seed):
    data = pandas.read_csv(data_file_path, index_col=False)

    for column_name in columns_names:
        data[column_name] = data[column_name].apply(lambda pat_ID_str: hashlib.md5(str(pat_ID_str.strip() + seed).encode()).hexdigest())

    return data

if __name__ == "__main__":
    # data_file_path = "C:\\Users\\agad069\\Anaconda3\\Lib\\site-packages\\workdir\\high_privacy\\workspaces\\test\\output\\input.csv"
    data_file_path = "$HOME/job-runner/jobrunner/workdir/high_privacy/workspaces/test/output/input.csv"
    # data_file_path = "patdemographics_hashed.csv"

    result, detected_columns_names, unique_columns_names = inspect_pat_ID(data_file_path=data_file_path)
    if result:
        print("The output data file {file} contains patient ID which is not allowed.".format(file=data_file_path))
        data = hash_columns(data_file_path=data_file_path, columns_names=unique_columns_names)
        print(data[detected_columns_names[0]])
    else:
        print("No patient ID found in the file {file}".format(file=data_file_path))
