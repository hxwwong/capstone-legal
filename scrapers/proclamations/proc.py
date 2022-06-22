from bs4 import BeautifulSoup
import pandas as pd
import requests

## general template is duplicated from exec.py since gazettes format the same way
def scrape_procs():
    r = requests.get('https://www.officialgazette.gov.ph/section/proclamations/')
    html = BeautifulSoup(r.content, 'lxml')

    proclamations = []

    summary_divs = html.find_all("div", {"class":"entry-summary"})
    titles = html.find_all('h3')[1:-1] # slicing to remove the unneeded header/footer h3 elements 

    for i in range(0, len(summary_divs)): 
        summaries = summary_divs[i].p 
        summary_content = summaries.get_text() 

        link = titles[i].find('a')
        url = link.get('href')
        id = link.get_text() 
        data = {'proc_id': id, 
                'title': summary_content, 
                'URL': url}

        proclamations.append(data)
    return proclamations

df = pd.DataFrame(scrape_procs())
df.to_csv('proclamations.csv')

## the URLs lead to the the html page, where you can access a pdf copy of the full EO order
