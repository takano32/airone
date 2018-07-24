#!/bin/sh

# clear the database
rm db.sqlite3
for dir in `find ./ -name "migrations"`
do
  rm ${dir}/0*.py || true
done

# recreate database of MySQL
db_name=$(python3 -c "from airone import settings; print(settings.DATABASES['default']['NAME'])")
db_user=$(python3 -c "from airone import settings; print(settings.DATABASES['default']['USER'])")
db_pass=$(python3 -c "from airone import settings; print(settings.DATABASES['default']['PASSWORD'])")

echo "drop database ${db_name}" | mysql -u${db_user} -p${db_pass}
echo "create database ${db_name}" | mysql -u${db_user} -p${db_pass}

# re-construct database
python3 manage.py makemigrations
python3 manage.py migrate

# create initial user
cat << END | python3 manage.py shell
from user.models import User

for name in ['demo', 'racktables']:
    user = User(username=name, email='%s@dmm.local' % name, is_superuser=True)
    user.set_password('demo')
    user.save()
END
