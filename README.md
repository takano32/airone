# AirOne
This is a yet another DCIM(Data Center Infrastructure Management).

[![CircleCI](https://cci.dmm.com/gh/XaaS/airone.svg?style=shield&circle-token=30a830821a30ded88a93523a2312306f7d241540)](https://cci.dmm.com/gh/XaaS/airone)

# Feature
These are the features of this software.
- Flexible permission setting. You can set permissions for each attribute data.
- Structured data. You can make data schema flexibly and dynamically.

# Setup
Here is the documentation to setup the development environment of AirOne.

## Preparation
You have to install Python3.5+ to run AirOne like below (for the case of `ubuntu`).
```
$ sudo apt-get install python3 python3-pip
```

And you have to install RabbitMQ for executing heavy processing as background task using [Celery](http://docs.celeryproject.org/) and Memcached for caching backend.
```
$ sudo apt-get install rabbitmq-server memcached
```

Then, you can install libraries on which AieOne depends by following.
```
$ git https://git.dmm.com/XaaS/airone
$ cd airone
$ sudo pip install -r requirements.txt
```

This command makes database schema using the [django Migrations](https://docs.djangoproject.com/en/1.11/topics/migrations/), and makes default user account.
```
$ tools/clear_and_initdb.sh
```

This is the default account information.

| Username | Password |
|:---------|:---------|
| demo     | demo     |

Finally, you can start AirOne and can browse from `http://hostname:8080/`.
```
$ python3 manage.py runserver 0:8080
```

### Celery

In addition, you have to run Celery worker to execute background task as following.
```
$ celery -A airone worker -l info
```

### ElasticSearch
You have to setup Elasticsearch by following.
```
$ wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-6.2.3.tar.gz
$ tar -xvf elasticsearch-6.2.3.tar.gz
```

Then, you can execute ElasticSearch search like that.
```
$ elasticsearch-6.2.3/bin/elasticsearch
```

## Tools
There are some heler scripts about AirOne in the `tools` directory.

### register_es_documnt.py
This regists all entries which has been created in the database to the Elasticsearch.

#### Usage
You can do it just by following command. The configurations about the database to read and Elasticsearch to register are referred from airone/settings.py.

```
$ tools/register_es_document.py
```
