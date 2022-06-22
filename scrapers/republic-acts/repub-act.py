from bs4 import BeautifulSoup
from time import sleep
import pandas as pd
import requests

# add a docstring 

def scrape_page():
    r = requests.get('https://lawphil.net/statutes/repacts/ra2021/ra2021.html')
    html = BeautifulSoup(r.content, 'lxml')

    table_RAs = html.find_all('table')[2]
    table_rows = table_RAs.find_all('tr')
    
    RAs = [] 
    base_url = 'https://lawphil.net/statutes/repacts/ra2021/'
    
    for idx, row in enumerate(table_rows): 
        if idx == 0: 
            continue
        
        if idx == (len(table_rows)-2): 
            break
        
        # print(row.text)
        row_data = row.find_all('td')
        ra_num = row_data[0].find('a').text
        ra_date = row_data[0].text.split(ra_num)[1].strip()
        ra_title = row_data[1].text.strip()
        url = ""
        link = row_data[0].find('a')
        
        
        try: 
            url = link['href']
        except: 
            url = link['xref']
         
        data = {'id': ra_num, 'date': ra_date, 'title': ra_title, 'url':f"{base_url}{url}"}
        RAs.append(data)

    return RAs 

def scrape_RAs(url): 
    sleep(1)
    try:
        r = requests.get(url)
        html = BeautifulSoup(r.content, 'lxml')

        table = html.find_all('table')[0]
        
        return table.text.strip() 
    # 36 /124 have broken links -- have been designated null -- add to documentation 
    except: 
        return None

df = pd.DataFrame(scrape_page())
df['body_text'] = df['url'].apply(lambda x: scrape_RAs(x))
df.to_csv('ra_data.csv', index=False)