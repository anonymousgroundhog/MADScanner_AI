import soot.*;
import soot.jimple.*;
import soot.options.Options;
import soot.util.Chain;

import java.util.Arrays;
import java.util.Map;

/**
 * A Soot transformer that injects Android Log.d calls at the beginning of each method.
 */
public class LogInjector {

    // Define a tag for the log messages
    private static final String LOG_TAG = "SootInjection";

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: java LogInjector <path-to-android-platforms> <path-to-apk>");
            System.exit(1);
        }

        String androidPlatforms = args[0]; // e.g., /path/to/android-sdk/platforms
        String apkPath = args[1];          // e.g., /path/to/your/app.apk
        System.out.println ("apkPATH:"+apkPath);
        // Initialize Soot
        setupSoot(androidPlatforms, apkPath);

        // Create and add the transformer to the Jimple Body Transformation pack (jtp)
        PackManager.v().getPack("jtp").add(new Transform("jtp.LogInjectorTransform", new BodyTransformer() {
            @Override
            protected void internalTransform(Body body, String phaseName, Map<String, String> options) {
                injectLog(body);
            }
        }));

        // Run Soot's main analysis/transformation phase
        // The main method arguments are passed to Soot
        soot.Main.main(new String[]{
                "-process-dir", apkPath // Specify the APK to process
        });

        System.out.println("Log injection complete. Output APK is in sootOutput/");
    }

/**
     * Configures Soot for Android APK processing.
     *
     * @param androidPlatforms Path to the Android platforms directory in the SDK.
     * @param apkPath          Path to the input APK file.
     */
    private static void setupSoot(String androidPlatforms, String apkPath) {
        // Reset Soot settings (important for running Soot multiple times in a single JVM instance)
        G.reset();

        // Set Soot options for Android processing
        Options.v().set_allow_phantom_refs(true); // Allow unresolved classes/methods, prevents crashes from missing dependencies
        Options.v().set_prepend_classpath(true);  // Prepend the default classpath, useful for resolving core Java classes
        Options.v().set_validate(false);           // Disable Jimple body validation (can sometimes cause issues with complex transformations)
        Options.v().set_process_multiple_dex(true); // Enable processing of multi-dex APKs
        Options.v().set_num_threads(1ex);             // Limit Soot to a single thread for stability and lower memory spikes

        // Specify the input format as APK
        Options.v().set_src_prec(Options.src_prec_apk);

        // Specify the output format as Dalvik bytecode (dex)
        Options.v().set_output_format(Options.output_format_dex);

        // Set the Android platforms directory (required for resolving Android framework classes like android.util.Log)
        Options.v().set_android_jars(androidPlatforms);

        // Specify the input APK file for processing
        java.util.List<String> processDirList = new java.util.ArrayList<>();
        processDirList.add(apkPath);
        Options.v().set_process_dir(processDirList);

        // These options are crucial for handling complex APKs and internal typing errors.
        Options.v().set_full_resolver(true); // Attempts a more comprehensive and robust type resolution
        Options.v().set_no_bodies_for_excluded(true); // Prevents building Jimple bodies for classes excluded from analysis, saving memory and avoiding issues in those bodies.
        // Options.v().set_allow_jimple_construction(true); // <--- THIS LINE IS NOW COMMENTED OUT
        // This option might not exist in older Soot versions or its functionality might be handled differently.
        // If you encounter 'cannot find symbol' for this line, keep it commented out.
        // Update Soot to a recent version to potentially gain access to or automatically handle this functionality.

        // --- IMPORTANT: Uncomment and adjust this line AFTER updating your Soot JARs ---
        // This explicitly tells Soot the target Android API level. A mismatch here is a common
        // cause of type resolution issues during Dex printing.
        // Try a common recent API level like 30 or 31 if unsure.
        // E.g., Options.v().set_android_targets_api_level(30);
        // E.g., Options.v().set_android_targets_api_level(31);
        // The error you got ("cannot find symbol") means your current Soot version doesn't
        // have this method. Update Soot, then uncomment this line.
        // Options.v().set_android_targets_api_level(34); // Keep this line commented until Soot is updated

        // Optional: If issues still persist, consider this. It tells Soot to ignore some
        // resolution errors, but can potentially hide real problems. Use with caution.
        // Options.v().set_ignore_resolution_errors(true);

        // Set the output directory for the instrumented APK
        Options.v().set_output_dir("sootOutput");

        // Load necessary classes from the classpath and Android JARs.
        // This step is critical for Soot to understand the structure of the application.
        Scene.v().loadNecessaryClasses();
    }
    /**
     * Injects a Log.d call at the beginning of the given method body.
     *
     * @param body The JimpleBody of the method to instrument.
     */
    private static void injectLog(Body body) {
        SootMethod method = body.getMethod();
        JimpleBody jimpleBody = (JimpleBody) body;
        Chain<Unit> units = jimpleBody.getUnits();

        // Get the signature of the method being instrumented
        String methodSignature = method.getSignature();

        // Create the constant strings for Log.d(TAG, message)
        StringConstant tagConstant = StringConstant.v(LOG_TAG);
        StringConstant msgConstant = StringConstant.v("Entering method: " + methodSignature);

        // Find the Log class and the 'd' method
        SootClass logClass = Scene.v().getSootClass("android.util.Log");
        // Signature: static int d(java.lang.String, java.lang.String)
        SootMethod logMethod = logClass.getMethod("int d(java.lang.String,java.lang.String)");

        // Create the static method invocation statement: Log.d(TAG, message)
        StaticInvokeExpr logInvokeExpr = Jimple.v().newStaticInvokeExpr(
                logMethod.makeRef(), // Reference to the Log.d method
                tagConstant,         // First argument: TAG
                msgConstant          // Second argument: Message
        );

        // Create a statement (Unit) from the invocation expression
        // We need an InvokeStmt because Log.d returns an int, which we ignore.
        Stmt logStmt = Jimple.v().newInvokeStmt(logInvokeExpr);

        // Insert the logging statement at the very beginning of the method body
        // Find the first non-identity statement to insert after any parameter assignments
        Unit insertionPoint = null;
        for (Unit u : units) {
            if (!(u instanceof IdentityStmt)) {
                insertionPoint = u;
                break;
            }
        }

        // If no non-identity statement is found (e.g., empty method), insert at the beginning
        if (insertionPoint == null) {
             // Check if the method is abstract or native, skip if so
             if (method.isAbstract() || method.isNative()) {
                System.out.println("Skipping abstract/native method: " + methodSignature);
                return;
             }
             // If it's an empty concrete method, we might still want to log entry
             // Handle potential edge cases or decide to skip entirely
             System.out.println("Warning: Method " + methodSignature + " has no non-identity statements. Inserting log at the beginning.");
             // Insert at the very beginning if needed, though this might be unusual for empty methods
             units.addFirst(logStmt);

        } else {
             // Insert the log statement *before* the first actual instruction

             units.insertBefore(logStmt, insertionPoint);
        }
    }
}
