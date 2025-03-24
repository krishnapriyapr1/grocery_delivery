import os
import requests
from PIL import Image
from io import BytesIO

# URLs for high-quality grocery images (replace with actual URLs)
IMAGES = {
    'hero': {
        'hero-bg': 'https://images.unsplash.com/photo-1542838132-92c53300491e?q=80&w=2574&auto=format&fit=crop',
        'newsletter-bg': 'https://images.unsplash.com/photo-1608686207856-001b95cf60ca?q=80&w=2574&auto=format&fit=crop',
    },
    'categories': {
        'fruits': 'https://images.unsplash.com/photo-1610832958506-aa56368176cf?q=80&w=2574&auto=format&fit=crop',
        'vegetables': 'https://images.unsplash.com/photo-1566385101042-1a0aa0c1268c?q=80&w=2574&auto=format&fit=crop',
        'dairy': 'https://images.unsplash.com/photo-1628088062854-d1870b4553da?q=80&w=2574&auto=format&fit=crop',
        'bakery': 'https://images.unsplash.com/photo-1509440159596-0249088772ff?q=80&w=2574&auto=format&fit=crop',
        'meat': 'https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?q=80&w=2574&auto=format&fit=crop',
        'beverages': 'https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?q=80&w=2574&auto=format&fit=crop',
    },
    'featured': {
        'bananas': 'https://images.unsplash.com/photo-1603833665858-e61d17a86224?q=80&w=2574&auto=format&fit=crop',
        'milk': 'https://images.unsplash.com/photo-1563636619-e9143da7973b?q=80&w=2574&auto=format&fit=crop',
        'bread': 'https://images.unsplash.com/photo-1509440159596-0249088772ff?q=80&w=2574&auto=format&fit=crop',
        'salmon': 'https://images.unsplash.com/photo-1499125562588-29fb8a56b5d5?q=80&w=2574&auto=format&fit=crop',
    }
}

def download_and_save_image(url, save_path, size=(800, 600)):
    try:
        response = requests.get(url)
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Resize image while maintaining aspect ratio
        img.thumbnail(size, Image.Resampling.LANCZOS)
        
        # Save the image
        img.save(save_path, 'JPEG', quality=85)
        print(f"Successfully saved {save_path}")
    except Exception as e:
        print(f"Error downloading {url}: {str(e)}")

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create directories if they don't exist
    for category in ['hero', 'categories', 'featured']:
        os.makedirs(os.path.join(base_dir, category), exist_ok=True)
    
    # Download hero images
    for name, url in IMAGES['hero'].items():
        save_path = os.path.join(base_dir, 'hero', f'{name}.jpg')
        download_and_save_image(url, save_path, size=(1920, 1080))
    
    # Download category images
    for name, url in IMAGES['categories'].items():
        save_path = os.path.join(base_dir, 'categories', f'{name}.jpg')
        download_and_save_image(url, save_path)
    
    # Download featured product images
    for name, url in IMAGES['featured'].items():
        save_path = os.path.join(base_dir, 'featured', f'{name}.jpg')
        download_and_save_image(url, save_path)

if __name__ == '__main__':
    main()
