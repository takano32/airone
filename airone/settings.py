import os
import sys
import logging
import subprocess
import pymysql

pymysql.install_as_MySQLdb()

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '(ch@ngeMe)'

# Celery settings
CELERY_BROKER_URL = 'amqp://guest:guest@localhost//'

#: Only add pickle to this list if your broker is secured
#: from unwanted access (see userguide/security.html)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_BACKEND = 'rpc://'
CELERY_TASK_SERIALIZER = 'json'
CELERY_BROKER_HEARTBEAT = 0

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'common',
    'user',
    'group',
    'entity',
    'acl',
    'dashboard',
    'entry',
    'job',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'import_export',
    'rest_framework',
    'rest_framework.authtoken',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'airone.urls'

PROJECT_PATH = os.path.realpath(os.path.dirname(__file__))
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            PROJECT_PATH + '/../templates/',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'airone.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'airone',
        'USER':'root',
        'PASSWORD':'',
        'HOST':'localhost',
    }
}


# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tokyo'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    PROJECT_PATH + '/../static/'
]

LOGIN_REDIRECT_URL='/dashboard/'

# global settins for AirOne
AIRONE = {
    'ENABLE_PROFILE': True,
    'CONCURRENCY': 1,
    'VERSION': 'unknown',
    'FILE_STORE_PATH': '/tmp/airone_app',
}
try:
    proc = subprocess.Popen("cd %s && git describe --tags" % BASE_DIR, shell=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate(timeout=1)
    # if `git describe --tags` prints some string to stdout, use the result as version
    # else use 'unknown' as version (e.g. untagged git repository)
    if outs != b'':
        AIRONE['VERSION'] = outs.strip()
    else:
        logging.getLogger(__name__).warning('could not describe airone version from git')

    # create a directory to store temporary file for applications
    if not os.path.exists(AIRONE['FILE_STORE_PATH']):
        os.makedirs(AIRONE['FILE_STORE_PATH'])

except FileNotFoundError:
    # do nothing and use 'unknown' as version when git does not exists
    logging.getLogger(__name__).warning('git command not found.')


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': 'localhost:11211',
        'TIMEOUT': None,
    }
}

ES_CONFIG = {
    'NODES': ['localhost:9200'],
    'INDEX': 'airone',
    'MAXIMUM_RESULTS_NUM': 500000,
    'TIMEOUT': None
}
