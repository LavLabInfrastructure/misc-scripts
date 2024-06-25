#!/bin/bash
read -p "How many patients do you want to process? " ptNum

while ! [[ "$ptNum" =~ ^[0-9]+$ ]]; do
    echo "Invalid input. Please enter a whole number."
    read -p "How many patients do you want to process? " ptNum
done

for ((i = 0; i < ptNum; i++)); do

    read -p "Enter a 3-digit ID (###): " code

    while [[ ! $code =~ ^[0-9]{3}$ ]]; do
        echo "Invalid code format. Please enter a 3-digit code."
        read -p "Enter a 3-digit code (###): " code
    done

    dir1="/Volumes/Medusa/Prostate_data"
    dir2="/Volumes/Siren/Prostate_Data"

    if mkdir -p "$dir1/$code/MRI/"; then
        echo "Directory '$dir1/$code/MRI' created successfully."
        rawdir="/Volumes/Medusa/Prostate_Data/$code/MRI"
    else
        echo "Failed to create directory."
    fi

    if mkdir -p "$dir2/$code/MRI/Processed"; then
        echo "Directory '$dir2/$code/MRI/Processed' created successfully." 
        procdir="/Volumes/Siren/Prostate_data/${code}/MRI/Processed"   
    else
        echo "Failed to create directory."
    fi

    read -p "Enter the patient's MRI code: " MRIcode
    while [[ ! $MRIcode =~ ^[0-9]{6}[a-zA-Z]{2}$ ]]; do
        echo "Invalid MRI code format. Please enter a 6-digit code followed by 2 letters (e.g., 230113mh)"
        read -p "Enter the patient's MRI code: " MRIcode
    done

        read -p "Enter your RCC username " user

        scp -r "$user@login-hpc.rcc.mcw.edu:/group/plaviole/work/Prostate_Raw/$MRIcode" $rawdir  

        if [ -d $rawdir/$MRIcode ]; then
            echo "The files were moved over sucessfully."
        fi
   
    cd "$rawdir/$MRIcode/Mr_Pelvis/"
    ls -l
    read -rp "Choose the dicom directory that you would like to process: " selected_directory
    T2="$rawdir/$MRIcode/Mr_Pelvis/$selected_directory"

    dcm2niix -b n -f %f -z y -o $procdir $T2
    
    cd $procdir

    find "$procdir" -type f -name '*_ROI*' -print
    read -p "Proceed with deletion? (y/n): " confirm_delete

    if [[ $confirm_delete == [yY] || $confirm_delete == [yY][eE][sS] ]]; then
        find "$procdir" -type f -name '*_ROI*' -exec rm -f {} +
        echo "Deleted files containing '_ROI'."
    else
        echo "Deletion canceled."
    fi

    echo "Files to be renamed (containing 'T2'):"
    find "$procdir" -type f -name '*T2*' -print
    read -p "Proceed with renaming? (y/n): " confirm_rename

    if [[ $confirm_rename == [yY] || $confirm_rename == [yY][eE][sS] ]]; then
        find "$procdir" -type f -name '*T2*' -exec sh -c '
            for file do
                echo "Renaming: $file"
                mv "$file" "T2.nii.gz"
            done
        ' sh {} +
        echo "Renamed files containing 'T2' to 'T2.nii.gz'."
    else
        echo "Renaming canceled."
    fi

    while true; do
        read -p "Are you ready to continue? (yes/no): " ready

        if [[ "$ready" =~ ^[Yy][Ee][Ss]|[Yy]$ ]]; then
            if [ ! -d "$procdir" ]; then
            echo "Directory '$procdir' does not exist."
            continue
            fi

            cd "$procdir" || {
                echo "Error: Could not change to directory '$procdir'."
                continue
            }

            3dcalc -a T2.nii.gz -expr 'a*0' -prefix prostate_mask.nii.gz

            if [ $? -ne 0 ]; then
                echo "Error running 3dcalc command."
                continue
            fi
            break
        fi
    done
done
