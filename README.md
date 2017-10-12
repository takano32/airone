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
