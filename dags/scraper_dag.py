from bz2 import compress
from datetime import timedelta
import boto3
import os
from io import StringIO, BytesIO
import feedparser
import pandas as pd
import spacy
import requests
import pybase64
from PIL import Image, ImageDraw
from google.cloud import bigquery, storage
from bs4 import BeautifulSoup
import pandas as pd
import requests
from selenium import webdriver 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.chrome.options import Options 
from selenium.webdriver.common.by import By 
from time import sleep 
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager 
import os 
import dotenv

# import en_core_web_sm

# The DAG object; we'll need this to instantiate a DAG
from airflow import DAG
from airflow.decorators import task
# from airflow.utils.dates import days_ago
from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
# from airflow.providers.discord.operators.discord_webhook import DiscordWebhookOperator 
from datetime import datetime

# importing provider packages 
from airflow.providers.docker.operators.docker import DockerOperator # for the dockerized selenium task 
from airflow.providers.google.cloud.operators.bigquery import BigQueryCheckOperator



#################################################################################################################
########################################### GLOBAL VARIABLES ####################################################
#################################################################################################################

BUCKET_NAME = "capstone-legal" # Our GCP bucket 
DATA_PATH = '/opt/airflow/data/' # VM's data folder

# GBQ variables for data validation
DATASET = "legal_documents"
TABLE_1 = "cases"
TABLE_2 = "executive_orders"
TABLE_3 = "proclamations"
TABLE_4 = "republic_acts"







#################################################################################################################
########################################### TASK 1 - EXTRACT ####################################################
#################################################################################################################

@task(task_id="scrape_proclamations")
def scrape_proc(ds=None, **kwargs): 
    def scrape_procs():
        """
        Scrapes the Official Gazette's section on Presidential Proclamations. 
        Finds the title of the EO_number, the EO title, and the URL, and outputs the df as a .parquet file
        """
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
    df.to_parquet(f"{DATA_PATH}proclamations.parquet")
    # df.to_csv(f"{DATA_PATH}proclamations.csv", index=False)
    return 'Success'
    
@task(task_id='scrape_EOs')
def scrape_eo(ds=None, **kwargs):
    """
    Scrapes the Official Gazette's section on Executive Orders. 
    Finds the title of the EO_number, the EO title, and the URL, and outputs the df as a .parquet file
    """
    r = requests.get('https://www.officialgazette.gov.ph/section/executive-orders/')
    html = BeautifulSoup(r.content, 'lxml')
    EOs = []
    summary_divs = html.find_all("div", {"class":"entry-summary"})
    titles = html.find_all('h3')[1:-1] # removing uneeded h3 elements 
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
    df = pd.DataFrame(EOs)
    df.to_parquet(f"{DATA_PATH}executive_orders.parquet")
    # df.to_csv(f"{DATA_PATH}executive_orders.csv", index=False) 
    return "Successfully srcraped EOs"

@task(task_id='scrape_republic_acts')
def scrape_RA(ds=None, **kwargs): 
    """
    Scrapes the lawphil.net page and outputs a .parquet file 
    with the RA_number, RA_title, date, URL, and body_text of the republic act. 
    The content of each RA is extracted from the URL, and applied elementwise to the df before being outputted.
    """
    def scrape_page():
        """
        Scrapes the base URL and returns a dictionary containing the column names of each row.
        A try and except clause has been added to account for broken links, which comprise around 1/3 of the target page
        """
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
            
            data = {'id': ra_num, 
                    'date': ra_date,
                    'title': ra_title,
                    'url':f"{base_url}{url}"}
            RAs.append(data)
        return RAs 

    def scrape_RAs(url): 
        """
        From the base URL, each individual page found in the initial scrape is navigated to, and the contents are scraped
        The text is stripped of unnecessary characters and returned
        """
        sleep(1)
        try:
            r = requests.get(url)
            html = BeautifulSoup(r.content, 'lxml')
            table = html.find_all('table')[0]
            return table.text.strip() 
        except: 
            return None

    df = pd.DataFrame(scrape_page())
    df['body_text'] = df['url'].apply(lambda x: scrape_RAs(x)).astype('str')
    df.to_parquet(f"{DATA_PATH}ra_data.parquet")
    return "Successfully scraped Republic Acts"





#################################################################################################################
########################################### TASK 2 - TRANSFORM ##################################################
#################################################################################################################

