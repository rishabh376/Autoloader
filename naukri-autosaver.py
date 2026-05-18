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
import undetected_chromedriver as uc

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

# Fast Interval: 10 seconds (Matches manual speed)
INTERVAL = 10

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
    options = uc.ChromeOptions()
    # options.add_argument("--headless") # Uncomment later to run in background
    
    try:
        driver = uc.Chrome(options=options)
        driver.maximize_window()
        return driver
    except Exception as e:
        logging.error(f"Could not start browser: {e}")
        raise



def login(driver):
    # Go DIRECTLY to the login page for better reliability
    logging.info("Navigating to login page...")
    driver.get("https://www.naukri.com/nlogin/login")
    
    wait = WebDriverWait(driver, 20)
    
    logging.info("Entering credentials...")
    
    try:
        # Enter email (using the specific ID Naukri uses)
        email_field = wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
        email_field.clear()
        email_field.send_keys(EMAIL)
        
        # Enter password
        password_field = driver.find_element(By.ID, "passwordField")
        password_field.clear()
        password_field.send_keys(PASSWORD)
        
        # Click login button
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # Wait for redirect to profile or dashboard
        logging.info("Waiting for dashboard to load...")
        wait.until(lambda d: "mnjuser" in d.current_url)
        
        logging.info("Login successful!")
        time.sleep(3)
        
    except Exception as e:
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
    while True:
        driver = None
        try:
            driver = get_driver()
            login(driver)
            
            logging.info("Starting continuous Key Skills auto-save loop...")
            
            while True:
                try:
                    click_key_skills_and_save(driver)
                    failures = 0  # reset on success
                    
                    # Random delay to look more human + respect server limits
                    delay = INTERVAL + random.uniform(10, 60)
                    logging.info(f"Waiting for {int(delay)} seconds before next update...")
                    time.sleep(delay)
                    
                except Exception as e:
                    failures += 1
                    logging.warning(f"Action failed ({failures}/{MAX_FAILURES}): {e}")
                    if failures >= MAX_FAILURES:
                        raise
                    time.sleep(2)
                    
        except KeyboardInterrupt:
            logging.info("Script stopped by user.")
            break
            
        except Exception as e:
            logging.error(f"Critical error: {e}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            time.sleep(10)  # Wait before full restart
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass


if __name__ == "__main__":
    print("Naukri Auto Key-Skills Saver Started (24x7)")
    main()