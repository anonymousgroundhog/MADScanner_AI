# MADScanner_AI
AI Based version of MADScanner

# Running the framework
First you must run `Inject_Code_Into_All_APK_Files.py` to get any file injected into the analyzed APK files. Files will be signed and output to Python/Soot_Output_Injector_APK_Files
cd
<!-- Next, run `Remove_Empty_Directory_in_sootOutput_Directory.py` for removing the empty directories.

Next, run `APK_Resigner.py` to cleanup the sootOutput directory and sign the APK files.

Next, run `File_Cleanup.py` to remove any files that contain no base.apk -->

Next, run `Clean_Directories.py` to remove all folders and files in the sootOutput and APK_Files_To_Analyze folders.

# Instrumenting and generating models
First, run `Instrument_APK_Files_In_Soot_Output_Injector_APK_Files_Directory.py` which will generate the logs.


# Blockchain

Install docker and virtualbox. Then run the following:
```shell
sudo docker run -p 8545:8545 trufflesuite/ganache
```

Compile the smart contract located under the folder smart_contract and deploy using remix IDE

In the `Web3.py` script under the `Python` folder. Note, be sure to change the contract address before running.