@task(task_id="word_count")
def word_count(ds=None, **kwargs):
    """
    Iterates through each .parquet file in DATA_PATH and
    creates two columns: a sum of the total number of individual words, and a frequency table in dictionary format. 
    Output is saved as a string dtype before overwriting the original file.
    """
    def word_count(text):
        """
        Counts the words and returns a dictionary containing the frequency of each detected word.
        Preprocessing is done at the start to remove words with specific characters, or those who fall below a specific length.
        """
        # returning an empty dict for blank/empty text
        if text is None: 
            return {}

        words = text.split()  
    
        # filtering for words w/ special chars
        temp = []
        for word in words: 
            s = ""
            for c in word: 
                if((ord(c) >= 97 and ord(c) <= 122) or (ord(c) >= 65 and ord(c) <= 90)):
                    s += c
            temp.append(s.lower())
        # filtering out words < 3 chars
        temp2 = []
        for word in temp: 
            if len(word) >= 3:
                temp2.append(word)
                    
                
        freq = [temp2.count(w) for w in temp2]
        word_dict = dict(zip(temp2, freq))
        return word_dict


    files = os.listdir(DATA_PATH)
    print(files)
    for file in files:
        outfile = f"{DATA_PATH}{file}"
        if not outfile.endswith('.parquet'):
            continue
        df = pd.read_parquet(outfile)
        ################################# TODO: IMPORTANT #########################################
        # you need to find the column where the text/content is located e.g. 'body' or 'content'
        # and add a conditional logic below
        ###########################################################################################
        if outfile.startswith(f'{DATA_PATH}cases'):
            df['sum_word_cnt'] = df['body_text'].apply(lambda x: len(x.split()))
            df['dict_word_cnt'] = df['body_text'].apply(lambda x: word_count(x)).astype('str')
            print(df[['body_text','sum_word_cnt', 'dict_word_cnt']])

        elif outfile.startswith(f'{DATA_PATH}executive'):
            df['sum_word_cnt'] = df['title'].apply(lambda x: len(x.split()))
            df['dict_word_cnt'] = df['title'].apply(lambda x: word_count(x)).astype('str')
            print(df[['title','sum_word_cnt', 'dict_word_cnt']])
        elif outfile.startswith(f'{DATA_PATH}proclamations'): 
            df['sum_word_cnt'] = df['title'].apply(lambda x: len(x.split()))
            df['dict_word_cnt'] = df['title'].apply(lambda x: word_count(x)).astype('str')
            print(df[['title','sum_word_cnt', 'dict_word_cnt']])
        elif outfile.startswith(f'{DATA_PATH}ra_data'):
            df['title_sum_word_cnt'] = df['title'].apply(lambda x: len(x.split()))
            df['title_dict_word_cnt'] = df['title'].apply(lambda x: word_count(x)).astype('str')
            df['body_sum_word_cnt'] = df['body_text'].apply(lambda x: ("" if x is None or len(x) == 0 else len(x.split())))
            df['body_dict_word_cnt'] = df['body_text'].apply(lambda x: word_count(x)).astype('str')
            print(df[['title', 'body_text','title_sum_word_cnt', 'title_dict_word_cnt', 'body_sum_word_cnt', 'body_dict_word_cnt']])
        ###########################################################################################

        df.to_parquet(outfile)
        
        

        


# NER
@task(task_id='spacy_ner')
def spacy_ner(ds=None, **kwargs):
    """
    Conducts Name Entity Recognition for each word found in the text functoin inputted. 
    It loops through all the .parquet files in DATA_PATH, and applies the ner() function elementwise. 
    The result is an overwritten .parquet file of the same name with additional NER columns for body 
    """
    nlp = spacy.load("/model/en_core_web_sm/en_core_web_sm-3.3.0")
    def ner(text):
        """
        Runs Name Entitry Recognition for each individual text input and returns a ner-object saved as a dictionary
        """
        doc = nlp(text)
        # print("Noun phrases:", [chunk.text for chunk in doc.noun_chunks])
        # print("Verbs:", [token.lemma_ for token in doc if token.pos_ == "VERB"])
        ner = {}
        for entity in doc.ents:
            ner[entity.text] = entity.label_
            print(entity.text, entity.label_)
        return ner

    files = os.listdir(DATA_PATH)
    for file in files:
        outfile = f"{DATA_PATH}{file}"
        if not outfile.endswith('.parquet'):
            continue
        df = pd.read_parquet(outfile)

        ################################# TODO: IMPORTANT #########################################
        # you need to find the column where the text/content is located e.g. 'title' or 'body_text'
        # and add conditional logic below
        ###########################################################################################

        if outfile.startswith(f'{DATA_PATH}cases'):
            df['NER'] = df['body_text'].apply(lambda x: ner(x)).astype('str')
            print(df['NER'])

        elif outfile.startswith(f'{DATA_PATH}executive'):
            df['NER'] = df['title'].apply(lambda x: ner(x)).astype('str')
            print(df['NER'])
        elif outfile.startswith(f'{DATA_PATH}proclamations'): 
            df['NER'] = df['title'].apply(lambda x: ner(x)).astype('str')
            print(df['NER'])
            
        elif outfile.startswith(f'{DATA_PATH}ra_data'):
            df['NER_title'] = df['title'].apply(lambda x: ner(x)).astype('str')
            df['NER_body'] = df['body_text'].apply(lambda x: ner(x)).astype('str')
           
            print(df[['NER_title', 'NER_body']])
        ###########################################################################################
        df.to_parquet(outfile)
        ###########################################################################################






