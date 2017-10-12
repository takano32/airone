#!/bin/sh

# clear the database
rm db.sqlite3
for dir in `find ./ -name "migrations"`
do
  rm ${dir}/0*.py || true
done

# re-construct database
python3 manage.py makemigrations
python3 manage.py migrate

# create initial user
cat << END | python3 manage.py shell
from user.models import User

for name in ['demo', 'racktables']:
    user = User(username=name, email='%s@dmm.local' % name)
    user.set_password('demo')
    user.save()
END
