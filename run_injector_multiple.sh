#!/bin/bash


# SETUP AND REMOVE UNECESSARY DIRECTORIES
rm -rf sootOutput
javac -cp "Jar_Libs/*" -d . Java/LogInjector.java
mkdir Soot_Output_Injector_APK_Files

for item in APK_Files_To_Analyze/*
do
    # The 'basename' command extracts the filename from a full path.
    # We check if the item is a regular file using the -f flag.
    if [ -f "$item" ] && [ "$(basename "$item")" != "Info.md" ]; then
        echo "File: $(basename "$item")"
        java -Xmx20g -cp ".:Jar_Libs/*" LogInjector "Android/platforms" "$item"
    fi
done

# pwd
# Iterate over all Files in sootOutput folder and align and zip and copy over to the output directory
for item in sootOutput/*
do
    # The 'basename' command extracts the filename from a full path.
    # We check if the item is a regular file using the -f flag.
    if [ -f "$item" ] && [ "$(basename "$item")" != "Info.md" ]; then
        filename=$(basename "$item")
        echo "File: $filename signed$filename"
        zipalign -fv 4 sootOutput/$filename sootOutput/signed$filename
        apksigner sign --ks my-release-key.keystore --ks-pass pass:password sootOutput/signed$filename
        rm sootOutput/*.idsig
        # # # COPY OVER FILES TO A OUTPUT DIRECTORY OTHER THAN THE sootOutput Folder
        cp sootOutput/signed$filename Soot_Output_Injector_APK_Files
    fi
done

rm Soot_Output_Injector_APK_Files/*.idsig