#################################################################################################################
############################################ TASK 3 - LOAD ######################################################
#################################################################################################################

@task(task_id="load_data")
def load_data(ds=None, **kwargs): 
    """
    Iterates through the files in DATA_PATH, and checks if they are .parquet files. If so, they run the image through
    the upload_file_to_gcs() function, which manually uploads them to the GCS bucket. 
    """
    files = os.listdir(DATA_PATH)
    for file in files: 
        outfile = f"{DATA_PATH}{file}"
        if not outfile.endswith('parquet'): 
            continue
        df = pd.read_parquet(outfile)
        # csv_buffer = StringIO()
        df.to_parquet('df.parquet')
        # upload_string_to_gcs(csv_body='df.parquet.gzip', uploaded_filename=file)
        upload_file_to_gcs(remote_file_name=file, local_file_name='df.parquet')


def upload_file_to_gcs(remote_file_name, local_file_name):
    """
    Uploads the file to the GCS bucket defined locally on the VM's Airflow variables. 
    Remote file name sets the name on the bucket, while local identifies the file in the DATA_PATH directory
    """
    gcs_client = boto3.client(
        "s3",
        region_name="auto",
        endpoint_url="https://storage.googleapis.com",
        aws_access_key_id=Variable.get("SERVICE_ACCESS_KEY"),
        aws_secret_access_key=Variable.get("SERVICE_SECRET"),
    )

    gcs_client.upload_file(local_file_name, BUCKET_NAME, remote_file_name)


#################################################################################################################
############################################ TASK 4 - CLEANUP ###################################################
#################################################################################################################

# be careful when running this task without any pre-generated files locally - it will break the container
@task(task_id='delete_residuals')
def delete_residuals(ds=None, **kwargs): 
    """
    This function iterates through each file in the data folder. For each file, it will print the name of the path, and then delete the 
    contents if it is a folder or a .parquet file. The end result is an empty /opt/airflow/data folder when checked on the VM 
    """
    files = os.listdir(f"{DATA_PATH}")
    for file in files: 
        outfile = f"{DATA_PATH}{file}"
        print(file)
        if os.path.isdir(outfile):
            shutil.rmtree(outfile)
        elif not outfile.endswith('.parquet'):
            continue 
        else: 
            os.remove(outfile)

#################################################################################################################
################################################# DAG ###########################################################
#################################################################################################################

with DAG(
    'capstone-legal-v1',
    # These args will get passed on to each operator
    # You can override them on a per-task basis during operator initialization
    default_args={
        # 'depends_on_past': False,
        # 'email': ['hxwwong@gmail.com'],
        # 'email_on_failure': False,
        # 'email_on_retry': False,
        # 'retries': 1,
        # 'retry_delay': timedelta(minutes=5),
        # 'queue': 'bash_queue',
        # 'pool': 'backfill',
        # 'priority_weight': 10,
        # 'end_date': datetime(2016, 1, 1),
        # 'wait_for_downstream': False,
        # 'sla': timedelta(hours=2),
        # 'execution_timeout': timedelta(seconds=300),
        # 'on_failure_callback': some_function,
        # 'on_success_callback': some_other_function,
        # 'on_retry_callback': another_function,
        # 'sla_miss_callback': yet_another_function,
        # 'trigger_rule': 'all_success'
    },
    description='legal document webscrapers',
    schedule_interval=timedelta(days=7), # scraping this weekly 
    start_date=datetime(2022, 6, 15),
    catchup=False,
    tags=['scrapers'],
) as dag:

    t_start = BashOperator( 
        task_id = 'start_dag',
        bash_command= "echo start dag",
        dag=dag
    )

    t_end = BashOperator( 
        task_id = 'end_dag',
        bash_command= "echo end dag",
        dag=dag
    )

    t_docker = DockerOperator(
        task_id='docker-cases-ETL',
        image='hxwwong/capstone-juris-scraper:latest',
        # api_version='auto',
        auto_remove=True,
        # command="/bin/sleep 30",
        # docker_url="unix://var/run/docker.sock",
        network_mode="bridge", 
        environment={'CDA_UN':Variable.get('CDA_UN'), 
                     'CDA_PW':Variable.get('CDA_PW'), 
                     'SERVICE_ACCESS_KEY':Variable.get('SERVICE_ACCESS_KEY'), 
                     'SERVICE_SECRET':Variable.get('SERVICE_SECRET')}, 
        force_pull=True,
        dag=dag
    )
    
    
#################################################################################################################
############################################ ETL PIPELINE #######################################################
#################################################################################################################

t_start >> t_docker >> [scrape_eo(), scrape_proc(), scrape_RA()] >> word_count() >> spacy_ner() >> load_data() >> delete_residuals() >> t_end 




