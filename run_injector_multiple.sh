#!/bin/bash


# SETUP AND REMOVE UNECESSARY DIRECTORIES
rm -rf sootOutput
javac -cp "Jar_Libs/*" -d . Java/LogInjector.java


for item in APK_Files_To_Analyze/*
do
    # The 'basename' command extracts the filename from a full path.
    # We check if the item is a regular file using the -f flag.
    if [ -f "$item" ] && [ "$(basename "$item")" != "Info.md" ]; then
        echo "File: $(basename "$item")"
        java -Xmx20g -cp ".:Jar_Libs/*" LogInjector "Android/platforms" "$item"
    fi
done

# Iterate over all Files in sootOutput folder and align and zip and copy over to the output directory



# rm -rf sootOutput
# javac -cp "Jar_Libs/*" -d . Java/LogInjector.java

# java -Xmx20g -cp ".:Jar_Libs/*" LogInjector "Android/platforms" "APK_Files_To_Analyze/$app"

# zipalign -fv 4 sootOutput/$app sootOutput/signed$app
# apksigner sign --ks my-release-key.keystore --ks-pass pass:password sootOutput/signed$app
# rm sootOutput/signed$app.idsig
# # COPY OVER FILES TO A OUTPUT DIRECTORY OTHER THAN THE sootOutput Folder
# mkdir Soot_Output_Injector_APK_Files
# cp sootOutput/signed$app Soot_Output_Injector_APK_Files
