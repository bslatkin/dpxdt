TODO: Work in progress


------


create secrets.py with these values:

go to the API console and update config with your own oauth scopes:

generate the db
create database test;

create a build

create an API key

make yourself and your api key superusers

select * from user;
update user set superuser = 1 where user.id = 'foo';
select * from api_key;
update api_key set superuser = 1 where id = 'foo';



app engine specific stuff

go here to provision cloudsql

connect to your sql instance this way

google_sql.sh dpxdt-cloud:test
