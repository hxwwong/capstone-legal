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



# loading the env files for website credentials 
# replace these with your own 
dotenv.load_dotenv('develop.env')

## INITIALIZING SELENIUM ## 

login_page = "https://login.dlsu.idm.oclc.org/login?qurl=https://cdasiaonline.com%2fl%2fee17a146%2fsearch%3fyear_end%3d2022%26year_start%3d2022"

# window setings 

options = webdriver.ChromeOptions() 
options.add_argument("--headless")
options.add_argument("--start-maximized") 
options.add_argument("--disable-notifications")
options.add_argument("--incognito")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get(login_page)
driver.maximize_window() 
sleep(3) 

# inputting credentials from the dotenv file 

#  find_element(by=By.NAME, value=name)
username = driver.find_element(by=By.NAME, value='user') 
username.send_keys(os.environ['CDA_UN'])
sleep(1)

password = driver.find_element(by=By.NAME, value='pass') 
password.send_keys(os.environ['CDA_PW'])
sleep(1)

submit_button = driver.find_element(by=By.NAME, value='login') 
submit_button.click()
sleep(3)

# clicking the prompt after being redirected from login_page 
continue_button = driver.find_element(by=By.CLASS_NAME, value='btn-card-submit')
continue_button.click()

#############
## SCRAPER ## 
############# 

# collecting all the rows containing cases entries
cases = driver.find_elements(by=By.CLASS_NAME, value='i-menu-newtab')
data_list = [] 

# finding  core elements within each case entry 
for case in cases: 
    td = case.find_elements(by=By.TAG_NAME, value='td')
    ref_num = td[0].text # reference number (eg G.R. 1234)
    case_name = td[1].text # eg (Person A v. Person B.)
    judge = td[2].text # eg (HERNANDEZ, J)
    date = td[4].text # eg 2022-03-21
    url = case.get_attribute('data-href') # https://cdasia-online...

    # storing info as a dict for dataframe 
    data = {'ref_num': ref_num, 
            'case': case_name, 
            'judge': judge, 
            'date':date, 
            'url':url} 

    data_list.append(data)



def scrape_cases(url): 
    sleep(1)
    # try:
    driver.get(url)
    doc = driver.find_element(by=By.CLASS_NAME, value='doc-view-container')
    
    return doc.text.strip() 
    # 36 /124 have broken links -- have been designated null -- add to documentation 
    # except: 
    #     return None


# exporting to a dataframe & csv
df = pd.DataFrame(data_list)
df['body_text'] = df['url'].apply(lambda x: scrape_cases(x))
df.to_csv('test.csv', index=False)
