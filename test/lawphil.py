import requests 
from bs4 import BeautifulSoup

r = requests.get('https://lawphil.net/statutes/repacts/ra2022/ra2022.html')

BeautifulSoup(r.content)

html = BeautifulSoup(r.content)

html.select()