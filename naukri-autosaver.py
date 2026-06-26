#!/usr/bin/env python3

import os
import time
import random
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import shutil
import subprocess
import re
import platform
# Note: use undetected_chromedriver.Chrome directly to avoid mixing
# webdriver-manager + selenium webdriver APIs which can cause type errors

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ========================= CONFIGURATION =========================
EMAIL = os.getenv("NAUKRI_EMAIL")
PASSWORD = os.getenv("NAUKRI_PASSWORD")

if not EMAIL or not PASSWORD:
    raise ValueError("NAUKRI_EMAIL or NAUKRI_PASSWORD environment variables are not set. Please set them in a .env file or environment.")

PROFILE_URL = "https://www.naukri.com/mnjuser/profile"

RUN_DURATION = os.getenv("RUN_DURATION", "").strip()
if RUN_DURATION:
    try:
        RUN_DURATION = int(RUN_DURATION)
        if RUN_DURATION <= 0:
            raise ValueError
    except ValueError:
        raise ValueError("RUN_DURATION must be a positive integer number of minutes.")
else:
    RUN_DURATION = 0

# Fast Interval: 10 seconds (Matches manual speed)
INTERVAL = 1

# Maximum consecutive failures before full restart
MAX_FAILURES = 5
# ================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("naukri_autosaver.log"),
        logging.StreamHandler()
    ]
)

