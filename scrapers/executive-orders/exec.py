from bs4 import BeautifulSoup
import pandas as pd
import requests

def scrape_EOs():
    r = requests.get('https://www.officialgazette.gov.ph/section/executive-orders/')
    html = BeautifulSoup(r.content, 'lxml')

    EOs = []

    summary_divs = html.find_all("div", {"class":"entry-summary"})
    titles = html.find_all('h3')[1:-1] # slicing to remove the unneeded header/footer h3 elements 

    for i in range(0, len(summary_divs)): 
        summaries = summary_divs[i].p 
        summary_content = summaries.get_text() 

        link = titles[i].find('a')
        url = link.get('href')
        id = link.get_text() 
        data = {'eo_id': id, 
                'title': summary_content, 
                'URL': url}

        EOs.append(data)
    return EOs 

df = pd.DataFrame(scrape_EOs())
df.to_csv('executive_orders.csv', index=False)

## the URLs lead to the the html page, where you can access a pdf copy of the full EO order
