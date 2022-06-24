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

# importing for running the dockerized selenium image 
from airflow.providers.docker.operators.docker import DockerOperator



# Our bucket
BUCKET_NAME = "capstone-legal"

MY_FOLDER_PREFIX = "hans-capstone"

DATA_PATH = '/opt/airflow/data/'



#################################################################################################################
########################################### HELPER FUNCTIONS ####################################################
#################################################################################################################

def upload_formatted_rss_feed(feed, feed_name):
    feed = feedparser.parse(feed)
    df = pd.DataFrame(feed['entries'])
    # csv_buffer = StringIO()
    # df.to_csv(csv_buffer)

    time_now = datetime.now().strftime('%Y-%m-%d_%I-%M-%S')
    filename = feed_name + '_' + time_now + '.csv'
    df.to_csv(f"{DATA_PATH}{filename}", index=False)
    # upload_string_to_gcs(csv_body=csv_buffer, uploaded_filename=filename)



#################################################################################################################
########################################### TASK 1 - EXTRACT ####################################################
#################################################################################################################

@task(task_id="scrape_proclamations")
def scrape_proc(ds=None, **kwargs): 
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
    df.to_parquet(f"{DATA_PATH}proclamations.parquet")
    # df.to_csv(f"{DATA_PATH}proclamations.csv", index=False)
    return 'Success'
    
@task(task_id='scrape_EOs')
def scrape_eo(ds=None, **kwargs):
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
    df['body_text'] = df['url'].apply(lambda x: scrape_RAs(x)).astype('str')
    df.to_parquet(f"{DATA_PATH}ra_data.parquet")
    # df.to_csv(f"{DATA_PATH}ra_data.csv", index=False)
    return "Successfully scraped Republic Acts"





#################################################################################################################
########################################### TASK 2 - TRANSFORM ##################################################
#################################################################################################################

@task(task_id="word_count")
def word_count(ds=None, **kwargs):

    def word_count(text):
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
    nlp = spacy.load("/model/en_core_web_sm/en_core_web_sm-3.3.0")
    def ner(text):
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
        # you need to find the column where the text/content is located e.g. 'summary' or 'content'
        # and add a conditional logic below
        ###########################################################################################

        if outfile.startswith(f'{DATA_PATH}cases'):
            df['NER'] = df['body_text'].apply(lambda x: ner(x))
            print(df['NER'])

        elif outfile.startswith(f'{DATA_PATH}executive'):
            df['NER'] = df['title'].apply(lambda x: ner(x))
            print(df['NER'])
        elif outfile.startswith(f'{DATA_PATH}proclamations'): 
            df['NER'] = df['title'].apply(lambda x: ner(x))
            print(df['NER'])
            
        elif outfile.startswith(f'{DATA_PATH}ra_data'):
            df['NER_title'] = df['title'].apply(lambda x: ner(x))
            df['NER_body'] = df['body_text'].apply(lambda x: ner(x))
           
            print(df[['NER_title', 'NER_body']])
        ###########################################################################################
        df.to_parquet(outfile)
        ###########################################################################################






#################################################################################################################
############################################ TASK 3 - LOAD ######################################################
#################################################################################################################

@task(task_id="load_data")
def load_data(ds=None, **kwargs): 
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

@task(task_id='upload_imgs')
def upload_imgs(ds=None, **kwargs): 
    files = os.listdir(f"{DATA_PATH}images/")
    for file in files: 
        outfile = f"{DATA_PATH}images/{file}"
        if not outfile.endswith('.png'): 
            continue
        with open(outfile, "rb") as img: 
            f = img.read()
            b = bytearray(f)

        # img = Image.open(outfile)
        # byteio = BytesIO()
        # img = img.save(byteio, 'PNG')
            print(b)
            upload_img_to_gcs(img=b, uploaded_filename=file)

# testing spacey 
# @task(task_id='spacey')
# def test_spacey(ds=None, **kwargs):  
#     nlp = spacy.load("en_core_web_sm")
#     text = ("When Sebastian Thrun started working on self-driving cars at "
#         "Google in 2007, few people outside of the company took him "
#         "seriously. “I can tell you very senior CEOs of major American "
#         "car companies would shake my hand and turn away because I wasn’t "
#         "worth talking to,” said Thrun, in an interview with Recode earlier "
#         "this week.")
#     doc = nlp(text)
#     print("Noun phrases:", [chunk.text for chunk in doc.noun_chunks])
#     print("Verbs:", [token.lemma_ for token in doc if token.pos_ == "VERB"])
#     for entity in doc.ents:
#         print(entity.text, entity.label_)

def upload_file_to_gcs(remote_file_name, local_file_name):
    gcs_client = boto3.client(
        "s3",
        region_name="auto",
        endpoint_url="https://storage.googleapis.com",
        aws_access_key_id=Variable.get("SERVICE_ACCESS_KEY"),
        aws_secret_access_key=Variable.get("SERVICE_SECRET"),
    )

    gcs_client.upload_file(local_file_name, BUCKET_NAME, remote_file_name)

# def upload_string_to_gcs(csv_body, uploaded_filename, service_secret=os.environ.get('SERVICE_SECRET')):
#     gcs_resource = boto3.resource(
#         "s3",
#         region_name="auto",
#         endpoint_url="https://storage.googleapis.com",
#         aws_access_key_id=Variable.get("SERVICE_ACCESS_KEY"),
#         aws_secret_access_key=Variable.get("SERVICE_SECRET"),
#     )
#     gcs_resource.Object(BUCKET_NAME, MY_FOLDER_PREFIX + "/" + uploaded_filename).put(Body=csv_body.getvalue())

def upload_img_to_gcs(img, uploaded_filename, service_secret=os.environ.get('SERVICE_SECRET')):
    gcs_resource = boto3.resource(
        "s3",
        region_name="auto",
        endpoint_url="https://storage.googleapis.com",
        aws_access_key_id=Variable.get("SERVICE_ACCESS_KEY"),
        aws_secret_access_key=Variable.get("SERVICE_SECRET"),
    )
    gcs_resource.Object(BUCKET_NAME, MY_FOLDER_PREFIX + "/images/" + uploaded_filename).put(Body=img)




# def upload_img_to_gcs(img, uploaded_filename, service_secret=os.environ.get('SERVICE_SECRET')):   
#     client = storage.Client.from_service_account_json(json_credentials_path='/keys/gcp_personal.json')
#     bucket = client.get_bucket(BUCKET_NAME)
#     object_name_in_gcs_bucket = bucket.blob(img)
#     object_name_in_gcs_bucket.upload_from_filename(MY_FOLDER_PREFIX + "/images/" + uploaded_filename)

#################################################################################################################
############################################ TASK 4 - CLEANUP ###################################################
#################################################################################################################

@task(task_id='delete_residuals')
def delete_residuals(ds=None, **kwargs): 
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
        'email': ['hxwwong@gmail.com'],
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
    schedule_interval=timedelta(days=1),
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
    
    
    # t1 = DockerOperator(
    #     task_id = 'scrape_jurisprudence'
    #     xcom = True # set to True to get all output in terminal 
    # )
    # ETL 
    # t1 >> [philstar_nation_feed()] >> t1_end >> t2 >> [word_count()] >> t2_end >> t3 >> [load_data()] >> t3_end >> t4 >> [map_images(), upload_imgs()] >> t4_end

    
#################################################################################################################
############################################ ETL PIPELINE #######################################################
#################################################################################################################

t_start >> t_docker >> [scrape_eo(), scrape_proc(), scrape_RA()] >> word_count() >> spacy_ner() >> load_data() >> t_end 



