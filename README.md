# capstone-legal

As the rise to continued threats to the safety of individuals, and the rising incidence of corruption, crime, and abuse of power, it becomes more essential for people to be aware of the law, decisions, and how they intersect with their daily lives.

With the rising costs of journal subscriptions, knowledge about the law is too important to people's lives to be gatekept from the public.

This capstone project aims to provide an automated data pipeline that ingests data from various open-source legal libraries, leading legal journals, and governmental websites in order to generate a dataset that is ready for consultation, or NLP assisted projects.

Through running a Google Cloud Engine instance, we utilize Docker and Apache Airflow to deploy an ETL pipeline which scrapes and aggregates data from different websites, legal journals, and publications to generate an NLP-ready database for the public. 

This is a capstone project made by Hans Xavier W. Wong for Sprint 4 of Cohort 1 of the Data Engineering Bootcamp.

# Setup

The main tool used for development was VSCode as an IDE, github, and the Google Cloud Engine as the virtual machine. 

Two repositories were used to develop the output. First, a `docker-compose.yaml` was created, alongside the `dags`, `data` , `plugins` , `logs` , 

## Initializing the Google Compute Engine - VM with Docker and Git

1. Select a cloud VM from the GCE page:  [https://console.cloud.google.com/](https://console.cloud.google.com/)compute
    1. Usually the E2 version with 8 GB of memory will be enough
2. Follow the docker installation docs for debian (or whichever corresponding OS is chosen): [https://docs.docker.com/engine/install/ubuntu/https://docs.docker.com/engine/install/debian/](https://docs.docker.com/engine/install/debian/)
3. run `apt install git`
4. generate a keygen with `ssh-keygen` and navigate to path, copy the follow ssh code, and add it as a github deploy key. You can then clone the github repo into the VM
5. run `docker compose up` with in the cloned git repo to initialize the `docker-compose.yaml` file 

## nginx configuration

1. run `apt install nginx`
2. run `vim nignx /etc/nginx/sites-available/default`
3. comment line 41 `root var www/html`
4. comment line 51 `try files $uri ...`
5. add a line with `proxy_pass http://127.0.0.1:8080;` 
6. run `service nginx restart`
    1. test with `service nginx status` if green: restart the IP on browser to access airflow 

## Building & Exporting the Selenium Scraper

After setting up this repo, you’ll notice that `scraper_dag.py` contains a docker-operator. 

This pulls a docker image from dockerhub, which has been independently configured in this repo: [https://github.com/hxwwong/capstone-legal-docker-scraper](https://github.com/hxwwong/capstone-legal-docker-scraper)

Follow the instructions there to build your own docker image, and push it to the docker hub. Make sure to configure the `DockerOperator` to have the following arguments: 

- `image` needs to contain the name of the image `'<image name>'` built with the files from the docker-scraper repo as a string. Additonally, you can add a `:<insert tag>` tag at the end to specify any individual tags. By default, it will pull the `'latest'` tag.
- `environment` needs to configure the credentials to be used, which can be obtained by passing a dictionary containing the key, and the `Variable.get` function. More on this in the security section below.
- `force_pull` needs to be set to `True` to ensure the docker image pulled is the lastest

### Common errors

A common error here occurs when a new docker image is pushed, and an attempt to run the DockerOperator task is made without updating the Airflow server. Since there are cached versions of the image, it’s possible the updated image may not be the one that is pulled. 

To fix this, it’s important to run `docker compose down` and `docker compose up` whenever a new image is built and pushed.

## Security Best Practices

- a `develop.env` file was used locally to save the credentials used for website scraping as well as the GCP service access keys to upload files to the Google Cloud Bucket. This file is parsed by `dotenv` in `scraper.py` to separate out GCP & selenium scraper credentials. Due to the use of `.gitignore` and `.dockerignore` files, they will not appear in the docker image and the repo. Hence you will need to create and initialize your own, and modify the `environ.os()` and `get.Variables()` tags if needed.
    - Once created, add the service keys manually to Airflow by going to the user toolbar and selecting Admin > Variables and Admin > Connections for each type of credential needed.
- Limited permissions were set on the Google Cloud Platform and the Google Big Query service accounts to minimize exposure.

# Data Extraction
This section covers the data sources, the ingestion process, and the scrapers.

## Data Sources

There are three main data sources used for this project: 

1. The LAWPHiL Project, by the Arellano Foundation - which hosts legal documents varying from jurisprudence, statutory law, and judicial issuances (link: [https://lawphil.net/](https://lawphil.net/judjuris/juri2022/juri2022.html))
2. CDAsia Online -  a law database curated and is accessible only with a specific set of credentials (link: [cdasiaonline-com.dlsu.idm.oclc.org](http://cdasiaonline-com.dlsu.idm.oclc.org/)) 
3. Official Gazette of the Philippines  - the official legal journal of the Republic of the Philippines created by decree of Act No. 453 and Commonwealth Act No. 68 (link: [https://www.officialgazette.gov.ph/](https://www.officialgazette.gov.ph/)) 

These data sources were selected for their completeness, frequent updates, and accessibility. In particular, the LAWPHiL Project was used to scrape the Republic Acts, CDA-Asia for jurisprudence/legal-cases, and the Official Gazette for Presidential Proclamations and Executive Orders.

## Data Ingestion

The data will be updated on a monthly basis, as legal jurisprudence is slower to update than other data sources. 

The primary tool for ingestion is the use of webscrapers. A total of four different webscrapers will be utilized for each of the four legal documents: cases/jurispredence, executive orders, proclamations, and republic acts. 

Three of these webscrapers (Executive Orders, Proclamations, and Republic Acts) utilize BeautifulSoup4 and are found locally in the `scraper_dag.py` . The cases/jurisprudence webscraper requires the use of Selenium, and will exist separetely on a Docker image called via the `DockerOperator` task. 

The output of these scrapers is a `.parquet` file, selected for its low size and compressibility as a columnar form of data storage. 

A GCE VM instance will run the scrapers on a scheduled basis, and within the `scraper_dag.py` file, upload their outputs. From there, scheduled data transfers will load the data into Google Big Query tables, while cleaning out the data source.

# Data Transformation, Validation

Some of the data transformation and reshaping comes bundled with the scraping scripts. Many of them include cleaning, stripping, and handling if the data posseses nulls, duplicates, and other irregular information.

However, there are two transformations that have distinct steps utilized for preparing the data for NLP projects in particular. Both of these steps require accessing the `DATA_PATH` variable containing the initial parquet files from the extraction phase, and overwriting them with the transformed values.

First, is `word_count()` which summarizes the total number of words in a given string, as well as creating a dictionary with individual words and their frequencies as key-value pairs.  

It’s worth noting that some level of validation is done here, because words that are blank, or NoneType, or have less than three characters are filtered out. Some exception handling here is managed.

These are then applied element-wise with `pandas.apply()` to create new columns, and overwrite the initial parquet files. 

The second transformation is `spacy_ner()`, which is a function that uses conditional logic to identify which of the parquet files have title/body text that can be analyzed with Named Entity Recognition. After analyzing each major table, new columns are appended, and the parquet files are overwritten.

### Common Errors

- If the spacy package fails to load, it could be a configuration error with the `ensemble_model_web_sm` is stored. It needs to be mounted on the `docker-compose.yaml` ’s volumes file inside of models, and the path specified in `nlp.load(<path>)` needs to access the package version needed.
- A common source of errors here will be forgetting to convert the dictionary objects yielded by the transformations into `str` . While this will not cause any errors in the DAG, it will cause erros when transferring the data from the buckets to the
    
    Failing to do this will create null values and missing columns that will cause errors when porting the data to Google Big Query tables. Each transformation should be appended by the `.astype('str')` method to avoid this. 
    
- Another common error is the lack of error or exception handling. When adding new columns or new transformations, some null-type objects and missing data can crop up. It’s important to use try-except clasues to pre-empt this were possible.
- When changing the names of files or the format they are saved in, make sure to modify modify the `.startswith()` and `.endswith()` clauses. Failing to do so can result in your files failing to be detected by the necessary functions/transformations.

# Loading Data & Cleanup

Following  the transformation stage, all the data is loaded into Google Cloud Storage via the `load_data()` and `upload_file_gcs()` functions. Both of these make use of the Airflow variables to access the credentials, and simply iterate through each parquet file in the `DATA_PATH`  directory. 

After this task is completed, `delete_residuals` is a cleanup task that removes all files and directories from the local drive once the uploading has completed. This ensures that we minimzie memory and hosting costs on GCE. 

Once in the bucket, scheduled data transfers mapped to the parquet files will transfer them to Google Big Query, loading them into preset tables at a scheduled pace. 

### Common Errors

- The cleanup task, in order to run, must have files to delete. If the task is triggered without any files, an error will occur. To avoid this, restart the DAG as a whole and ensure files are generated before the cleanup task is ran.
- ensure that the `remote_file_name` and `local_file_name` inputs are configured properly and that they take strings as inputs. Passing variables or invalid names will result in an error.
- When changing the names of files or the format they are saved in, make sure to modify modify the `.startswith()` and `.endswith()` clauses. Failing to do so can result in your files failing to be detected by the necessary functions/transformations.

# Challenges & Points for Improvement

- A major point of improvement is the use of more rigorous data validation for the files, and the use of branching operators to manage failures in the pipeline. Most of the time spent on the project was mostly ensuring the files and the end output were bug-free, and had limited opportunity to polish the ingestion requirements and parameters.

- Another point of improvement is the use of a better cleanup task. Rather than just clearing the local file, it’s possible to attach a date and time modifier to ensure that no duplication exists when ingesting new data, and when managing data transfers. This lowers the cost accrued by redundancy.

- A major challenge that I encountered were managing the data types and dealing with the errors that cropped uip on overlapping processes. A lot of time was spent tracking, debugging, and coding plenty of try-except clauses to ensure that all the data was parsed properly, and the dag wouldn’t fail. I think more attention to detail with things like data-types, file paths, and the like, especially when changes were made, would help reduce the number of iterations needed in this process.

- Another struggle was how long it took for certain dags or images to build/compose. It made it hard to get immediate feedback on what was going wrong, and slowed down the whole error-correction pipeline. In an extreme case, it even meant that I had to restart the setup process again because repeated docker image pulling ended up consuming too much memory space. I From that, I understand better the importance of creating a dedicated environment for testing, validation, and placing checks to ensure resources are manged optimally.


# References 
Dyevre, A. (2021). Text-mining for lawyers: How machine learning techniques can advance our understanding of legal discourse. Erasmus Law Review, 14, 7. https://heinonline.org/HOL/Page?handle=hein.journals/erasmus14&id=9&div=&collection=

Ibarra, V. C., & Revilla, C. D. (2014). Consumers’ awareness on their eight basic rights: A comparative study of filipinos in the philippines and guam (SSRN Scholarly Paper No. 2655817). Social Science Research Network. https://papers.ssrn.com/abstract=2655817

Peramo, E., Cheng, C., & Cordel, M. (2021). Juris2vec: Building word embeddings from philippine jurisprudence. 2021 International Conference on Artificial Intelligence in Information and Communication (ICAIIC), 121–125. https://doi.org/10.1109/ICAIIC51459.2021.9415251

Virtucio, M. B. L., Aborot, J. A., Abonita, J. K. C., Aviñante, R. S., Copino, R. J. B., Neverida, M. P., Osiana, V. O., Peramo, E. C., Syjuco, J. G., & Tan, G. B. A. (2018). Predicting decisions of the philippine supreme court using natural language processing and machine learning. 2018 IEEE 42nd Annual Computer Software and Applications Conference (COMPSAC), 02, 130–135. https://doi.org/10.1109/COMPSAC.2018.10348




