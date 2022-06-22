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



# Our bucket
BUCKET_NAME = "news_sites"

MY_FOLDER_PREFIX = "fem_hans"

DATA_PATH = '/opt/airflow/data/'

def upload_formatted_rss_feed(feed, feed_name):
    feed = feedparser.parse(feed)
    df = pd.DataFrame(feed['entries'])
    # csv_buffer = StringIO()
    # df.to_csv(csv_buffer)

    time_now = datetime.now().strftime('%Y-%m-%d_%I-%M-%S')
    filename = feed_name + '_' + time_now + '.csv'
    df.to_csv(f"{DATA_PATH}{filename}", index=False)
    # upload_string_to_gcs(csv_body=csv_buffer, uploaded_filename=filename)


@task(task_id="inquirer_feed")
def inquirer_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://www.inquirer.net/fullfeed", "inquirer")
    return True

@task(task_id="philstar_nation")
def philstar_nation_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://www.philstar.com/rss/nation", "philstar")

@task(task_id="business_world")
def business_world_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://www.bworldonline.com/feed/", "business_world")

@task(task_id="sunstar")
def sunstar_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://www.sunstar.com.ph/rssFeed/0", "sunstart")

@task(task_id="manila_standard")
def manila_standard_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://manilastandard.net/feed", "manila_standard")

@task(task_id="gma_national")
def gma_national_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://data.gmanetwork.com/gno/rss/news/nation/feed.xml", "gma_national")

@task(task_id="business_mirror")
def business_mirror_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://businessmirror.com.ph/feed/", "business_mirror")

@task(task_id="pna")
def pna_feed(ds=None, **kwargs):
    upload_formatted_rss_feed("https://www.pna.gov.ph/latest.rss", "pna")

# start of task 2 - transformation 
@task(task_id="word_count")
def word_count(ds=None, **kwargs):

    def word_count(text):
        words = text.split()
        freq = [words.count(w) for w in words]
        word_dict = dict(zip(words, freq))
        return word_dict


    files = os.listdir(DATA_PATH)
    print(files)
    for file in files: 
        outfile = f"{DATA_PATH}{file}"
        if not outfile.endswith('.csv'): 
            continue
        df = pd.read_csv(outfile)
        df['sum_word_cnt'] = df['summary'].apply(lambda x: len(x.split()))
        df['dict_word_cnt'] = df['summary'].apply(lambda x: word_count(x))
        df.to_csv(outfile, index=False)
        print(df[['summary','sum_word_cnt', 'dict_word_cnt']])

# task 3 - loading 
@task(task_id="load_data")
def load_data(ds=None, **kwargs): 
    files = os.listdir(DATA_PATH)
    for file in files: 
        outfile = f"{DATA_PATH}{file}"
        if not outfile.endswith('.csv'): 
            continue
        df = pd.read_csv(outfile)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer)
        upload_string_to_gcs(csv_body=csv_buffer, uploaded_filename=outfile)

# google street view 
@task(task_id='map_images')
def map_images(ds=None, **kwargs): 
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/keys/bigquery.json'
    client = bigquery.Client() 

    dataset = client.get_dataset('bigquery-public-data.geo_openstreetmap')
    tables = list(client.list_tables(dataset))
    print([table.table_id for table in tables])

    sql = """
    SELECT nodes.*
    FROM `bigquery-public-data.geo_openstreetmap.planet_nodes` AS nodes
    JOIN UNNEST(all_tags) AS tags
    WHERE tags.key = 'amenity'
    AND tags.value IN ('hospital',
        'clinic',
        'doctors')
    LIMIT 10
    """

    # Set up the query
    query_job = client.query(sql)

    # Make an API request  to run the query and return a pandas DataFrame
    df = query_job.to_dataframe()

    def google_maps_from_coords(lat, lon):
        return "https://maps.googleapis.com/maps/api/staticmap?center="+str(lat)+",+"+str(lon)+"&zoom=17&scale=1&size=600x300&maptype=satellite&format=png&visual_refresh=true"

    GOOGLE_MAPS_STATIC_API_KEY="AIzaSyD4Hwvz-wcXXa44NOZz-RAK3GBr6Zl-gBA"

    if not os.path.exists('/opt/airflow/data/images'):
        os.mkdir('/opt/airflow/data/images') 

    for _, row in df.iterrows():
        url = google_maps_from_coords(row['latitude'], row['longitude']) + "&key=" + GOOGLE_MAPS_STATIC_API_KEY
        req = requests.get(url, stream=True) 
        img = Image.open(req.raw)
        img_path = '/opt/airflow/data/images/'
        img.save(f"{img_path}{row['latitude']}_{row['longitude']}.png")

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

def upload_string_to_gcs(csv_body, uploaded_filename, service_secret=os.environ.get('SERVICE_SECRET')):
    gcs_resource = boto3.resource(
        "s3",
        region_name="auto",
        endpoint_url="https://storage.googleapis.com",
        aws_access_key_id=Variable.get("SERVICE_ACCESS_KEY"),
        aws_secret_access_key=Variable.get("SERVICE_SECRET"),
    )
    gcs_resource.Object(BUCKET_NAME, MY_FOLDER_PREFIX + "/" + uploaded_filename).put(Body=csv_body.getvalue())

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
  


with DAG(
    'coffee_lake_scrapers-v1',
    # These args will get passed on to each operator
    # You can override them on a per-task basis during operator initialization
    default_args={
        # 'depends_on_past': False,
        # 'email': ['caleb@eskwelabs.com'],
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
    description='RSS parsers',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2022, 6, 15),
    catchup=False,
    tags=['scrapers'],
) as dag:

    t1 = BashOperator(
        task_id="t1_start_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"starting task 1: scraping\"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )
    # t1 = EmptyOperator(task_id="start_message")

    t1_end = BashOperator(
        task_id="t1_end_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"ending task 1: scraping\"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )

    t2 = BashOperator( 
        task_id="t2_start_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"starting task 2: transformation - counting words \"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )

    t2_end = BashOperator( 
        task_id="t2_end_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"ending task 2: transformation - counting words \"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )

    t3 = BashOperator( 
        task_id="t3_start_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"starting task 3: loading - counting words \"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )
    
    t3_end = BashOperator( 
        task_id="t3_end_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"ending task 3: loading - counting words \"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )

    t4 = BashOperator( 
        task_id="t4_start_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"starting task 4: loading - osm street images \"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )

    t4_end = BashOperator( 
        task_id="t4_end_msg",
        bash_command="curl -X POST -H 'Content-type: application/json' --data '{\"text\" : \"ending task 4: loading - osm street images \"}' \"https://discord.com/api/webhooks/986224448984195082/pQp4GNcVWh-J2XtmIycVnjxYuGRGVIYFeveDRS5EwvgmGozthyd_alj8wbeKhfVn9SSk/slack\"",
        dag=dag
    )

    # ETL 
    t1 >> [philstar_nation_feed()] >> t1_end >> t2 >> [word_count()] >> t2_end >> t3 >> [load_data()] >> t3_end >> t4 >> [map_images(), upload_imgs()] >> t4_end

    # add commas to the list for extra functions 
    # add @task decorator, make the ids unique

    # t1 >> [inquirer_feed(), philstar_nation_feed(), business_world_feed(), sunstar_feed(), manila_standard_feed(), gma_national_feed(), business_mirror_feed(), pna_feed()] >> t_end




