import pandas as pd
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path
import time
import json
from typing import Dict, Optional
from urllib.parse import urljoin

def _find_best_image_url(driver: webdriver.Chrome, page_url: str) -> Optional[str]:
    """
    Finds the best quality image URL from a page using a prioritized search strategy.
    """
    try:
        driver.get(page_url)
        time.sleep(2)

        # --- NEW: More robust meta tag search ---
        # Look for the high-quality image URL provided for social media sharing
        meta_selectors = [
            '//meta[@property="og:image"]',
            '//meta[@name="twitter:image"]'
        ]
        for selector in meta_selectors:
            try:
                meta_tag = driver.find_element(By.XPATH, selector)
                if meta_tag:
                    url = meta_tag.get_attribute('content')
                    if url:
                        print(f"  - Found high-quality image in meta tag: {selector}")
                        return urljoin(page_url, url)
            except Exception:
                continue # Tag not found, try the next one

        # Fallback to searching for the largest <img> tag if meta tags fail
        print("  - Fallback: Searching for largest visible image...")
        images = driver.find_elements(By.TAG_NAME, 'img')
        if not images: return None

        largest_image_url = None
        max_area = 0
        for img in images:
            try:
                src = img.get_attribute('src')
                if not src: continue
                
                # --- NEW: More aggressive thumbnail filtering ---
                # Ignore common thumbnail indicators in the URL
                if any(keyword in src for keyword in ['thumb', 'icon', 'logo', 'avatar']):
                    continue
                
                width = img.size.get('width', 0)
                height = img.size.get('height', 0)
                area = width * height

                if area > max_area and width > 150 and height > 150:
                    max_area = area
                    largest_image_url = src
            except Exception:
                continue
        
        if largest_image_url:
            print("  - Found largest image via fallback method.")
            return urljoin(page_url, largest_image_url)

        return None

    except Exception as e:
        print(f"  - An error occurred while processing page {page_url}: {e}")
        return None
    
    
def _download_and_save_image(image_url: str, output_path: Path):
    """
    Downloads an image from a URL and saves it to a specified path.
    """
    try:
        response = requests.get(image_url, stream=True, timeout=15)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
        print(f"  - Successfully saved image to {output_path}")

    except requests.exceptions.RequestException as e:
        print(f"  - Failed to download image from {image_url}: {e}")

def test_single_url(config: Dict, test_url: str, recipe_id: str = "test_recipe"):
    """
    A helper function to test the image finding logic on a single URL.
    """
    print(f"\n--- Testing single URL: {test_url} ---")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
    
    image_url = _find_best_image_url(driver, test_url)
    
    if image_url:
        print(f"  - Found best image URL: {image_url}")
        image_output_path = Path(config["IMAGE_OUTPUT_DIR"]) / f"{recipe_id}.png"
        _download_and_save_image(image_url, image_output_path)
    else:
        print("  - Could not find a suitable image URL.")
        
    driver.quit()
    print("--- Test complete ---")

def process_all_recipes(config: Dict):
    """
    Main function to iterate through all recipes, find their images,
    and update the dataset.
    """
    print("\n--- Starting full image processing workflow ---")
    
    data_path = Path(config["PROCESSED_DATA_PATH"])
    try:
        df = pd.read_parquet(data_path)
    except FileNotFoundError:
        print(f"FATAL ERROR: Processed data file not found at {data_path}")
        return

    image_dir = Path(config["IMAGE_OUTPUT_DIR"])
    image_dir.mkdir(parents=True, exist_ok=True)
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
    
    image_urls = []
    
    for index, row in df.iterrows():
        recipe_id = row['recipe_id']
        recipe_url = row['recipe_url']
        print(f"\nProcessing Recipe ID: {recipe_id} ({index + 1} of {len(df)})")
        
        image_url = _find_best_image_url(driver, recipe_url)
        
        if image_url:
            image_output_path = image_dir / f"{recipe_id}.png"
            _download_and_save_image(image_url, image_output_path)
            image_urls.append(image_url)
        else:
            image_urls.append(None)

    driver.quit()

    df['image_url'] = image_urls
    df.to_parquet(data_path, index=False)
    
    print("\n--- Full image processing complete ---")
    print(f"Updated dataset with 'image_url' column saved to {data_path}")

if __name__ == '__main__':
    CONFIG = {
        "PROCESSED_DATA_PATH": "processed_recipes.parquet",
        "IMAGE_OUTPUT_DIR": "recipe_images"
    }
    
    # To test a single URL, uncomment the line below and run the script.
    test_single_url(CONFIG, test_url="https://www.food.com/recipe/best-baked-ziti-94978", recipe_id="94978")
    
    # To run the full process for all recipes, uncomment the line below.
    # WARNING: This will be very slow.
    # process_all_recipes(CONFIG)