Username (leave blank to use 'asus'):Username (leave blank to use 'asus'):Username (leave blank to use 'asus'):import os
import requests
from PIL import Image
from io import BytesIO

# URLs for high-quality authentication images
IMAGES = {
    'login-bg': 'https://images.unsplash.com/photo-1542838132-92c53300491e?q=80&w=2574&auto=format&fit=crop',
    'register-bg': 'https://images.unsplash.com/photo-1543168256-418811576931?q=80&w=2574&auto=format&fit=crop'
}

def download_and_save_image(url, save_path, size=(1920, 1080)):
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
    
    # Create auth directory if it doesn't exist
    os.makedirs(base_dir, exist_ok=True)
    
    # Download auth images
    for name, url in IMAGES.items():
        save_path = os.path.join(base_dir, f'{name}.jpg')
        download_and_save_image(url, save_path)

if __name__ == '__main__':
    main()
