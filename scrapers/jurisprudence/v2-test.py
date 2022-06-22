import random 
from selenium import webdriver 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.chrome.options import Options 
from selenium.webdriver.common.by import By 
from time import sleep 
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager 
import os 
import dotenv
import pandas as pd 
from bs4 import BeautifulSoup
import requests 

dotenv.load_dotenv('develop.env')

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
login_page = "https://login.dlsu.idm.oclc.org/login?qurl=https://cdasiaonline.com%2fl%2fee17a146%2fsearch%3fyear_end%3d2022%26year_start%3d2022"

driver.get(login_page)
driver.maximize_window() 

options = Options() 
options.add_argument("--headless")
options.add_argument("--start-maximized") 
options.add_argument("--disable-notifications")
options.add_argument("--incognito")
sleep(3) 
# sleep(3)

username = driver.find_element_by_name('user') 
username.send_keys(os.environ['CDA_UN'])
sleep(1)

password = driver.find_element_by_name('pass')
password.send_keys(os.environ['CDA_PW'])
sleep(1)

submit_button = driver.find_element_by_name('login')
submit_button.click()
sleep(3)

continue_button = driver.find_element_by_class_name('btn-card-submit')
continue_button.click()

# scraping the page 
cases = driver.find_elements_by_class_name('i-menu-newtab')
data_list = [] 
for case in cases: 
    td = case.find_elements_by_tag_name('td')
    

    ref_num = td[0].text
    case_name = td[1].text 
    judge = td[2].text 
    date = td[4].text 
    url = case.get_attribute('data-href')

    data = {'ref_num': ref_num, 
            'case': case_name, 
            'judge': judge, 
            'date':date, 
            'url':url} 

    data_list.append(data)

# doc-view-container js-content

def scrape_cases(url): 
    sleep(1)
    # try:
    driver.get(url)
    doc = driver.find_element_by_class_name('doc-view-container')
    
    return doc.text.strip() 
    # 36 /124 have broken links -- have been designated null -- add to documentation 
    # except: 
    #     return None


# exporting to a dataframe & csv
df = pd.DataFrame(data_list)
df['body_text'] = df['url'].apply(lambda x: scrape_cases(x))
df.to_csv('cases_data_v2.csv', index=False)
df