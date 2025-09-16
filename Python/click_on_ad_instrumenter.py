import sys, time
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from ppadb.client import Client as AdbClient

# NOTE robust_click_on_elements and get_connected_device remain the same
def get_connected_device()
    """
    Connects to the ADB server and returns the name of the first connected device.
    Raises an error if no device is found.
    """
    try
        client = AdbClient(host="127.0.0.1", port=5037)
        devices = client.devices()

        if not devices
            raise RuntimeError("No ADB devices or emulators found. Please ensure one is running.")
        
        device_name = devices[0].serial
        print(f"Detected ADB device {device_name}")
        return device_name

    except ConnectionRefusedError
        raise RuntimeError("Could not connect to ADB server. Please start the server using 'adb start-server'.")
    except Exception as e
        raise RuntimeError(f"An error occurred while detecting ADB device {e}")

def robust_click_on_elements(driver, locator_strategy, locator_value, text_filter=None, max_attempts=5)
    """
    Finds and clicks on elements robustly, handling multiple pop-ups or dynamic changes.
    Returns True if an element was clicked, False otherwise.
    """
    did_click = False
    for attempt in range(max_attempts)
        try
            wait = WebDriverWait(driver, 5)
            elements = wait.until(EC.presence_of_all_elements_located((locator_strategy, locator_value)))

            for element in elements
                if element.is_displayed() and (text_filter is None or text_filter.lower() in element.text.lower())
                    element.click()
                    print(f"  -> Clicked '{element.text}' ({element.class_name})")
                    did_click = True
                    time.sleep(1)
                    break
            
            if not did_click
                break
        except (TimeoutException, NoSuchElementException)
            break
        except Exception as e
            print(f"An unexpected error occurred {e}")
            break
    
    return did_click

def main()
    if len(sys.argv) < 3
        print("Usage python script.py <app> <appActivity>")
        sys.exit(1)

    try
        device_name = get_connected_device()
    except RuntimeError as e
        print(f"Error {e}")
        sys.exit(1)

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = device_name
    options.app_ = sys.argv[1]
    options.app_activity = sys.argv[2]
    options.no_reset = True
    options.auto_grant_permissions = True
    options.adb_exec_timeout = 30000
    
    print("\nConnecting to Appium server...")
    try
        driver = webdriver.Remote("http//127.0.0.14723/wd/hub", options=options)
        print("Driver connected successfully. Waiting for app to load...")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//*[@displayed='true']")))
        print("App is ready.")

        # --- Handle Permissions (if any) ---
        print("\nAttempting to handle permissions...")
        if not robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "allow")
            print("  -> No 'Allow' buttons found.")

        # --- Click on the Ad and Navigate Back ---
        print("\nAttempting to click on ads...")
        try
            # We explicitly wait for the ad button.
            ad_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ACCESSIBILITY_ID, "OPEN"))
            )
            print("  -> Found ad button with Accessibility ID 'OPEN'. Clicking...")
            ad_button.click()
            
            # The page will change here. Wait for the new activity (browser) to open.
            time.sleep(5) 
            
            print("  -> Navigating back to the app...")
            driver.back()
            time.sleep(2) # Give the app time to reappear
            
            print("  -> Successfully returned to the app.")
            
        except (TimeoutException, NoSuchElementException)
            print("  -> No 'OPEN' ad button found on the screen.")
            
        # --- Check for lingering close buttons ---
        print("\nChecking for any remaining pop-ups or ads...")
        if not robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "close")
            print("  -> No 'close' buttons found.")

        # --- Swipe Screen ---
        print("\nSwiping the screen to test for dynamic ads...")
        driver.swipe(150, 800, 250, 200, 1000)
        time.sleep(2)

        # --- Final Check ---
        print("\nFinal check for any remaining ads...")
        if not robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "close")
            print("  -> No ads found after swipe.")

    finally
        print("\nTest finished. Quitting driver.")
        if 'driver' in locals()
            driver.quit()

if __name__ == "__main__"
    main()