def get_driver():
    logging.info("Starting browser (undetected-mode)...")
    options = Options()
    # Use new headless mode where supported
    options.add_argument("--headless=new")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    # Speed / privacy optimizations to reduce startup time
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-plugins-discovery')
    options.add_argument('--disable-default-apps')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    # Try to return control earlier (after DOMContentLoaded) to speed navigation
    try:
        options.page_load_strategy = 'eager'
    except Exception:
        pass
    
    def detect_chrome_major_version():
        # Allow overrides via environment
        env_version = os.getenv('CHROME_VERSION')
        env_path = os.getenv('CHROME_PATH')
        if env_version:
            try:
                return int(env_version.split('.')[0])
            except Exception:
                logging.warning('Invalid CHROME_VERSION env var; ignoring.')
        if env_path:
            if os.path.exists(env_path):
                try:
                    out = subprocess.check_output([env_path, '--version'], stderr=subprocess.STDOUT, text=True)
                    m = re.search(r"(\d+)\.", out)
                    if m:
                        return int(m.group(1))
                except Exception:
                    logging.warning('CHROME_PATH provided but version probe failed.')
        # Try to find chrome executable and read its version
        exe_candidates = []
        system = platform.system()
        if system == 'Windows':
            program_files = os.environ.get('PROGRAMFILES', r"C:\Program Files")
            program_files_x86 = os.environ.get('PROGRAMFILES(X86)', r"C:\Program Files (x86)")
            local_app = os.environ.get('LOCALAPPDATA', r"C:\Users\%USERNAME%\AppData\Local")
            exe_candidates += [
                os.path.join(program_files, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(program_files_x86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(local_app, 'Google', 'Chrome', 'Application', 'chrome.exe'),
            ]
            # also try PATH
            which = shutil.which('chrome') or shutil.which('chrome.exe')
            if which:
                exe_candidates.insert(0, which)
        else:
            which = shutil.which('google-chrome') or shutil.which('chrome') or shutil.which('chromium')
            if which:
                exe_candidates.append(which)

        for exe in exe_candidates:
            try:
                if not exe or not os.path.exists(exe):
                    continue
                out = subprocess.check_output([exe, '--version'], stderr=subprocess.STDOUT, text=True)
                m = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", out)
                if m:
                    return int(m.group(1))
                m2 = re.search(r"(\d+)\.", out)
                if m2:
                    return int(m2.group(1))
            except Exception:
                continue
        return None

    # Also detect chrome executable path for options if available
    def detect_chrome_executable():
        # honor CHROME_PATH override
        env_path = os.getenv('CHROME_PATH')
        if env_path and os.path.exists(env_path):
            return env_path
        system = platform.system()
        if system == 'Windows':
            candidates = [
                os.path.join(os.environ.get('PROGRAMFILES', r"C:\Program Files"), 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', r"C:\Program Files (x86)"), 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(os.environ.get('LOCALAPPDATA', r"C:\Users\%USERNAME%\AppData\Local"), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            ]
            which = shutil.which('chrome') or shutil.which('chrome.exe')
            if which:
                candidates.insert(0, which)
        else:
            candidates = [shutil.which('google-chrome') or shutil.which('chrome') or shutil.which('chromium')]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    version_main = detect_chrome_major_version()
    if version_main:
        logging.info(f"Detected Chrome major version: {version_main}")
    else:
        logging.warning("Could not detect local Chrome version; webdriver_manager will attempt to match the driver.")

    # If we found a chrome executable, feed it to options so webdriver_manager can match
    chrome_exe = detect_chrome_executable()
    if chrome_exe:
        logging.info(f"Using Chrome executable: {chrome_exe}")
        options.binary_location = chrome_exe
    # Allow reusing a profile to avoid repeated sign-ins and speed up start
    profile_dir = os.getenv('CHROME_PROFILE_DIR')
    if profile_dir and os.path.exists(profile_dir):
        logging.info(f"Using Chrome profile dir: {profile_dir}")
        options.add_argument(f"--user-data-dir={profile_dir}")

    try:
        # Let webdriver_manager download the matching chromedriver for the detected browser
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        # sensible timeouts
        try:
            driver.set_page_load_timeout(60)
        except Exception:
            pass
        try:
            driver.implicitly_wait(3)
        except Exception:
            pass
        return driver
    except Exception as e:
        logging.exception("Could not start browser")
        raise



def login(driver):
    # Go DIRECTLY to the login page for better reliability
    logging.info("Navigating to login page...")
    try:
        logging.info(f"Before navigate, current_url={getattr(driver,'current_url',None)}")
    except Exception:
        pass
    try:
        driver.get("https://www.naukri.com/nlogin/login")
    except Exception as e:
        logging.warning(f"driver.get() raised: {e}")

    wait = WebDriverWait(driver, 20)
    
    logging.info("Entering credentials...")
    
    def find_email_field():
        candidates = [
            (By.ID, 'usernameField'),
            (By.NAME, 'email'),
            (By.NAME, 'username'),
            (By.XPATH, "//input[@type='email']"),
            (By.CSS_SELECTOR, "input[type='email']"),
        ]
        for loc in candidates:
            try:
                el = wait.until(EC.presence_of_element_located(loc))
                return el
            except Exception:
                continue
        return None

    def find_password_field():
        candidates = [
            (By.ID, 'passwordField'),
            (By.NAME, 'password'),
            (By.XPATH, "//input[@type='password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]
        for loc in candidates:
            try:
                el = driver.find_element(*loc)
                return el
            except Exception:
                continue
        return None

    try:
        email_field = find_email_field()
        if not email_field:
            logging.error('Could not find email input on login page')
            raise RuntimeError('Email input not found')
        email_field.clear()
        email_field.send_keys(EMAIL)

        password_field = find_password_field()
        if not password_field:
            logging.error('Could not find password input on login page')
            raise RuntimeError('Password input not found')
        password_field.clear()
        password_field.send_keys(PASSWORD)

        # Click login button - try multiple selectors
        clicked = False
        btn_selectors = [
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[contains(., 'Login') or contains(., 'Log in') or contains(., 'Sign in')]")
        ]
        for sel in btn_selectors:
            try:
                btn = driver.find_element(*sel)
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            logging.warning('Login button not found; attempting to submit via Enter key')
            try:
                email_field.send_keys('\n')
            except Exception:
                pass

        # Wait for either profile URL or profile link
        logging.info("Waiting for dashboard to load...")
        try:
            wait.until(lambda d: 'mnjuser' in d.current_url or len(d.find_elements(By.XPATH, "//a[contains(@href,'mnjuser') or contains(@href,'/profile')]") )>0)
        except Exception:
            # not guaranteed; continue to check
            pass

        logging.info("Login step complete, current_url=%s" % getattr(driver, 'current_url', 'unknown'))
        time.sleep(2)

    except Exception as e:
        # dump diagnostics
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        try:
            screenshot = f'diag_login_{ts}.png'
            driver.save_screenshot(screenshot)
            logging.info(f'Saved screenshot: {screenshot}')
        except Exception:
            pass
        try:
            htmlfile = f'diag_login_{ts}.html'
            with open(htmlfile, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logging.info(f'Saved page source: {htmlfile}')
        except Exception:
            pass
        logging.error(f"Login failed: {e}")
        raise



def click_key_skills_and_save(driver):
    # Stay on the page if already there to increase speed
    if "mnjuser/profile" not in driver.current_url:
        logging.info("Navigating to profile page...")
        driver.get(PROFILE_URL)
        time.sleep(2)
        
    wait = WebDriverWait(driver, 10)
    
    # Quick scroll
    driver.execute_script("window.scrollTo(0, 600);")
    time.sleep(1)
    
    # Find and Open Popup
    edit_xpath = "//*[contains(text(),'Key Skills')]/ancestor::div[contains(@class,'section')]//span[contains(@class,'edit')] | //div[contains(@class,'keySkills')]//span[contains(@class,'edit')] | //div[contains(@class, 'key-skills')]//span[contains(@class, 'edit')]"
    key_skills_edit = wait.until(EC.presence_of_element_located((By.XPATH, edit_xpath)))
    
    # Ensure it's in view
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", key_skills_edit)
    time.sleep(1)
    
    # Fast JS Click
    driver.execute_script("arguments[0].click();", key_skills_edit)
    
    # Wait for popup to settle
    time.sleep(5)
    
    # ALL-BUTTON SCAN: Find every button on the page and click the one that says Save or Update
    logging.info("Scanning for Save button...")
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        clicked = False
        for btn in buttons:
            btn_text = btn.text.lower()
            if "save" in btn_text or "update" in btn_text:
                logging.info(f"Found button: '{btn.text}'. Clicking now...")
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                break
        
        if clicked:
            logging.info(f"[{datetime.now().strftime('%H:%M:%S')}] Key Skills Saved Successfully")
        else:
            logging.warning("Could not find any button labeled 'Save' or 'Update'.")
            driver.get(PROFILE_URL)
            
    except Exception as e:
        logging.error(f"Save scan failed: {e}")
        driver.get(PROFILE_URL)
        raise


def main():
    failures = 0
    start_time = time.time()
    driver = None
    while True:
        if RUN_DURATION and time.time() - start_time >= RUN_DURATION * 60:
            logging.info(f"Run duration reached ({RUN_DURATION} minutes). Exiting cleanly.")
            return

        try:
            driver = get_driver()
            # Try opening profile directly to speed up flow and skip login if session exists
            try:
                driver.get(PROFILE_URL)
            except Exception:
                pass

            # small pause to let redirect happen
            time.sleep(1)

            # If not already on a user profile, perform login
            try:
                cur = getattr(driver, 'current_url', '') or ''
                if 'mnjuser' not in cur and 'profile' not in cur:
                    logging.info('Not signed in, performing login...')
                    login(driver)
                else:
                    logging.info('Already signed in (skipping login).')
            except Exception:
                logging.info('Could not determine login state; attempting login.')
                login(driver)

            logging.info("Starting continuous Key Skills auto-save loop...")

            while True:
                if RUN_DURATION and time.time() - start_time >= RUN_DURATION * 60:
                    logging.info(f"Run duration reached ({RUN_DURATION} minutes). Exiting cleanly.")
                    return

                try:
                    click_key_skills_and_save(driver)
                except Exception as e:
                    logging.error(f"Auto-save cycle failed: {e}")
                    failures += 1
                    if failures >= MAX_FAILURES:
                        logging.error("Maximum consecutive failures reached; restarting browser.")
                        break
                else:
                    failures = 0

                time.sleep(INTERVAL)

            # End of continuous save loop
            break

        except Exception as e:
            logging.error(f"Main loop exception: {e}")
            failures += 1
            if failures >= MAX_FAILURES:
                logging.error("Maximum failures reached; exiting.")
                return
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
