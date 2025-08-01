#!/bin/bash

app=$1
rm -rf sootOutput
javac -cp "Jar_Libs/*" -d . Java/LogInjector.java

java -Xmx20g -cp ".:Jar_Libs/*" LogInjector "Android/platforms" "APK_Files_To_Analyze/$app"

zipalign -fv 4 sootOutput/$app sootOutput/signed$app
apksigner sign --ks my-release-key.keystore --ks-pass pass:password sootOutput/signed$app
rm sootOutput/signed$app.idsig
# COPY OVER FILES TO A OUTPUT DIRECTORY OTHER THAN THE sootOutput Folder
mkdir Soot_Output_Injector_APK_Files
cp sootOutput/signed$app Soot_Output_Injector_APK_Files
