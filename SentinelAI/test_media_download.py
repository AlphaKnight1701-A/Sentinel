import requests
import os

url = "https://pbs.twimg.com/media/Gq61KDyXcAEIzOd.jpg"
response = requests.get(url, stream=True)
if response.status_code == 200:
    with open("temp_media.jpg", "wb") as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)
    print("Saved")
